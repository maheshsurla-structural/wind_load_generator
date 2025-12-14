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

# Matches both "_Q3" and "Q3" (case-insensitive), returns quadrant digit 1..4
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


def _parse_quadrant_from_load_case_name(name: str) -> int:
    """
    Parse quadrant (Q1..Q4) from a load case name. Defaults to 1 if absent.
    Matches both "_Q3" and "Q3" patterns.
    """
    m = _QUADRANT_RE.search(name or "")
    return int(m.group(1)) if m else 1


def _apply_quadrant_sign_convention(q: int, t: float, l: float) -> tuple[float, float]:
    """
    Apply sign conventions per quadrant to base (Q1) transverse/longitudinal
    coefficients and return (t, l).
    """
    ts, ls = _QUAD_SIGNS.get(int(q), _QUAD_SIGNS[1])
    return ts * t, ls * l


def _normalize_and_validate_wl_cases_df(wl_cases_df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and normalize the WL cases table.

    Expected columns:
      - Case: (present but not used here; required for schema consistency)
      - Angle: integer degrees (numeric; must be integer-like, e.g., 15 or 15.0)
      - Value: load case name string (non-empty; will be stripped)

    Returns a copy with:
      - Angle coerced to int
      - Value stripped and coerced to string

    Raises ValueError with row indices on invalid input.
    """
    needed = {"Case", "Angle", "Value"}
    missing = needed - set(wl_cases_df.columns)
    if missing:
        raise ValueError(f"wl_cases_df is missing columns: {missing}")

    df = wl_cases_df.copy()

    # Coerce Angle to numeric first
    df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
    bad_angle = df["Angle"].isna()
    if bad_angle.any():
        raise ValueError(
            f"wl_cases_df has non-numeric Angle at rows: {df.index[bad_angle].tolist()}"
        )

    # Enforce integer-like angles (e.g., 15.0 OK, 15.5 not OK)
    non_int = (df["Angle"] % 1 != 0)
    if non_int.any():
        raise ValueError(
            f"wl_cases_df has non-integer Angle at rows: {df.index[non_int].tolist()}"
        )
    df["Angle"] = df["Angle"].astype(int)

    # Normalize + validate Value (load case name)
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

def build_wl_case_components_from_control_data(
    *,
    angles: Sequence[int],
    transverse: Sequence[float],
    longitudinal: Sequence[float],
    wl_cases_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combine ControlData 'wind_live' coefficients with the WL load cases table.

    Returns a DataFrame like:

        load_case      (str)   e.g. "WL_Ang15_Q1"
        load_group     (str)   same as load_case (rule: group name = case name)
        angle          (int)   e.g. 15
        transverse     (float) with sign adjusted by quadrant
        longitudinal   (float) with sign adjusted by quadrant

    Any WL rows whose Angle is not in `angles` are skipped.
    """
    if wl_cases_df is None or wl_cases_df.empty:
        return pd.DataFrame(
            columns=["load_case", "load_group", "angle", "transverse", "longitudinal"]
        )

    # Validate + normalize external WL cases table
    wl_cases_df = _normalize_and_validate_wl_cases_df(wl_cases_df)

    # Map angle -> (Tx, Lx) for the *base* (Q1) coefficients
    if not (len(angles) == len(transverse) == len(longitudinal)):
        raise ValueError("angles / transverse / longitudinal must have same length")

    angle_to_coeffs: dict[int, tuple[float, float]] = {}
    for ang, t, l in zip(angles, transverse, longitudinal):
        angle_to_coeffs[int(ang)] = (float(t), float(l))

    rows: list[dict] = []
    for _, row in wl_cases_df.iterrows():
        ang = row["Angle"]  # already int after normalization
        lcname = str(row["Value"])  # already validated + stripped

        coeffs = angle_to_coeffs.get(ang)
        if coeffs is None:
            # No coefficient for this angle – skip
            continue

        base_t, base_l = coeffs

        # Quadrant-based sign handling
        q = _parse_quadrant_from_load_case_name(lcname)
        t, l = _apply_quadrant_sign_convention(q, base_t, base_l)

        rows.append(
            {
                "load_case": lcname,
                "load_group": lcname,  # rule: group name = case name
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

def build_wl_beam_load_plan_for_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    eccentricity: float = 6.0,
    element_ids: list[int] | None = None,
    elements_in_model=None,   # accepted for API compatibility (unused)
    nodes_in_model=None,      # accepted for API compatibility (unused)
) -> pd.DataFrame:
    """
    Take WL components (transverse/longitudinal line loads) and build a combined
    beam-load plan DataFrame for MIDAS, but DO NOT send it.
    """
    if components_df is None or components_df.empty:
        print(f"[build_wl_beam_load_plan_for_group] No components for {group_name}")
        return pd.DataFrame()

    # Resolve group → element_ids (cached)
    if element_ids is None:
        element_ids = get_group_element_ids(group_name)
    else:
        element_ids = [int(e) for e in element_ids]

    if not element_ids:
        print(f"[build_wl_beam_load_plan_for_group] Group {group_name} has no elements")
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
                    eccentricity=eccentricity,  # 6 ft by default
                )
            )

    if not plans:
        print(f"[build_wl_beam_load_plan_for_group] All WL line loads ~ 0 for {group_name}")
        return pd.DataFrame()

    combined_plan = pd.concat(plans, ignore_index=True)
    combined_plan.sort_values(["load_case", "element_id"], inplace=True)
    combined_plan.reset_index(drop=True, inplace=True)
    return combined_plan


