from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import json
import re
from typing import Any, Dict, Iterable

import pandas as pd


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


def _item_to_dict(item: Any) -> Dict[str, Any]:
    """
    Make BeamLoadItem (or any object) JSON-serializable.
    Tries common patterns: model_dump(), dict(), __dict__.
    """
    if item is None:
        return {}
    if hasattr(item, "model_dump"):
        try:
            return item.model_dump()
        except Exception:
            pass
    if hasattr(item, "dict"):
        try:
            return item.dict()
        except Exception:
            pass
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    return {"repr": repr(item)}


@dataclass
class DebugSink:
    """
    Run-scoped debug artifact recorder.

    When enabled, creates a run directory and writes:
      - manifest.json
      - plans/*.json (+ per-case splits)
      - components/*.json
      - midas_chunks/*chunk_###.json
      - summaries/*.json (new)
    """
    enabled: bool = False
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "wind_debug")
    run_label: str = "WIND"
    run_id: str = field(default_factory=_now_stamp)

    # internal manifest
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

    def _add_artifact(self, kind: str, path: Path, meta: Dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        self.manifest["artifacts"].append({"kind": kind, "path": str(path), "meta": meta or {}})
        self._write_manifest()

    def _write_manifest(self) -> None:
        if not self.enabled:
            return
        _json_dump(self.run_dir / "manifest.json", self.manifest)

    # ---------------------------
    # Public dump helpers
    # ---------------------------

    def dump_plan(
        self,
        plan_df: pd.DataFrame,
        *,
        label: str,
        split_per_case: bool = True,
    ) -> None:
        if not self.enabled:
            return
        if plan_df is None or plan_df.empty:
            return

        safe_label = _safe_name(label)
        out_path = self.run_dir / "plans" / f"{safe_label}.json"

        payload = {
            "label": label,
            "rows": int(len(plan_df)),
            "columns": list(plan_df.columns),
            "data": plan_df.to_dict(orient="records"),
        }
        _json_dump(out_path, payload)
        self._add_artifact("plan", out_path, {"label": label, "rows": int(len(plan_df))})

        if split_per_case and "load_case" in plan_df.columns:
            for lc, sub in plan_df.groupby("load_case", sort=False):
                lc_path = self.run_dir / "plans" / safe_label / "by_case" / f"{_safe_name(lc)}.json"
                _json_dump(
                    lc_path,
                    {
                        "label": label,
                        "load_case": str(lc),
                        "rows": int(len(sub)),
                        "data": sub.to_dict(orient="records"),
                    },
                )
                self._add_artifact(
                    "plan_case",
                    lc_path,
                    {"label": label, "load_case": str(lc), "rows": int(len(sub))},
                )

    def dump_components(self, df: pd.DataFrame, *, label: str) -> None:
        if not self.enabled:
            return
        if df is None or df.empty:
            return
        safe_label = _safe_name(label)
        out_path = self.run_dir / "components" / f"{safe_label}.json"
        _json_dump(
            out_path,
            {
                "label": label,
                "rows": int(len(df)),
                "columns": list(df.columns),
                "data": df.to_dict(orient="records"),
            },
        )
        self._add_artifact("components", out_path, {"label": label, "rows": int(len(df))})

    def dump_chunk_specs(
        self,
        specs: Iterable[tuple[int, Any]],
        *,
        label: str,
        chunk_index: int,
        reason: str = "",
    ) -> None:
        if not self.enabled:
            return

        safe_label = _safe_name(label)
        out_path = self.run_dir / "midas_chunks" / safe_label / f"chunk_{chunk_index:03d}.json"

        rows = []
        n = 0
        for element_id, item in specs:
            rows.append({"element_id": int(element_id), "item": _item_to_dict(item)})
            n += 1

        _json_dump(
            out_path,
            {
                "label": label,
                "chunk_index": int(chunk_index),
                "reason": reason,
                "count": n,
                "specs": rows,
            },
        )
        self._add_artifact(
            "midas_chunk",
            out_path,
            {"label": label, "chunk_index": int(chunk_index), "count": n, "reason": reason},
        )

    def dump_summary(self, summary: Dict[str, Any], *, label: str) -> None:
        """
        Store a compact summary dict (typically from summarize_plan()).
        """
        if not self.enabled:
            return
        safe_label = _safe_name(label)
        out_path = self.run_dir / "summaries" / f"{safe_label}.json"
        _json_dump(out_path, {"label": label, **(summary or {})})
        self._add_artifact("summary", out_path, {"label": label})
