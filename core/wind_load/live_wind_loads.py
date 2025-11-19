# core/wind_load/live_wind_loads.py
from __future__ import annotations

from typing import Sequence, List, Tuple
import pandas as pd
import math
import re  # ← NEW

from core.wind_load.beam_load import (
    build_uniform_load_beam_load_plan_for_group,
    apply_beam_load_plan_to_midas,
)

from midas.resources.structural_group import StructuralGroup
from midas.resources.element_beam_load import BeamLoadItem, BeamLoadResource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_quadrant_from_name(name: str) -> int:
    """
    Look for a quadrant marker in the load case name.

    Expected patterns (case-insensitive), e.g.:
        "WL_A15_Q1", "WL_A30_Q2", "MyNameQ3", "X_Q4_extra"

    Returns 1..4, defaulting to 1 if none is found.
    """
    s = (name or "").upper()

    # First try the common "_Q1" style
    m = re.search(r"_Q([1-4])\b", s)
    if m:
        return int(m.group(1))

    # Fallback: bare "Q1".."Q4" anywhere
    m = re.search(r"\bQ([1-4])\b", s)
    if m:
        return int(m.group(1))

    # Default: treat as Q1
    return 1


def _apply_quadrant_signs(q: int, t: float, l: float) -> tuple[float, float]:
    """
    Apply sign conventions per quadrant:

        Q1:  L+, T+
        Q2:  L-, T+
        Q3:  L-, T-
        Q4:  L+, T-
    """
    q = int(q)
    if q == 2:
        return t, -l
    if q == 3:
        return -t, -l
    if q == 4:
        return -t, l
    # default Q1
    return t, l


# ---------------------------------------------------------------------------
# 1) Build components table from ControlData + WL cases
# ---------------------------------------------------------------------------

def build_live_wind_components_table(
    *,
    angles: Sequence[int],
    transverse: Sequence[float],
    longitudinal: Sequence[float],
    wl_cases_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combine ControlData 'wind_live' coefficients with the WL load
    cases defined in PairWindLoadCases.

    Returns a DataFrame like:

        load_case      (str)  e.g. "WL_Ang15_Q1"
        load_group     (str)  (same as load_case for convenience)
        angle          (int)  e.g. 15
        transverse     (float)  (with sign adjusted by quadrant)
        longitudinal   (float)  (with sign adjusted by quadrant)

    Any WL rows whose Angle is not in `angles` are skipped.
    """

    if wl_cases_df is None or wl_cases_df.empty:
        return pd.DataFrame(
            columns=["load_case", "load_group", "angle", "transverse", "longitudinal"]
        )

    # Ensure the columns we expect exist
    needed_cols = {"Case", "Angle", "Value"}
    missing = needed_cols - set(wl_cases_df.columns)
    if missing:
        raise ValueError(f"wl_cases_df is missing columns: {missing}")

    # Map angle -> (Tx, Lx) for the *base* (Q1) coefficients
    if not (len(angles) == len(transverse) == len(longitudinal)):
        raise ValueError("angles / transverse / longitudinal must have same length")

    angle_to_coeffs: dict[int, tuple[float, float]] = {}
    for ang, t, l in zip(angles, transverse, longitudinal):
        angle_to_coeffs[int(ang)] = (float(t), float(l))

    rows: list[dict] = []
    for _, row in wl_cases_df.iterrows():
        ang = int(row["Angle"])
        lcname = str(row["Value"] or "").strip()
        if not lcname:
            continue

        coeffs = angle_to_coeffs.get(ang)
        if coeffs is None:
            # No coefficient for this angle – just skip
            continue

        base_t, base_l = coeffs

        # --- NEW: quadrant-based sign handling -----------------------------
        q = _extract_quadrant_from_name(lcname)
        t, l = _apply_quadrant_signs(q, base_t, base_l)
        # -------------------------------------------------------------------

        rows.append(
            {
                "load_case": lcname,
                "load_group": lcname,   # rule: group name = case name
                "angle": ang,
                "transverse": t,
                "longitudinal": l,
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(["angle", "load_case"], inplace=True)
        out.reset_index(drop=True, inplace=True)
    return out



# ---------------------------------------------------------------------------
# 2) Build beam-load plan for a structural group (WL only)
# ---------------------------------------------------------------------------

def build_live_wind_beam_load_plan_for_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    eccentricity: float = 6.0,
) -> pd.DataFrame:
    """
    Take the WL components (transverse/longitudinal line loads) and build
    a combined beam-load plan DataFrame for MIDAS, but DO NOT send it.

    This mirrors the old apply_live_wind_loads_to_group implementation.
    """

    # Resolve group → element_ids once
    element_ids = StructuralGroup.get_elements_by_name(group_name)
    element_ids = [int(e) for e in element_ids]

    if not element_ids:
        print(f"[build_live_wind_beam_load_plan_for_group] Group {group_name} has no elements")
        return pd.DataFrame()

    if components_df is None or components_df.empty:
        print(f"[build_live_wind_beam_load_plan_for_group] No components for {group_name}")
        return pd.DataFrame()

    plans: list[pd.DataFrame] = []

    for _, row in components_df.iterrows():
        lcname = str(row["load_case"])
        lgname = str(row["load_group"] or lcname)
        t = float(row["transverse"])
        l = float(row["longitudinal"])

        # Transverse → local Y
        if abs(t) > 1e-9:
            plans.append(
                build_uniform_load_beam_load_plan_for_group(
                    group_name=group_name,
                    load_case_name=lcname,
                    line_load=t,
                    udl_direction="LY",
                    load_group_name=lgname,
                    element_ids=element_ids,
                    eccentricity=eccentricity,   # 6 ft by default
                )
            )

        # Longitudinal → local X
        if abs(l) > 1e-9:
            plans.append(
                build_uniform_load_beam_load_plan_for_group(
                    group_name=group_name,
                    load_case_name=lcname,
                    line_load=l,
                    udl_direction="LX",
                    load_group_name=lgname,
                    element_ids=element_ids,
                    eccentricity=eccentricity,
                )
            )

    if not plans:
        print(f"[build_live_wind_beam_load_plan_for_group] All WL line loads ~ 0 for {group_name}")
        return pd.DataFrame()

    combined_plan = pd.concat(plans, ignore_index=True)
    combined_plan.sort_values(["load_case", "element_id"], inplace=True)
    combined_plan.reset_index(drop=True, inplace=True)
    return combined_plan



# ---------------------------------------------------------------------------
# 3) Apply the plan to MIDAS (wrapper)
# ---------------------------------------------------------------------------

def apply_live_wind_loads_to_group(group_name: str, components_df: pd.DataFrame) -> None:
    """
    Backwards-compatible wrapper: build the WL beam-load plan and send it
    to MIDAS in one call.
    """
    combined_plan = build_live_wind_beam_load_plan_for_group(group_name, components_df)

    if combined_plan is None or combined_plan.empty:
        print(f"[apply_live_wind_loads_to_group] No loads for group {group_name}")
        return

    apply_beam_load_plan_to_midas(combined_plan)


