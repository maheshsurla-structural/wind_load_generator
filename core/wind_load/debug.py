# core/wind_load/debug.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import json
import re
from typing import Any, Dict, Optional


def _safe_name(name: str) -> str:
    s = str(name or "").strip()
    s = re.sub(r"[^\w\-\.]+", "_", s)
    return s or "unnamed"


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _json_dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)


@dataclass
class DebugSink:
    """
    Minimal run-scoped debug sink.

    Your requested behavior:
      - When enabled: write exactly ONE JSON file containing the exact PUT payload(s)
        sent to MIDAS by apply_beam_load_plan_to_midas().

    Output:
      wind_debug/<run_id>_<run_label>/apply/<label>.json
    """
    enabled: bool = False
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "wind_debug")
    run_label: str = "WIND"
    run_id: str = field(default_factory=_now_stamp)

    # internal manifest (optional but handy)
    manifest: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.enabled:
            return
        self.base_dir.mkdir(exist_ok=True, parents=True)
        self.manifest = {
            "run_id": self.run_id,
            "run_label": self.run_label,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "artifacts": [],
        }
        self._write_manifest()

    @property
    def run_dir(self) -> Path:
        return self.base_dir / f"{self.run_id}_{_safe_name(self.run_label)}"

    def _add_artifact(self, kind: str, path: Path, meta: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled:
            return
        self.manifest["artifacts"].append({"kind": kind, "path": str(path), "meta": meta or {}})
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
            "puts": put_payloads,
        }

        _json_dump(out_path, payload)
        self._add_artifact("apply_payload", out_path, {"label": str(label), "n_puts": int(len(put_payloads))})


__all__ = ["DebugSink"]
