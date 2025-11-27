# core/wind_load/structural_wind_loads.py
from __future__ import annotations

from typing import Sequence, Dict
import pandas as pd

from core.wind_load.beam_load import (
    apply_beam_load_plan_to_midas,
    build_uniform_pressure_beam_load_plan_from_depths,
    _get_element_to_section_map,
)
from midas.resources.structural_group import StructuralGroup
from midas import get_section_properties
from core.wind_load.compute_section_exposures import compute_section_exposures

from core.wind_load.live_wind_loads import (
    _extract_quadrant_from_name,
    _apply_quadrant_signs,
)

from core.wind_load.debug_utils import summarize_plan


from wind_database import wind_db


# ---------------------------------------------------------------------------
# 1) Build WS components
# ---------------------------------------------------------------------------

def build_structural_wind_components_table(
    *,
    group_name: str,
    angles: Sequence[int],
    transverse: Sequence[float],     # from Skew Coefficients
    longitudinal: Sequence[float],   # from Skew Coefficients
    ws_cases_df: pd.DataFrame,       # Case / Angle / Value
    wind_pressures_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    For each WS case row and angle, build signed transverse/longitudinal
    *pressures* starting from:

        Pz (ksf)  ← from wind_pressures table for (group, Case)
        T(θ), L(θ) ← from Skew Coefficients

    ws_cases_df columns:
        Case   : base load case name (e.g. 'Strength III')
        Angle  : skew angle
        Value  : final MIDAS load case name (with Q1..Q4 in it)

    Returns DataFrame:

        load_case
        load_group
        angle
        base_case
        Pz
        p_transverse
        p_longitudinal
    """

    if wind_pressures_df is None:
        wind_pressures_df = wind_db.wind_pressures

    if wind_pressures_df.empty or ws_cases_df is None or ws_cases_df.empty:
        return pd.DataFrame(
            columns=[
                "load_case",
                "load_group",
                "angle",
                "base_case",
                "Pz",
                "p_transverse",
                "p_longitudinal",
            ]
        )

    needed_ws = {"Case", "Angle", "Value"}
    if missing := needed_ws - set(ws_cases_df.columns):
        raise ValueError(f"ws_cases_df missing columns: {missing}")

    needed_p = {"Group", "Load Case", "Pz (ksf)"}
    if missing := needed_p - set(wind_pressures_df.columns):
        raise ValueError(f"wind_pressures_df missing columns: {missing}")

    if not (len(angles) == len(transverse) == len(longitudinal)):
        raise ValueError("angles / transverse / longitudinal must have same length")

    angle_to_coeffs: dict[int, tuple[float, float]] = {}
    for ang, t, l in zip(angles, transverse, longitudinal):
        angle_to_coeffs[int(ang)] = (float(t), float(l))

    rows: list[dict] = []

    for _, ws_row in ws_cases_df.iterrows():
        ang = int(ws_row["Angle"])
        lcname = str(ws_row["Value"] or "").strip()
        base_case = str(ws_row["Case"] or "").strip()
        if not lcname or not base_case:
            continue

        coeffs = angle_to_coeffs.get(ang)
        if coeffs is None:
            # angle not configured in skew coefficients
            continue

        base_t, base_l = coeffs

        # Pz for this group + base case
        mask = (
            (wind_pressures_df["Group"] == group_name)
            & (wind_pressures_df["Load Case"] == base_case)
        )
        sub = wind_pressures_df[mask]
        if sub.empty:
            continue

        Pz = float(sub.iloc[0]["Pz (ksf)"])

        # Quadrant-based sign handling – same as WL
        q = _extract_quadrant_from_name(lcname)
        t_coeff, l_coeff = _apply_quadrant_signs(q, base_t, base_l)

        # Directional pressures (ksf, already signed)
        p_trans = Pz * t_coeff
        p_long = Pz * l_coeff

        rows.append(
            {
                "load_case": lcname,
                "load_group": lcname,
                "angle": ang,
                "base_case": base_case,
                "Pz": Pz,
                "p_transverse": p_trans,
                "p_longitudinal": p_long,
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(["angle", "load_case"], inplace=True)
        out.reset_index(drop=True, inplace=True)
    return out


# ---------------------------------------------------------------------------
# 2) Build WS beam-load plan using precomputed depths (like live wind)
# ---------------------------------------------------------------------------

def build_structural_wind_beam_load_plan_for_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    # depth axis: "y" → exposure_y, "z" → exposure_z
    exposure_axis: str = "y",

    # extra Y exposure options (same as for deck live wind eccentricity)
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
) -> pd.DataFrame:
    """
    Same logic as apply_structural_wind_loads_to_group, but returns the
    combined beam-load plan DataFrame instead of sending it to MIDAS.
    """

    if components_df is None or components_df.empty:
        print(f"[build_structural_wind_beam_load_plan_for_group] No loads for {group_name}")
        return pd.DataFrame()

    # ---- 1) Resolve elements & exposures ONCE ------------------------
    element_ids = StructuralGroup.get_elements_by_name(group_name)
    element_ids = [int(e) for e in element_ids]

    if not element_ids:
        print(f"[build_structural_wind_beam_load_plan_for_group] Group {group_name} has no elements")
        return pd.DataFrame()

    elem_to_sect = _get_element_to_section_map(element_ids)
    if not elem_to_sect:
        print(f"[build_structural_wind_beam_load_plan_for_group] No section mapping for group {group_name}")
        return pd.DataFrame()

    section_props_raw = get_section_properties()
    exposures_df = compute_section_exposures(
        section_props_raw,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
        as_dataframe=True,
    )

    try:
        exposures_df.index = exposures_df.index.astype(int)
    except ValueError:
        pass

    depth_col = "exposure_z" if exposure_axis.lower() == "z" else "exposure_y"

    depth_by_eid: Dict[int, float] = {}
    for eid, sect_id in elem_to_sect.items():
        if sect_id in exposures_df.index:
            depth_by_eid[int(eid)] = float(exposures_df.loc[sect_id, depth_col])

    if not depth_by_eid:
        print(f"[build_structural_wind_beam_load_plan_for_group] No exposure depths for group {group_name}")
        return pd.DataFrame()

    # ---- 2) Build per-case plans in memory ---------------------------
    plans: list[pd.DataFrame] = []

    for _, row in components_df.iterrows():
        lcname = str(row["load_case"])
        lgname = str(row["load_group"] or lcname)

        p_trans = float(row["p_transverse"])
        p_long = float(row["p_longitudinal"])

        # Transverse pressure → LY
        if abs(p_trans) > 1e-9:
            plan_t = build_uniform_pressure_beam_load_plan_from_depths(
                group_name=group_name,
                load_case_name=lcname,
                pressure=p_trans,
                udl_direction="LY",
                depth_by_eid=depth_by_eid,
                load_group_name=lgname,
            )
            if not plan_t.empty:
                plans.append(plan_t)

        # Longitudinal pressure → LX
        if abs(p_long) > 1e-9:
            plan_l = build_uniform_pressure_beam_load_plan_from_depths(
                group_name=group_name,
                load_case_name=lcname,
                pressure=p_long,
                udl_direction="LX",
                depth_by_eid=depth_by_eid,
                load_group_name=lgname,
            )
            if not plan_l.empty:
                plans.append(plan_l)

    if not plans:
        print(f"[build_structural_wind_beam_load_plan_for_group] All WS line loads ~ 0 for group {group_name}")
        return pd.DataFrame()

    combined_plan = pd.concat(plans, ignore_index=True)
    combined_plan.sort_values(["load_case", "element_id"], inplace=True)
    combined_plan.reset_index(drop=True, inplace=True)
    return combined_plan


# ---------------------------------------------------------------------------
# 3) Apply WS plan to MIDAS (wrapper)
# ---------------------------------------------------------------------------

def apply_structural_wind_loads_to_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    exposure_axis: str = "y",
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
) -> None:
    """
    Backwards-compatible wrapper: build the WS beam-load plan and send it
    to MIDAS in one call.
    """

    combined_plan = build_structural_wind_beam_load_plan_for_group(
        group_name=group_name,
        components_df=components_df,
        exposure_axis=exposure_axis,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
    )

    if combined_plan is None or combined_plan.empty:
        print(f"[apply_structural_wind_loads_to_group] No loads for {group_name}")
        return

    # === DEBUG: summary, optional CSV + log ==========================
    summarize_plan(
        combined_plan,
        label=f"WS_{group_name}",
        dump_csv_per_case=False,   # flip to True when you want CSVs
        write_log=True,
    )
    # ================================================================

    apply_beam_load_plan_to_midas(combined_plan)

