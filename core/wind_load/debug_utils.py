# core/wind_load/debug_utils.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import re
from typing import Dict, Any

import pandas as pd

# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------

DEBUG_DIR = Path(__file__).resolve().parent / "wind_debug"
DEBUG_DIR.mkdir(exist_ok=True)

DEBUG_LOG_FILE = DEBUG_DIR / "wind_debug.txt"


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


def _safe_case_name(name: str) -> str:
    """
    Turn a load-case name into a safe filename fragment.
    """
    s = str(name).strip()
    s = re.sub(r"[^\w\-\.]+", "_", s)
    return s or "unnamed"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# -------------------------------------------------------------------
# Plan summary + optional CSV dump + logging
# -------------------------------------------------------------------

def summarize_plan(
    plan_df: pd.DataFrame,
    label: str,
    *,
    dump_csv_per_case: bool = False,
    write_log: bool = True,
    max_cases_print: int = 30,
) -> None:
    """
    Pretty-print a summary of a beam-load plan, optionally:
      - writing per-load-case CSVs
      - logging a compact summary to wind_debug.txt
    """

    if plan_df is None or plan_df.empty:
        print(color(f"[DEBUG:{label}] plan_df is empty", "yellow"))
        return

    total_rows = len(plan_df)
    unique_cases = plan_df["load_case"].unique()
    n_cases = len(unique_cases)

    print(
        color(
            f"\n[DEBUG:{label}] Beam-load plan summary "
            f"(rows={total_rows}, load_cases={n_cases})",
            "cyan",
        )
    )

    # Per-load-case counts
    case_counts = (
        plan_df.groupby("load_case")["element_id"]
        .nunique()
        .sort_index()
    )
    # Per-load-case & direction
    case_dir_counts = (
        plan_df.groupby(["load_case", "load_direction"])["element_id"]
        .nunique()
        .sort_index()
    )

    print(color("  Element count per load_case:", "bold"))
    if len(case_counts) <= max_cases_print:
        print(case_counts)
    else:
        # Print first few only
        print(case_counts.head(max_cases_print))
        print(color(f"  ... ({len(case_counts) - max_cases_print} more)", "yellow"))

    print(color("\n  Element count per (load_case, direction):", "bold"))
    if len(case_dir_counts) <= max_cases_print:
        print(case_dir_counts)
    else:
        print(case_dir_counts.head(max_cases_print))
        print(color(f"  ... ({len(case_dir_counts) - max_cases_print} more)", "yellow"))

    # Optional: per-load-case CSVs
    if dump_csv_per_case:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for lc in unique_cases:
            safe_lc = _safe_case_name(lc)
            out_path = DEBUG_DIR / f"{ts}_{label}_{safe_lc}.csv"
            sub = plan_df[plan_df["load_case"] == lc]
            sub.to_csv(out_path, index=False)
        print(
            color(
                f"\n  [DEBUG:{label}] wrote per-load-case CSVs to {DEBUG_DIR}",
                "green",
            )
        )

    # Optional: compact log line
    if write_log:
        with DEBUG_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(
                f"[{_now_str()}] {label}: rows={total_rows}, "
                f"cases={n_cases}\n"
            )
            for lc, cnt in case_counts.items():
                f.write(f"    {lc}: {cnt} elements\n")

    print()  # blank line
    return


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

    elems_a = set(map(int, plan_a["element_id"].unique()))
    elems_b = set(map(int, plan_b["element_id"].unique()))

    extra_a = sorted(elems_a - elems_b)
    extra_b = sorted(elems_b - elems_a)

    result["extra_elements_in_a"] = extra_a
    result["extra_elements_in_b"] = extra_b

    print(
        color(
            f"\n[COMPARE] Element coverage {label_a} vs {label_b}", "magenta"
        )
    )
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

    # Per-load-case counts
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
            print(
                color(
                    f"  {lc}: {label_a}={ca}, {label_b}={cb}  <-- MISMATCH",
                    "red",
                )
            )
            result["mismatched_cases"][lc] = (ca, cb)
        else:
            print(f"  {lc}: {label_a}={ca}, {label_b}={cb}")

    if not result["mismatched_cases"]:
        print(color("\n[COMPARE] All common load cases have matching counts.", "green"))

    print()
    return result
