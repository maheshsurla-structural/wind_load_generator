# core/wind_load/live_wind_loads.py
from __future__ import annotations

from typing import Sequence, Iterable, Mapping
import re

import pandas as pd

from core.wind_load.beam_load import (
    build_uniform_load_beam_load_plan_for_group,
    apply_beam_load_plan_to_midas,
)
from core.wind_load.debug_utils import summarize_plan
from core.wind_load.group_cache import get_group_element_ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUADRANT_RE = re.compile(r"(?:_Q|Q)([1-4])\b", re.I)

# returns (t_sign, l_sign) for each quadrant
_QUAD_SIGNS = {
    1: (+1, +1),
    2: (+1, -1),
    3: (-1, -1),
    4: (-1, +1),
}

_COMPONENTS = (
    ("transverse", "LY"),    # Transverse → local Y
    ("longitudinal", "LX"),  # Longitudinal → local X
)


def _extract_quadrant_from_name(name: str) -> int:
    """
    Extract quadrant (Q1..Q4) from a load case name. Defaults to 1 if absent.
    Matches both "_Q3" and "Q3" patterns.
    """
    m = _QUADRANT_RE.search(name or "")
    return int(m.group(1)) if m else 1


def _apply_quadrant_signs(q: int, t: float, l: float) -> tuple[float, float]:
    """
    Apply sign conventions per quadrant to base (Q1) transverse/longitudinal
    coefficients and return (t, l).
    """
    ts, ls = _QUAD_SIGNS.get(int(q), _QUAD_SIGNS[1])
    return ts * t, ls * l


