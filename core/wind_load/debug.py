# core/wind_load/debug.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import json
import re
import tempfile
from typing import Any, Dict, Optional


# A conservative filename-safe character set:
# - keep letters/digits/underscore via \w
# - keep hyphen and dot
_SAFE_CHARS_RE = re.compile(r"[^\w\-\.]+")
_UNDERSCORE_RUN_RE = re.compile(r"_+")


def _safe_name(name: str) -> str:
    """
    Convert an arbitrary label into a filesystem-friendly single path component.

    - Replaces unsafe characters with "_"
    - Collapses repeated underscores
    - Avoids empty/relative names
    """
    s = str(name or "").strip()
    s = _SAFE_CHARS_RE.sub("_", s)
    s = _UNDERSCORE_RUN_RE.sub("_", s).strip("_")

    # Avoid edge-case path components that are legal but undesirable.
    if not s or s in {".", ".."}:
        return "unnamed"

    # Optional: keep names from getting absurdly long.
    # (Still deterministic; avoids OS/path limits in practice.)
    return s[:128]


def _now_stamp() -> str:
    """Timestamp used for run_id (local time)."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _json_dump(path: Path, obj: Any) -> None:
    """
    Write JSON to disk atomically:
    - create parent dirs
    - write to a temp file in the same directory
    - replace the target file
    This prevents partial/corrupt files if the process crashes mid-write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(obj, indent=2, ensure_ascii=False, default=str)

    # Atomic replace requires temp file on same filesystem -> use same dir.
    tmp_fd: int | None = None
    tmp_path: Path | None = None
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        tmp_path = Path(tmp_name)

        with open(tmp_fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.write("\n")  # friendly newline at EOF

        tmp_path.replace(path)  # atomic on most OS/filesystems
    finally:
        # If something failed before replace, best-effort cleanup.
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


@dataclass(slots=True)
class DebugSink:
    """
    Minimal run-scoped debug sink.

    Behavior:
      - When enabled: write JSON artifacts under a run directory.
      - Primary artifact: ONE JSON file containing the exact PUT payload(s)
        sent to MIDAS by apply_beam_load_plan_to_midas().

    Output:
      wind_debug/<run_id>_<run_label>/apply/<label>.json
    """
    enabled: bool = False
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "wind_debug")
    run_label: str = "WIND"
    run_id: str = field(default_factory=_now_stamp)

    # internal manifest (optional but handy)
    manifest: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # Normalize base_dir early (nice for consistent manifests).
        self.base_dir = Path(self.base_dir)

        if not self.enabled:
            return

        # Initialize manifest once per run.
        self.manifest = {
            "run_id": self.run_id,
            "run_label": self.run_label,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "artifacts": [],
        }
        self._write_manifest()

    @property
    def run_dir(self) -> Path:
        # Derive run directory deterministically from id + label.
        return self.base_dir / f"{self.run_id}_{_safe_name(self.run_label)}"

    def _add_artifact(self, kind: str, path: Path, meta: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled:
            return

        # Be defensive: ensure manifest shape even if someone toggles enabled late.
        if not self.manifest:
            self.manifest = {
                "run_id": self.run_id,
                "run_label": self.run_label,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "artifacts": [],
            }
        self.manifest.setdefault("artifacts", []).append(
            {"kind": str(kind), "path": str(path), "meta": meta or {}}
        )
        self._write_manifest()

    def _write_manifest(self) -> None:
        if not self.enabled:
            return
        _json_dump(self.run_dir / "manifest.json", self.manifest)

    def dump_apply_payload(self, *, label: str, put_payloads: list[dict]) -> None:
        """
        Write exactly ONE JSON file containing the exact payload(s) sent to MIDAS PUT.

        Parameters
        ----------
        label : str
            Usually debug_label from apply_beam_load_plan_to_midas (e.g. "ALL_WIND")
        put_payloads : list[dict]
            List of raw payloads passed to BeamLoadResource.put_raw(),
            each typically like {"Assign": {...}}.
        """
        if not self.enabled:
            return

        safe_label = _safe_name(label)
        out_path = self.run_dir / "apply" / f"{safe_label}.json"

        payload = {
            "label": str(label),
            "n_puts": int(len(put_payloads)),
            "puts": put_payloads,  # keep exact structure
        }

        _json_dump(out_path, payload)
        self._add_artifact(
            "apply_payload",
            out_path,
            {"label": str(label), "n_puts": int(len(put_payloads))},
        )


__all__ = ["DebugSink"]
