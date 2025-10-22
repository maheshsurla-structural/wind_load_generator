# services/persistence.py
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Union

try:
    import jsonschema  # type: ignore
except Exception:  # jsonschema is optional
    jsonschema = None  # type: ignore


def _expand(path: Union[str, Path]) -> Path:
    return Path(os.path.expanduser(str(path))).resolve()


class ConfigError(RuntimeError):
    pass


class ConfigManager:
    """
    Production-grade JSON persistence with:
    - Atomic writes (tempfile + os.replace)
    - Schema validation (optional; uses jsonschema if installed)
    - Versioning + simple migration hooks
    - Thread-safety across calls
    - Automatic backup (.bak) on write

    Typical use:
        cfg = ConfigManager(app_name="wind_load_generator")
        data = cfg.load("control_data.json", default={...}, version=1, migrate=migrate_fn)
        cfg.save("control_data.json", data)
    """

    def __init__(
        self,
        app_name: str = "wind_load_generator",
        base_dir: Optional[Union[str, Path]] = None,
        schemas_dir: Optional[Union[str, Path]] = None,
    ):
        self._lock = threading.RLock()
        self.app_name = app_name
        self.base_dir = _expand(base_dir or Path.home() / f".{app_name}")
        self.schemas_dir = _expand(schemas_dir or self.base_dir / "schemas")
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Subfolders you may find useful
        (self.base_dir / "logs").mkdir(exist_ok=True)
        (self.base_dir / "backups").mkdir(exist_ok=True)

    # ------------- public high-level helpers (project-specific) -------------


    def load_control_data(self) -> dict[str, Any]:
        default = {
            "version": 5,
            "geometry": {"reference_height": 0.0, "pier_radius": 10.0},
            "naming": {
                "deck_name": "Deck",
                "pier_base_name": "Pier",
                "starting_index": 1,
                "suffix_above": "_SubAbove",
                "suffix_below": "_SubBelow",
                "wind": {
                    "bases": {"wind_on_structure": "WS", "wind_on_live_load": "WL"},
                    "limit_state_labels": {"strength_label": "ULS", "service_label": "SLS"},
                    "cases": {"strength_cases": ["III", "V"], "service_cases": ["I", "IV"]},
                    "angle": {"prefix": "Ang"},
                    "text": {"template": "{base}_{limit}_{case}_{angle_prefix}_{angle}"},
                },
            },
            "loads": {
                "gust_factor": 1.00,
                "drag_coefficient": 1.20,
                "crash_barrier_depth": 0.0,
                # NEW: skew defaults (fixed-angle table: 0,15,30,45,60)
                "skew": {
                    "transverse":  [1.000, 0.880, 0.820, 0.660, 0.340],
                    "longitudinal": [0.000, 0.120, 0.240, 0.320, 0.380],
                },
            },
            "units": {"length": "FT", "force": "KIPS"},
        }
        return self.load(
            "control_data.json",
            default=default,
            version=5,
            schema_name="control_data.schema.json",
            migrate=self._migrate_control_data,
        )



    def save_control_data(self, data: Any) -> None:
        """
        Persist control data to control_data.json.
        Accepts a ControlDataModel (with .to_dict), a dataclass, or a plain dict.
        Normalizes units and guarantees a valid loads.skew shape before writing.
        """
        # Prefer model's to_dict() if available (ControlDataModel)
        if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
            payload = data.to_dict()
        elif is_dataclass(data):
            payload = asdict(data)
        else:
            payload = data

        if not isinstance(payload, dict):
            raise ConfigError("control_data must be dict, dataclass, or model with to_dict().")

        # ---- Normalize units (accept legacy top-level keys) ----
        units = payload.get("units")
        if not isinstance(units, dict):
            units = {}
            payload["units"] = units

        if "length_unit" in payload:  # migrate legacy top-level field
            units["length"] = payload.pop("length_unit")
        if "force_unit" in payload:   # migrate legacy top-level field
            units["force"] = str(payload.pop("force_unit")).upper()

        # Stamp sensible unit defaults and normalize force spelling
        units.setdefault("length", "FT")
        f = str(units.get("force", "KIPS")).upper()
        if f == "KIP":
            f = "KIPS"
        units["force"] = f

        # ---- Ensure loads.skew is present and valid (5 values each) ----
        loads = payload.setdefault("loads", {})
        skew_in = loads.get("skew", {})
        if not isinstance(skew_in, dict):
            skew_in = {}
        loads["skew"] = self._coerce_skew_arrays(skew_in)


        # ---- Ensure crash_barrier_depth exists and is a number ----
        try:
            loads["crash_barrier_depth"] = float(loads.get("crash_barrier_depth", 0.0) or 0.0)
        except Exception:
            loads["crash_barrier_depth"] = 0.0

        # ---- Ensure version ----
        if "version" not in payload:
            payload["version"] = 5

        # ---- Save atomically with backup ----
        self.save("control_data.json", payload)



    # ------------- generic API -------------

    def load(
        self,
        filename: str,
        *,
        default: Any,
        version: int,
        migrate: Optional[Callable[[dict, int, int], dict]] = None,
        schema_name: Optional[str] = None,
        on_corruption: str = "backup_then_reset",  # or "raise"
    ) -> Any:
        """
        Load a JSON file with optional migration & schema validation.
        - default: returned if missing/corrupt (and written to disk)
        - version: current schema version
        - migrate: fn(old_data, old_version, new_version) -> new_data
        - schema_name: relative filename under `schemas_dir` (optional)
        - on_corruption: "backup_then_reset" | "raise"
        """
        path = self._path(filename)
        with self._lock:
            if not path.exists():
                self._atomic_write(path, default)
                return default

            try:
                data = self._read_json(path)
            except Exception as e:
                if on_corruption == "raise":
                    raise ConfigError(f"Failed to read {path}: {e}") from e
                # backup raw file and write default
                self._backup_corrupt(path)
                self._atomic_write(path, default)
                return default

            # Version / migration
            old_version = int(data.get("version", 0)) if isinstance(data, dict) else 0
            if old_version != version:
                if migrate:
                    try:
                        data = migrate(data if isinstance(data, dict) else {}, old_version, version)
                    except Exception as e:
                        # If migration fails, reset to default to avoid bricking the app
                        self._backup_corrupt(path, suffix=".migrate.bak")
                        self._atomic_write(path, default)
                        return default
                else:
                    # No migration provided: assume breaking change → reset to default
                    self._backup_corrupt(path, suffix=f".v{old_version}.bak")
                    data = default
                # ensure target version is stamped
                if isinstance(data, dict):
                    data["version"] = version
                self._atomic_write(path, data)

            # Schema validation (optional)
            if schema_name and jsonschema:
                schema_path = self.schemas_dir / schema_name
                if schema_path.exists():
                    try:
                        schema = self._read_json(schema_path)
                        jsonschema.validate(instance=data, schema=schema)  # type: ignore
                    except Exception as e:
                        # If schema fails, don’t crash user session; log via exception
                        # (You can replace with real logging)
                        print(f"[ConfigManager] Schema validation failed for {filename}: {e}")

            return data

    def save(self, filename: str, data: Any) -> None:
        """
        Save JSON with atomic replace and backup of previous file.
        Accepts dicts or dataclasses.
        """
        payload = asdict(data) if is_dataclass(data) else data
        if not isinstance(payload, (dict, list)):
            raise ConfigError("Only dict or list (or dataclass) can be saved as JSON.")
        path = self._path(filename)
        with self._lock:
            self._atomic_write(path, payload, make_backup=True)

    # ------------- internal utils -------------

    def _path(self, filename: str) -> Path:
        return self.base_dir / filename

    def _read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _atomic_write(self, path: Path, data: Any, make_backup: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to temp file first
        fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            if path.exists() and make_backup:
                backup = path.with_suffix(path.suffix + ".bak")
                shutil.copy2(path, backup)
            os.replace(tmp, path)  # atomic on POSIX/NTFS
        finally:
            # If replace succeeded, tmp is gone. If failed, ensure cleanup.
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def _backup_corrupt(self, path: Path, *, suffix: str = ".bak") -> None:
        try:
            target = path.with_suffix(path.suffix + suffix)
            shutil.copy2(path, target)
        except Exception:
            # Silent best-effort; avoid raising here
            pass



    def _coerce_skew_arrays(self, skew_in: dict) -> dict:
        """
        Ensure skew has 5 floats for both transverse and longitudinal.
        Truncates or pads with defaults as needed and coerces types safely.
        """
        defaults_t = [1.000, 0.880, 0.820, 0.660, 0.340]
        defaults_l = [0.000, 0.120, 0.240, 0.320, 0.380]
        N = 5

        def _as_float_list(v, fallback):
            if isinstance(v, (list, tuple)):
                out = []
                for x in v:
                    try:
                        out.append(float(x))
                    except Exception:
                        # fall back to default position if bad entry
                        out.append(None)
                # pad/truncate & fill missing with fallback
                out = (out[:N] + [None] * N)[:N]
                return [out[i] if out[i] is not None else fallback[i] for i in range(N)]
            return fallback

        t = _as_float_list(skew_in.get("transverse"), defaults_t)
        g = _as_float_list(skew_in.get("longitudinal"), defaults_l)
        return {"transverse": t, "longitudinal": g}



    # ------------- migrations -------------


    def _migrate_control_data(self, old: dict, old_v: int, new_v: int) -> dict:
        data = dict(old) if isinstance(old, dict) else {}
        ov = int(data.get("version", old_v or 0))

        # Ensure sections exist (new shape uses 'geometry')
        g = data.setdefault("geometry", {})
        n = data.setdefault("naming", {})
        l = data.setdefault("loads", {})
        u = data.setdefault("units", {})

        # ---- Legacy 'structural' -> merge into 'geometry'
        legacy_struct = data.get("structural") if isinstance(data.get("structural"), dict) else None
        if legacy_struct:
            for k, v in legacy_struct.items():
                g.setdefault(k, v)
            try:
                del data["structural"]
            except Exception:
                pass

        # ---- v0/v1 -> v2: normalize *_m keys inside geometry
        if "reference_height_m" in g and "reference_height" not in g:
            g["reference_height"] = g.pop("reference_height_m")
        if "pier_radius_m" in g and "pier_radius" not in g:
            g["pier_radius"] = g.pop("pier_radius_m")

        # ---- Normalize units (accept legacy top-level keys)
        if "length_unit" in data and "length" not in u:
            u["length"] = data.pop("length_unit")
        if "force_unit" in data and "force" not in u:
            u["force"] = str(data.pop("force_unit")).upper()

        # Defaults for units
        u.setdefault("length", "FT")
        fu = str(u.get("force") or "KIPS").upper()
        if fu == "KIP":
            fu = "KIPS"
        u["force"] = fu

        # ---- If coming from very old versions, convert geometry values from meters to current length unit
        length = str(u.get("length") or "FT").upper()

        def m_to_unit(x: float, unit: str) -> float:
            factors = {"M": 1.0, "CM": 100.0, "MM": 1000.0, "FT": 3.280839895, "IN": 39.37007874}
            return float(x) * factors.get(unit, 1.0)

        if ov < 1 and ("reference_height" in g or "pier_radius" in g):
            try:
                if "reference_height" in g:
                    g["reference_height"] = m_to_unit(float(g["reference_height"]), length)
                if "pier_radius" in g:
                    g["pier_radius"] = m_to_unit(float(g["pier_radius"]), length)
            except Exception:
                # best-effort; keep raw values if conversion fails
                pass

        # ---- Stamp sensible geometry defaults
        g.setdefault("reference_height", 0.0)
        g.setdefault("pier_radius", 10.0)

        # ---- Naming defaults (structural)
        n.setdefault("deck_name", "Deck")
        n.setdefault("pier_base_name", "Pier")
        n.setdefault("starting_index", 1)
        n.setdefault("suffix_above", "_SubAbove")
        n.setdefault("suffix_below", "_SubBelow")

        # ---- Loads defaults
        l.setdefault("gust_factor", 1.00)
        l.setdefault("drag_coefficient", 1.20)


        # ---- NEW in v5: crash_barrier_depth (accept legacy aliases)
        # Legacy keys we’ll accept: 'crash_pattern_width', 'crash_barrier_width'
        if "crash_barrier_depth" not in l:
            for k in ("crash_pattern_width", "crash_barrier_width"):
                if k in l:
                    l["crash_barrier_depth"] = l.get(k)
                    break
        try:
            l["crash_barrier_depth"] = float(l.get("crash_barrier_depth", 0.0) or 0.0)
        except Exception:
            l["crash_barrier_depth"] = 0.0

        # ---- NEW: Ensure skew table exists and is valid (fixed 5-angle table)
        skew_in = l.get("skew")
        if not isinstance(skew_in, dict):
            skew_in = {}
        l["skew"] = self._coerce_skew_arrays(skew_in)


        # ======================================================================
        # Wind naming migration & normalization (→ v4 simplified schema)
        # ======================================================================
        # Ensure 'wind' exists and is a dict (guard against null/str/list)
        wind = n.get("wind")
        if not isinstance(wind, dict):
            wind = {}
        n["wind"] = wind

        # Coerce sub-sections to dicts as well
        def _dict_or(d, key):
            val = d.get(key)
            if not isinstance(val, dict):
                val = {}
                d[key] = val
            return val

        bases = _dict_or(wind, "bases")
        limits = _dict_or(wind, "limit_state_labels")
        cases  = _dict_or(wind, "cases")
        angle  = _dict_or(wind, "angle")
        text   = _dict_or(wind, "text")

        # Defaults
        bases.setdefault("wind_on_structure", "WS")
        bases.setdefault("wind_on_live_load", "WL")

        limits.setdefault("strength_label", "ULS")
        limits.setdefault("service_label", "SLS")

        def _as_list(v, fallback):
            if isinstance(v, list):
                return [str(x) for x in v if str(x).strip()]
            if isinstance(v, str):
                parts = [t.strip() for t in v.split(",") if t.strip()]
                return parts or fallback
            return fallback

        cases["strength_cases"] = _as_list(cases.get("strength_cases"), ["III", "V"])
        cases["service_cases"]  = _as_list(cases.get("service_cases"),  ["I", "IV"])

        # Angle simplified: only 'prefix'
        angle["prefix"] = str(angle.get("prefix") or "Ang")
        for k in ("decimals", "zero_pad", "unit_suffix"):
            angle.pop(k, None)

        # Text simplified: only 'template'
        text["template"] = str(text.get("template") or "{base}_{limit}_{case}_{angle_prefix}_{angle}")
        text.pop("upper_case", None)

        # Reattach (explicit; already referencing same dicts, but keeps intent clear)
        wind["bases"] = bases
        wind["limit_state_labels"] = limits
        wind["cases"] = cases
        wind["angle"] = angle
        wind["text"] = text


        # ---- Finalize
        data["version"] = new_v
        return data



