# core/wind_load/debug.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import json
import re
from typing import Any, Dict, Iterable, Optional

import pandas as pd


# -------------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------------

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


# -------------------------------------------------------------------
# DebugSink (artifact writer)
# -------------------------------------------------------------------

@dataclass
class DebugSink:
    """
    Run-scoped debug artifact recorder.

    When enabled, creates a run directory and writes:
      - manifest.json
      - plans/*.json (+ per-case splits)
      - components/*.json
      - midas_chunks/*chunk_###.json
      - summaries/*.json
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

    def _add_artifact(self, kind: str, path: Path, meta: Optional[Dict[str, Any]] = None) -> None:
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
        if not self.enabled or plan_df is None or plan_df.empty:
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
        if not self.enabled or df is None or df.empty:
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


# -------------------------------------------------------------------
# Console helpers (ANSI)
# -------------------------------------------------------------------

_COLORS: Dict[str, str] = {
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "bold": "\033[1m",
}


def color(text: str, name: str) -> str:
    code = _COLORS.get(name, "")
    end = "\033[0m" if code else ""
    return f"{code}{text}{end}"


# -------------------------------------------------------------------
# Plan summary (NO file writing here; only via sink)
# -------------------------------------------------------------------

def summarize_plan(
    plan_df: pd.DataFrame,
    label: str,
    *,
    print_summary: bool = False,
    max_cases_print: int = 30,
    sink=None,                 # DebugSink-like (optional). Avoid importing GUI side.
    dump_to_sink: bool = True, # if sink.enabled and sink.dump_summary exists
) -> Dict[str, Any]:
    """
    Compute a compact summary of a beam-load plan.

    Returns dict:
      - rows
      - n_cases
      - case_counts
      - case_dir_counts
    """
    if plan_df is None or plan_df.empty:
        summary = {"rows": 0, "n_cases": 0, "case_counts": {}, "case_dir_counts": {}}
        if print_summary:
            print(color(f"[DEBUG:{label}] plan_df is empty", "yellow"))
        _maybe_dump_summary_to_sink(summary, label=label, sink=sink, dump_to_sink=dump_to_sink)
        return summary

    total_rows = int(len(plan_df))
    n_cases = int(plan_df["load_case"].dropna().nunique()) if "load_case" in plan_df.columns else 0

    # Per-load-case counts (unique elements)
    if {"load_case", "element_id"}.issubset(plan_df.columns):
        case_counts_s = plan_df.groupby("load_case")["element_id"].nunique().sort_index()
        case_counts = {str(k): int(v) for k, v in case_counts_s.items()}
    else:
        case_counts_s = None
        case_counts = {}

    # Per-load-case & direction counts
    if {"load_case", "load_direction", "element_id"}.issubset(plan_df.columns):
        case_dir_counts_s = (
            plan_df.groupby(["load_case", "load_direction"])["element_id"].nunique().sort_index()
        )
        case_dir_counts: Dict[str, Dict[str, int]] = {}
        for (lc, direction), v in case_dir_counts_s.items():
            case_dir_counts.setdefault(str(lc), {})[str(direction)] = int(v)
    else:
        case_dir_counts_s = None
        case_dir_counts = {}

    summary = {
        "rows": total_rows,
        "n_cases": n_cases,
        "case_counts": case_counts,
        "case_dir_counts": case_dir_counts,
    }

    if print_summary:
        print(
            color(
                f"\n[DEBUG:{label}] Beam-load plan summary (rows={total_rows}, load_cases={n_cases})",
                "cyan",
            )
        )

        if case_counts_s is not None:
            print(color("  Element count per load_case:", "bold"))
            if len(case_counts_s) <= max_cases_print:
                print(case_counts_s)
            else:
                print(case_counts_s.head(max_cases_print))
                print(color(f"  ... ({len(case_counts_s) - max_cases_print} more)", "yellow"))

        if case_dir_counts_s is not None:
            print(color("\n  Element count per (load_case, direction):", "bold"))
            if len(case_dir_counts_s) <= max_cases_print:
                print(case_dir_counts_s)
            else:
                print(case_dir_counts_s.head(max_cases_print))
                print(color(f"  ... ({len(case_dir_counts_s) - max_cases_print} more)", "yellow"))

        print()

    _maybe_dump_summary_to_sink(summary, label=label, sink=sink, dump_to_sink=dump_to_sink)
    return summary


def _maybe_dump_summary_to_sink(
    summary: Dict[str, Any],
    *,
    label: str,
    sink=None,
    dump_to_sink: bool,
) -> None:
    if not dump_to_sink:
        return
    if sink is None or not getattr(sink, "enabled", False):
        return
    dump_fn = getattr(sink, "dump_summary", None)
    if callable(dump_fn):
        try:
            dump_fn(summary, label=label)
        except Exception:
            # Debug should never crash main logic
            pass


# -------------------------------------------------------------------
# Consistency checker between two plans (e.g. WL vs WS)
# -------------------------------------------------------------------

def compare_plan_element_patterns(
    plan_a: pd.DataFrame,
    plan_b: pd.DataFrame,
    *,
    label_a: str = "A",
    label_b: str = "B",
) -> Dict[str, Any]:
    """
    Compare two beam-load plans (e.g. WL vs WS) and report:
      - global element_id coverage differences
      - per-load-case element count differences (only common load cases)

    Returns a dict with mismatch info.
    """
    result: Dict[str, Any] = {
        "extra_elements_in_a": [],
        "extra_elements_in_b": [],
        "mismatched_cases": {},
    }

    if plan_a is None or plan_a.empty:
        print(color(f"[COMPARE] {label_a} plan is empty", "red"))
        return result
    if plan_b is None or plan_b.empty:
        print(color(f"[COMPARE] {label_b} plan is empty", "red"))
        return result
    if "element_id" not in plan_a.columns or "element_id" not in plan_b.columns:
        print(color("[COMPARE] Missing 'element_id' column in one of the plans.", "red"))
        return result

    elems_a = set(map(int, plan_a["element_id"].unique()))
    elems_b = set(map(int, plan_b["element_id"].unique()))

    extra_a = sorted(elems_a - elems_b)
    extra_b = sorted(elems_b - elems_a)

    result["extra_elements_in_a"] = extra_a
    result["extra_elements_in_b"] = extra_b

    print(color(f"\n[COMPARE] Element coverage {label_a} vs {label_b}", "magenta"))
    print(f"  {label_a}: {len(elems_a)} unique elements")
    print(f"  {label_b}: {len(elems_b)} unique elements")
    print(f"  Common: {len(elems_a & elems_b)} elements")

    if extra_a:
        print(color(f"  Elements only in {label_a}: {len(extra_a)} (e.g., {extra_a[:10]} ...)", "yellow"))
    if extra_b:
        print(color(f"  Elements only in {label_b}: {len(extra_b)} (e.g., {extra_b[:10]} ...)", "yellow"))

    if "load_case" not in plan_a.columns or "load_case" not in plan_b.columns:
        print(color("[COMPARE] Missing 'load_case' column in one of the plans.", "red"))
        print()
        return result

    counts_a = plan_a.groupby("load_case")["element_id"].nunique().sort_index()
    counts_b = plan_b.groupby("load_case")["element_id"].nunique().sort_index()

    common_cases = sorted(set(counts_a.index) & set(counts_b.index))

    print(color("\n[COMPARE] Per-load-case element counts:", "bold"))
    for lc in common_cases:
        ca = int(counts_a[lc])
        cb = int(counts_b[lc])
        if ca != cb:
            print(color(f"  {lc}: {label_a}={ca}, {label_b}={cb}  <-- MISMATCH", "red"))
            result["mismatched_cases"][str(lc)] = (ca, cb)
        else:
            print(f"  {lc}: {label_a}={ca}, {label_b}={cb}")

    if not result["mismatched_cases"]:
        print(color("\n[COMPARE] All common load cases have matching counts.", "green"))

    print()
    return result


__all__ = [
    "DebugSink",
    "color",
    "summarize_plan",
    "compare_plan_element_patterns",
]