# ---------------------------------------------------------------------------
# 3) Apply the plan to MIDAS (wrapper)
# ---------------------------------------------------------------------------

def apply_wl_beam_loads_to_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    dbg=None,
    print_summary: bool = False,
) -> None:
    """
    Convenience wrapper: build the WL beam-load plan and send it to MIDAS.

    Changes:
      - summarize_plan() no longer writes CSV/log; it can optionally dump a summary to DebugSink.
      - apply_beam_load_plan_to_midas() is called with debug/debug_label for chunk dumping.
    """
    combined_plan = build_wl_beam_load_plan_for_group(group_name, components_df)

    if combined_plan is None or combined_plan.empty:
        print(f"[apply_wl_beam_loads_to_group] No loads for group {group_name}")
        return

    summarize_plan(
        combined_plan,
        label=f"WL_{group_name}",
        sink=dbg,
        print_summary=print_summary,
    )

    apply_beam_load_plan_to_midas(
        combined_plan,
        debug=dbg,
        debug_label=f"WL_{group_name}",
    )



# ---------------------------------------------------------------------------
# 4) Build plans for multiple deck groups (WL only)
# ---------------------------------------------------------------------------

def build_wl_beam_load_plans_for_deck_groups(
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
    Build WL wind beam-load plans for all deck groups.

    Args:
        deck_groups: iterable of deck group names
        wind_live: object with attributes angles/transverse/longitudinal (Control Data)
        wl_cases_df: DataFrame with columns Case/Angle/Value
        group_members: optional mapping group_name -> element_ids
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
    components_df = build_wl_case_components_from_control_data(
        angles=angles,
        transverse=wind_live.transverse,
        longitudinal=wind_live.longitudinal,
        wl_cases_df=wl_cases_df,
    )
    if components_df.empty:
        return [], False

    plans: list[pd.DataFrame] = []
    wl_applied_any = False

    for group_name in deck_groups:
        group_name = str(group_name).strip()
        if not group_name:
            continue

        cached_ids = group_members.get(group_name)
        element_ids_for_plan = cached_ids if cached_ids else None

        plan_wl = build_wl_beam_load_plan_for_group(
            group_name=group_name,
            components_df=components_df,
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
