# core/wind_load/live_wind_loads.py
from __future__ import annotations

from typing import Sequence,List, Tuple
import pandas as pd
import math
from core.wind_load.beam_load import (
    build_uniform_load_beam_load_plan_for_group,
    apply_beam_load_plan_to_midas,
)

from midas.resources.structural_group import StructuralGroup
from midas.resources.element_beam_load import BeamLoadItem, BeamLoadResource


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

        load_case      (str)  e.g. "WL_Ang15"
        load_group     (str)  (same as load_case for convenience)
        angle          (int)  e.g. 15
        transverse     (float)
        longitudinal   (float)

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

    # Map angle -> (Tx, Lx)
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

        t, l = coeffs
        rows.append(
            {
                "load_case": lcname,
                "load_group": lcname,   # ← your rule: group name = case name
                "angle": ang,
                "transverse": t,
                "longitudinal": l,
            }
        )

    out = pd.DataFrame(rows)
    out.sort_values(["angle", "load_case"], inplace=True)
    out.reset_index(drop=True, inplace=True)
    return out


# ---------------------------------------------------------------------------
# 2) Apply those components to a structural group in MIDAS
# ---------------------------------------------------------------------------


def apply_live_wind_loads_to_group(group_name: str, components_df: pd.DataFrame) -> None:
    """
    components_df columns:
        ['load_case', 'load_group', 'angle', 'transverse', 'longitudinal']
    """

    # ------------------------------------------------------------------
    # 0) Resolve group → element_ids once
    # ------------------------------------------------------------------
    # Again, adjust this to match your actual StructuralGroup API.
    element_ids = StructuralGroup.get_elements_by_name(group_name)
    element_ids = [int(e) for e in element_ids]

    if not element_ids:
        print(f"[apply_live_wind_loads_to_group] Group {group_name} has no elements")
        return

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
                    eccentricity=6.0,      # ← 6 ft eccentric
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
                    eccentricity=6.0,      # ← same 6 ft
                )
            )

    if not plans:
        print(f"[apply_live_wind_loads_to_group] No loads for group {group_name}")
        return

    combined_plan = pd.concat(plans, ignore_index=True)
    apply_beam_load_plan_to_midas(combined_plan)

