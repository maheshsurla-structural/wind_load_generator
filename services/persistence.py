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
            "version": 1,
            "structural": {"reference_height": 0.0, "pier_radius": 10.0},  # match dialog
            "naming": {
                "deck_name": "Deck",
                "pier_base_name": "Pier",
                "starting_index": 1,
                "suffix_above": "_SubAbove",
                "suffix_below": "_SubBelow",
            },
            "loads": {"gust_factor": 1.00, "drag_coefficient": 1.20},
            "units": {"length": "FT", "force": "KIPS"},
        }
        return self.load(
            "control_data.json",
            default=default,
            version=1,
            schema_name="control_data.schema.json",
            migrate=self._migrate_control_data,
        )


    def save_control_data(self, data: Any) -> None:
        # Accept dataclasses as well as dicts
        payload = asdict(data) if is_dataclass(data) else data
        if not isinstance(payload, dict):
            raise ConfigError("control_data must be a dict or dataclass.")
        if "version" not in payload:
            payload = {"version": 1, **payload}
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

    # ------------- migrations -------------

    def _migrate_control_data(self, old: dict, old_v: int, new_v: int) -> dict:
        data = dict(old) if isinstance(old, dict) else {}
        ov = int(data.get("version", old_v or 0))

        # Ensure sections exist
        s = data.setdefault("structural", {})
        n = data.setdefault("naming", {})
        l = data.setdefault("loads", {})
        u = data.setdefault("units", {})

        # --- v0 -> v1: normalize structural keys & convert from meters if needed ---
        # 1) If old *_m keys exist, move them to new names
        if "reference_height_m" in s and "reference_height" not in s:
            s["reference_height"] = s.pop("reference_height_m")
        if "pier_radius_m" in s and "pier_radius" not in s:
            s["pier_radius"] = s.pop("pier_radius_m")

        # 2) If we migrated from *_m, convert those meter values to current units (default FT)
        length = (u.get("length") or "FT").upper()
        def m_to_unit(x: float, unit: str) -> float:
            factors = {
                "M": 1.0, "CM": 100.0, "MM": 1000.0,
                "FT": 3.280839895, "IN": 39.37007874,
            }
            return float(x) * factors.get(unit, 1.0)

        # Convert only if original keys existed in meters
        if ov < 1 and ("reference_height" in s or "pier_radius" in s):
            # Heuristically assume pre-v1 values were meters
            try:
                if "reference_height" in s:
                    s["reference_height"] = m_to_unit(float(s["reference_height"]), length)
                if "pier_radius" in s:
                    s["pier_radius"] = m_to_unit(float(s["pier_radius"]), length)
            except Exception:
                # best-effort; if conversion fails, keep raw values
                pass

        # Stamp sensible defaults for any missing fields
        s.setdefault("reference_height", 0.0)
        s.setdefault("pier_radius", 10.0)

        n.setdefault("deck_name", "Deck")
        n.setdefault("pier_base_name", "Pier")
        n.setdefault("starting_index", 1)
        n.setdefault("suffix_above", "_SubAbove")
        n.setdefault("suffix_below", "_SubBelow")

        l.setdefault("gust_factor", 1.00)
        l.setdefault("drag_coefficient", 1.20)

        # Also normalize force unit alias
        fu = (u.get("force") or "KIPS").upper()
        if fu == "KIP":
            fu = "KIPS"
        u["force"] = fu
        u.setdefault("length", "FT")

        data["version"] = new_v
        return data

