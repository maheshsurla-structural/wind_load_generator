# core/wind_load/substructure_wind_loads.py
from __future__ import annotations

from typing import Dict
import math

import pandas as pd

from midas.resources.structural_group import StructuralGroup
from midas import get_section_properties

from core.wind_load.compute_section_exposures import compute_section_exposures
from core.wind_load.beam_load import (
    build_uniform_pressure_beam_load_plan_from_depths,
    _get_element_to_section_map,
    apply_beam_load_plan_to_midas,
)
from core.wind_load.debug_utils import summarize_plan
from core.wind_load.live_wind_loads import (
    _extract_quadrant_from_name,
    _apply_quadrant_signs,
)

from wind_database import wind_db


# ---------------------------------------------------------------------------
# 1) Build components table (pressure in local Y/Z for substructure)
# ---------------------------------------------------------------------------

def build_substructure_wind_components_table(
    *,
    group_name: str,
    ws_cases_df: pd.DataFrame,
    wind_pressures_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    For each WS-substructure row and angle, build signed local-Y/local-Z
    *pressures* starting from:

        P (ksf)  ← from wind_pressures table for (Group, Case)
        θ        ← from ws_cases_df['Angle'], in degrees, measured from local +Y
        Q1..Q4   ← inferred from load_case name (same logic as live wind)

    INPUT TABLES
    ------------

    ws_cases_df columns (same style as your WS deck table):
        Case   : base load case name (e.g. 'Strength III')
        Angle  : wind direction angle (deg from local +Y toward +Z)
        Value  : final MIDAS load case name, e.g. 'WS_Pier_Q2_A15'

    wind_pressures_df columns (same as deck structural wind):
        Group
        Load Case
        Pz (ksf)   ← here treated as the horizontal pressure magnitude P

    RETURNS
    -------
    pandas.DataFrame with columns:

        load_case   : final MIDAS load case name (Value)
        load_group  : same as load_case (for convenience)
        angle       : angle in degrees (as provided)
        base_case   : wind base case name (Case)
        P           : pressure magnitude (ksf)
        p_local_y   : signed pressure component in local +Y (ksf)
        p_local_z   : signed pressure component in local +Z (ksf)

    SIGN / ANGLE CONVENTION
    -----------------------
    - θ = 0°   → load fully in local +Y (p_local_y = +P, p_local_z = 0)
    - θ = 90°  → load fully in local +Z (p_local_y = 0,  p_local_z = +P)
    - intermediate angles use cos/sin components.

    After that, quadrant Q1..Q4 is applied via `_apply_quadrant_signs`,
    where we interpret:

        T ≡ local Y,  L ≡ local Z

    so the wind case name can flip signs consistently with live wind loads.
    """
    if wind_pressures_df is None:
        wind_pressures_df = wind_db.wind_pressures

    if (
        wind_pressures_df is None
        or wind_pressures_df.empty
        or ws_cases_df is None
        or ws_cases_df.empty
    ):
        return pd.DataFrame(
            columns=[
                "load_case",
                "load_group",
                "angle",
                "base_case",
                "P",
                "p_local_y",
                "p_local_z",
            ]
        )

    needed_ws = {"Case", "Angle", "Value"}
    if missing := needed_ws - set(ws_cases_df.columns):
        raise ValueError(f"ws_cases_df missing columns: {missing}")

    needed_p = {"Group", "Load Case", "Pz (ksf)"}
    if missing := needed_p - set(wind_pressures_df.columns):
        raise ValueError(f"wind_pressures_df missing columns: {missing}")

    rows: list[dict] = []

    for _, ws_row in ws_cases_df.iterrows():
        base_case = str(ws_row["Case"] or "").strip()
        lcname = str(ws_row["Value"] or "").strip()
        if not lcname or not base_case:
            continue

        try:
            ang_deg = float(ws_row["Angle"])
        except (TypeError, ValueError):
            continue

        # Pressure magnitude for this group + base case
        mask = (
            (wind_pressures_df["Group"] == group_name)
            & (wind_pressures_df["Load Case"] == base_case)
        )
        sub = wind_pressures_df[mask]
        if sub.empty:
            # No pressure defined for this (group, base_case)
            continue

        P = float(sub.iloc[0]["Pz (ksf)"])  # treat as magnitude

        # --- Base components from angle (Q1-equivalent) -----------------
        # 0° is local +Y; positive angle rotates toward local +Z.
        theta = math.radians(ang_deg)
        base_y = P * math.cos(theta)
        base_z = P * math.sin(theta)

        # --- Quadrant sign handling (reuse live_wind helpers) -----------
        # Interpret T ≡ local Y, L ≡ local Z for the sign logic.
        q = _extract_quadrant_from_name(lcname)
        y_signed, z_signed = _apply_quadrant_signs(q, base_y, base_z)

        rows.append(
            {
                "load_case": lcname,
                "load_group": lcname,
                "angle": ang_deg,
                "base_case": base_case,
                "P": P,
                "p_local_y": y_signed,
                "p_local_z": z_signed,
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(["angle", "load_case"], inplace=True)
        out.reset_index(drop=True, inplace=True)
    return out


# ---------------------------------------------------------------------------
# 2) Build substructure WS beam-load plan (LY + LZ)
# ---------------------------------------------------------------------------

def build_substructure_wind_beam_load_plan_for_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
) -> pd.DataFrame:
    """
    Build a combined beam-load plan (LY + LZ) for substructure wind on a
    structural group.

    PARAMETERS
    ----------
    group_name : str
        Name of the MIDAS structural group containing the substructure elements
        (e.g., 'Pier_1').
    components_df : pd.DataFrame
        Expected to come from build_substructure_wind_components_table and
        must contain at least:

            load_case
            load_group
            p_local_y   (ksf, signed)
            p_local_z   (ksf, signed)

    extra_exposure_y_default : float
        Global additional exposure in local Y to add (ft).
    extra_exposure_y_by_id : dict[int, float] | None
        Optional {property_id: extra_exposure_y} overrides for Y.

    LOGIC
    -----
    For each load case:

        q_LY = p_local_y * exposure_y  (k/ft)
        q_LZ = p_local_z * exposure_z  (k/ft)

    where:

        exposure_y = top + bottom + extra_y
        exposure_z = left + right

    from compute_section_exposures(). The line loads are applied as:

        LY for the Y component
        LZ for the Z component
    """
    if components_df is None or components_df.empty:
        print(f"[build_substructure_wind_beam_load_plan_for_group] No loads for {group_name}")
        return pd.DataFrame()

    # ---- Resolve elements in the group --------------------------------
    element_ids = StructuralGroup.get_elements_by_name(group_name)
    element_ids = [int(e) for e in element_ids]

    if not element_ids:
        print(
            "[build_substructure_wind_beam_load_plan_for_group] "
            f"Group {group_name} has no elements"
        )
        return pd.DataFrame()

    # ---- Map element -> section/property ID ---------------------------
    elem_to_sect = _get_element_to_section_map(element_ids)
    if not elem_to_sect:
        print(
            "[build_substructure_wind_beam_load_plan_for_group] "
            f"No section mapping for group {group_name}"
        )
        return pd.DataFrame()

    # ---- Compute exposures (Y and Z) from section properties ----------
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

    if exposures_df.empty:
        print(
            "[build_substructure_wind_beam_load_plan_for_group] "
            f"Exposure table is empty for group {group_name}"
        )
        return pd.DataFrame()

    # Build depth maps for local Y and Z separately
    depth_y_by_eid: Dict[int, float] = {}
    depth_z_by_eid: Dict[int, float] = {}

    for eid, sect_id in elem_to_sect.items():
        if sect_id in exposures_df.index:
            depth_y_by_eid[int(eid)] = float(exposures_df.loc[sect_id, "exposure_y"])
            depth_z_by_eid[int(eid)] = float(exposures_df.loc[sect_id, "exposure_z"])

    if not depth_y_by_eid and not depth_z_by_eid:
        print(
            "[build_substructure_wind_beam_load_plan_for_group] "
            f"No exposure depths for group {group_name}"
        )
        return pd.DataFrame()

    # ---- Build per-case plans in memory -------------------------------
    plans: list[pd.DataFrame] = []

    for _, row in components_df.iterrows():
        lcname = str(row["load_case"])
        lgname = str(row.get("load_group") or lcname)

        p_y = float(row.get("p_local_y", 0.0))
        p_z = float(row.get("p_local_z", 0.0))

        # Local Y component → LY
        if abs(p_y) > 1e-9 and depth_y_by_eid:
            plan_y = build_uniform_pressure_beam_load_plan_from_depths(
                group_name=group_name,
                load_case_name=lcname,
                pressure=p_y,
                udl_direction="LY",
                depth_by_eid=depth_y_by_eid,
                load_group_name=lgname,
            )
            if not plan_y.empty:
                plans.append(plan_y)

        # Local Z component → LZ
        if abs(p_z) > 1e-9 and depth_z_by_eid:
            plan_z = build_uniform_pressure_beam_load_plan_from_depths(
                group_name=group_name,
                load_case_name=lcname,
                pressure=p_z,
                udl_direction="LZ",
                depth_by_eid=depth_z_by_eid,
                load_group_name=lgname,
            )
            if not plan_z.empty:
                plans.append(plan_z)

    if not plans:
        print(
            "[build_substructure_wind_beam_load_plan_for_group] "
            f"All substructure WS line loads ~ 0 for group {group_name}"
        )
        return pd.DataFrame()

    combined_plan = pd.concat(plans, ignore_index=True)
    combined_plan.sort_values(["load_case", "element_id"], inplace=True)
    combined_plan.reset_index(drop=True, inplace=True)
    return combined_plan


# ---------------------------------------------------------------------------
# 3) Apply wrapper: build + summarize + send to MIDAS
# ---------------------------------------------------------------------------

def apply_substructure_wind_loads_to_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
) -> None:
    """
    Backwards-style wrapper for substructure WS:

        - build the WS-substructure beam-load plan (LY + LZ)
        - print a summary via summarize_plan
        - send to MIDAS via apply_beam_load_plan_to_midas
    """
    combined_plan = build_substructure_wind_beam_load_plan_for_group(
        group_name=group_name,
        components_df=components_df,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
    )

    if combined_plan is None or combined_plan.empty:
        print(f"[apply_substructure_wind_loads_to_group] No loads for {group_name}")
        return

    summarize_plan(
        combined_plan,
        label=f"WS_SUB_{group_name}",
        dump_csv_per_case=False,   # flip to True if you want per-case CSVs
        write_log=True,
    )

    apply_beam_load_plan_to_midas(combined_plan)