def _validate_wl_cases_df(wl_cases_df: pd.DataFrame) -> pd.DataFrame:

    needed = {"Case", "Angle", "Value"}
    missing = needed - set(wl_cases_df.columns)
    if missing:
        raise ValueError(f"wl_cases_df is missing columns: {missing}")

    df = wl_cases_df.copy()

    # Check if the Angle input is valid numeric
    df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
    bad_angle = df["Angle"].isna()
    if bad_angle.any():
        raise ValueError(
            f"wl_cases_df has non-numeric Angle at rows: {df.index[bad_angle].tolist()}"
        )

    # Check Load case name is valid input
    s = df["Value"]
    empty = s.isna() | (s.astype(str).str.strip() == "")
    if empty.any():
        raise ValueError(
            f"wl_cases_df has empty Value at rows: {df.index[empty].tolist()}"
        )

    df["Value"] = s.astype(str).str.strip()


    return df


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

    # Validate + normalize external WL cases table
    wl_cases_df = _validate_wl_cases_df(wl_cases_df)

    # Map angle -> (Tx, Lx) for the *base* (Q1) coefficients
    if not (len(angles) == len(transverse) == len(longitudinal)):
        raise ValueError("angles / transverse / longitudinal must have same length")

    angle_to_coeffs: dict[int, tuple[float, float]] = {}
    for ang, t, l in zip(angles, transverse, longitudinal):
        angle_to_coeffs[int(ang)] = (float(t), float(l))

    rows: list[dict] = []
    for _, row in wl_cases_df.iterrows():
        ang = int(row["Angle"])

        # Value is already validated + stripped by _validate_wl_cases_df
        lcname = str(row["Value"])

        coeffs = angle_to_coeffs.get(ang)
        if coeffs is None:
            # No coefficient for this angle – just skip
            continue

        base_t, base_l = coeffs

        # Quadrant-based sign handling
        q = _extract_quadrant_from_name(lcname)
        t, l = _apply_quadrant_signs(q, base_t, base_l)

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
    element_ids: list[int] | None = None,
    elements_in_model=None,   # accepted for API compatibility (unused)
    nodes_in_model=None,      # accepted for API compatibility (unused)
) -> pd.DataFrame:


    """
    Take the WL components (transverse/longitudinal line loads) and build
    a combined beam-load plan DataFrame for MIDAS, but DO NOT send it.

    This mirrors the old apply_live_wind_loads_to_group implementation.
    """

    if components_df is None or components_df.empty:
        print(f"[build_live_wind_beam_load_plan_for_group] No components for {group_name}")
        return pd.DataFrame()

    # Resolve group → element_ids (cached)
    if element_ids is None:
        element_ids = get_group_element_ids(group_name)
    else:
        element_ids = [int(e) for e in element_ids]

    if not element_ids:
        print(f"[build_live_wind_beam_load_plan_for_group] Group {group_name} has no elements")
        return pd.DataFrame()

    plans: list[pd.DataFrame] = []

    for _, row in components_df.iterrows():
        lcname = str(row["load_case"])
        lgname = str(row["load_group"] or lcname)

        for col, direction in _COMPONENTS:
            val = float(row[col])
            if abs(val) <= 1e-9:
                continue

            plans.append(
                build_uniform_load_beam_load_plan_for_group(
                    group_name=group_name,
                    load_case_name=lcname,
                    line_load=val,
                    udl_direction=direction,
                    load_group_name=lgname,
                    element_ids=element_ids,
                    eccentricity=eccentricity,   # 6 ft by default
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

    # === DEBUG: summary, optional CSV + log ==========================
    summarize_plan(
        combined_plan,
        label=f"WL_{group_name}",
        dump_csv_per_case=False,   # set True if you want per-case CSVs
        write_log=True,
    )
    # ================================================================

    apply_beam_load_plan_to_midas(combined_plan)




def build_live_wind_plans_for_deck_groups(
    *,
    deck_groups: Iterable[str],
    wind_live,  # expects .angles, .transverse, .longitudinal
    wl_cases_df: pd.DataFrame,
    group_members: Mapping[str, list[int]] | None = None,
    elements_in_model: dict | None = None,
    nodes_in_model: dict | None = None,
    dbg=None,  # DebugSink | None (kept generic to avoid GUI import)
) -> tuple[list[pd.DataFrame], bool]:
    """
    Build LIVE wind (WL) beam-load plans for all deck groups.

    Args:
        deck_groups: iterable of deck group names
        wind_live: object with attributes angles/transverse/longitudinal (Control Data)
        wl_cases_df: DataFrame with columns Case/Angle/Value
        group_members: optional dict-like mapping group_name -> element_ids
        elements_in_model/nodes_in_model: accepted for API compatibility (unused in builder)
        dbg: optional debug sink (must have .enabled and .dump_plan())

    Returns:
        (plans, wl_applied_any)
    """
    elements_in_model = elements_in_model or {}
    nodes_in_model = nodes_in_model or {}
    group_members = group_members or {}

    angles = getattr(wind_live, "angles", None)
    if wl_cases_df is None or wl_cases_df.empty or angles is None or len(angles) == 0:
        return [], False

    # Build WL components once (shared for all deck groups)
    live_components_df = build_live_wind_components_table(
        angles=angles,
        transverse=wind_live.transverse,
        longitudinal=wind_live.longitudinal,
        wl_cases_df=wl_cases_df,
    )
    if live_components_df.empty:
        return [], False

    plans: list[pd.DataFrame] = []
    wl_applied_any = False

    for group_name in deck_groups:
        group_name = str(group_name).strip()
        if not group_name:
            continue

        cached_ids = group_members.get(group_name)
        element_ids_for_plan = cached_ids if cached_ids else None

        plan_wl = build_live_wind_beam_load_plan_for_group(
            group_name=group_name,
            components_df=live_components_df,
            element_ids=element_ids_for_plan,
            elements_in_model=elements_in_model,
            nodes_in_model=nodes_in_model,
        )

        if plan_wl is not None and not plan_wl.empty:
            if dbg is not None and getattr(dbg, "enabled", False):
                dbg.dump_plan(plan_wl, label=f"WL_{group_name}", split_per_case=True)

            plans.append(plan_wl)
            wl_applied_any = True

    return plans, wl_applied_any
