from __future__ import annotations

from typing import Dict, Any

import pandas as pd

# -------------------------------------------------------------------
# Coloring helpers (ANSI)
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
# Plan summary (NO file writing)
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

    - If print_summary=True: prints a readable summary to console.
    - If sink is provided (DebugSink-like) and enabled: dumps summary JSON into the run.

    Returns
    -------
    dict with keys:
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

    if "load_case" in plan_df.columns:
        n_cases = int(plan_df["load_case"].dropna().nunique())
    else:
        n_cases = 0


    # Per-load-case counts (unique elements)
    if {"load_case", "element_id"}.issubset(plan_df.columns):
        case_counts_s = (
            plan_df.groupby("load_case")["element_id"]
            .nunique()
            .sort_index()
        )
        case_counts = {str(k): int(v) for k, v in case_counts_s.items()}
    else:
        case_counts_s = None
        case_counts = {}

    # Per-load-case & direction counts (JSON-safe nested dict)
    if {"load_case", "load_direction", "element_id"}.issubset(plan_df.columns):
        case_dir_counts_s = (
            plan_df.groupby(["load_case", "load_direction"])["element_id"]
            .nunique()
            .sort_index()
        )

        # JSON-safe: { "CASE1": {"LY": 123, "LX": 123}, "CASE2": {...} }
        case_dir_counts: Dict[str, Dict[str, int]] = {}
        for (lc, direction), v in case_dir_counts_s.items():
            lc = str(lc)
            direction = str(direction)
            case_dir_counts.setdefault(lc, {})[direction] = int(v)
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
                f"\n[DEBUG:{label}] Beam-load plan summary "
                f"(rows={total_rows}, load_cases={n_cases})",
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


def _maybe_dump_summary_to_sink(summary: Dict[str, Any], *, label: str, sink=None, dump_to_sink: bool) -> None:
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
      - per-load-case element count differences
        (only for load cases present in BOTH plans)

    Returns a dict with basic mismatch info, so you can also assert() in tests.
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
        print(
            color(
                f"  Elements only in {label_a}: {len(extra_a)} "
                f"(e.g., {extra_a[:10]} ...)",
                "yellow",
            )
        )
    if extra_b:
        print(
            color(
                f"  Elements only in {label_b}: {len(extra_b)} "
                f"(e.g., {extra_b[:10]} ...)",
                "yellow",
            )
        )

    if "load_case" not in plan_a.columns or "load_case" not in plan_b.columns:
        print(color("[COMPARE] Missing 'load_case' column in one of the plans.", "red"))
        print()
        return result

    counts_a = (
        plan_a.groupby("load_case")["element_id"]
        .nunique()
        .sort_index()
    )
    counts_b = (
        plan_b.groupby("load_case")["element_id"]
        .nunique()
        .sort_index()
    )

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
