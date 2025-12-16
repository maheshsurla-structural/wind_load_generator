# core/wind_load/wind_common.py
from __future__ import annotations

from typing import Any, Sequence, Dict, Tuple, Mapping
import re
import pandas as pd

from core.wind_load.groups import get_group_element_ids
from core.wind_load.beam_load import (
    build_uniform_load_beam_load_plan_for_group,
    convert_pressure_to_line_loads_by_exposure_depth,
    _get_element_to_section_map,
    get_section_properties_cached,
)
from core.wind_load.beam_load import compute_section_exposures


# =============================================================================
# Quadrant helpers
# =============================================================================

_QUADRANT_RE = re.compile(r"(?:_Q|Q)([1-4])\b", re.I)

_QUAD_SIGNS: dict[int, tuple[int, int]] = {
    1: (+1, +1),
    2: (+1, -1),
    3: (-1, -1),
    4: (-1, +1),
}


def parse_quadrant_from_load_case_name(name: str) -> int:
    """Parse Q1..Q4 from case name. Defaults to Q1 if missing."""
    m = _QUADRANT_RE.search(name or "")
    return int(m.group(1)) if m else 1


def apply_quadrant_sign_convention(q: int, t: float, l: float) -> tuple[float, float]:
    """Apply quadrant signs to (t, l)."""
    ts, ls = _QUAD_SIGNS.get(int(q), _QUAD_SIGNS[1])
    return ts * float(t), ls * float(l)


# =============================================================================
# Case table normalization: Case/Angle/Value
# Used by WL + WS deck + WS sub
# =============================================================================

def normalize_and_validate_cases_df(
    df_in: pd.DataFrame,
    *,
    df_name: str = "cases_df",
) -> pd.DataFrame:
    """
    Expected columns: Case, Angle, Value
    - Angle numeric + integer-like -> int
    - Case/Value stripped and non-empty
    """
    needed = {"Case", "Angle", "Value"}
    missing = needed - set(df_in.columns)
    if missing:
        raise ValueError(f"{df_name} is missing columns: {missing}")

    df = df_in.copy()

    df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
    bad = df["Angle"].isna()
    if bad.any():
        raise ValueError(f"{df_name} has non-numeric Angle at rows: {df.index[bad].tolist()}")

    non_int = (df["Angle"] % 1 != 0)
    if non_int.any():
        raise ValueError(f"{df_name} has non-integer Angle at rows: {df.index[non_int].tolist()}")

    df["Angle"] = df["Angle"].astype(int)

    df["Case"] = df["Case"].astype(str).str.strip()
    df["Value"] = df["Value"].astype(str).str.strip()

    empty_case = df["Case"] == ""
    if empty_case.any():
        raise ValueError(f"{df_name} has empty Case at rows: {df.index[empty_case].tolist()}")

    empty_val = df["Value"] == ""
    if empty_val.any():
        raise ValueError(f"{df_name} has empty Value at rows: {df.index[empty_val].tolist()}")

    return df


# =============================================================================
# Coefficients normalization (angles, transverse, longitudinal)
# Used by WL coeffs + skew coeffs
# =============================================================================

def coeffs_by_angle(
    *,
    angles: Sequence[Any],
    transverse: Sequence[Any],
    longitudinal: Sequence[Any],
    table_name: str = "coeffs",
    require_unique_angles: bool = True,
) -> Dict[int, Tuple[float, float]]:
    """
    Returns {angle:int -> (T:float, L:float)}
    """
    if angles is None:
        raise ValueError(f"{table_name}: angles is None")

    if not (len(angles) == len(transverse) == len(longitudinal)):
        raise ValueError(
            f"{table_name}: angles/transverse/longitudinal must have same length "
            f"(got {len(angles)}, {len(transverse)}, {len(longitudinal)})"
        )

    df = pd.DataFrame({"Angle": list(angles), "T": list(transverse), "L": list(longitudinal)})

    df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
    bad = df["Angle"].isna()
    if bad.any():
        raise ValueError(f"{table_name}: non-numeric angle at rows: {df.index[bad].tolist()}")

    non_int = (df["Angle"] % 1 != 0)
    if non_int.any():
        raise ValueError(f"{table_name}: non-integer angle at rows: {df.index[non_int].tolist()}")

    df["Angle"] = df["Angle"].astype(int)

    df["T"] = pd.to_numeric(df["T"], errors="coerce")
    bad_t = df["T"].isna()
    if bad_t.any():
        raise ValueError(f"{table_name}: non-numeric transverse at rows: {df.index[bad_t].tolist()}")

    df["L"] = pd.to_numeric(df["L"], errors="coerce")
    bad_l = df["L"].isna()
    if bad_l.any():
        raise ValueError(f"{table_name}: non-numeric longitudinal at rows: {df.index[bad_l].tolist()}")

    if require_unique_angles:
        dup = df["Angle"].duplicated(keep=False)
        if dup.any():
            counts = df.loc[dup, "Angle"].value_counts().sort_index().to_dict()
            raise ValueError(f"{table_name}: duplicate angles found: {counts}")

    return {
        int(a): (float(t), float(l))
        for a, t, l in zip(df["Angle"].tolist(), df["T"].tolist(), df["L"].tolist())
    }


# =============================================================================
# Plan helpers (formerly plan_common.py)
# =============================================================================

EPS = 1e-9


def resolve_element_ids(group_name: str, element_ids: list[int] | None) -> list[int]:
    """
    Return element_ids (int list). Uses cached group lookup if element_ids is None.
    """
    if element_ids is None:
        element_ids = get_group_element_ids(group_name)
    return [int(e) for e in element_ids]


def combine_plans(plans: list[pd.DataFrame]) -> pd.DataFrame:
    """
    Combine plan dfs into one (sorted).
    """
    if not plans:
        return pd.DataFrame()
    out = pd.concat(plans, ignore_index=True)
    out.sort_values(["load_case", "element_id"], inplace=True)
    out.reset_index(drop=True, inplace=True)
    return out


def build_line_load_plan_from_components(
    *,
    group_name: str,
    components_df: pd.DataFrame,
    component_map: Mapping[str, str],  # {component_col: "LX"/"LY"/...}
    element_ids: list[int],
    eccentricity: float = 0.0,
    load_case_col: str = "load_case",
    load_group_col: str = "load_group",
) -> pd.DataFrame:
    """
    Build a combined plan from a components_df where each component column is already k/ft (line load).
    """
    if components_df is None or components_df.empty:
        return pd.DataFrame()
    if not element_ids:
        return pd.DataFrame()

    plans: list[pd.DataFrame] = []

    for _, row in components_df.iterrows():
        lc = str(row.get(load_case_col, "")).strip()
        if not lc:
            continue
        lg = str(row.get(load_group_col) or lc)

        for col, direction in component_map.items():
            val = float(row.get(col, 0.0))
            if abs(val) <= EPS:
                continue

            plan = build_uniform_load_beam_load_plan_for_group(
                group_name=group_name,
                load_case_name=lc,
                line_load=val,
                udl_direction=direction,
                load_group_name=lg,
                element_ids=element_ids,
                eccentricity=eccentricity,
            )
            if plan is not None and not plan.empty:
                plans.append(plan)

    return combine_plans(plans)


def _depth_map_for_axis(
    *,
    element_ids: list[int],
    axis: str,  # "y" or "z"
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
) -> Dict[int, float]:
    """
    Resolve depth_by_eid for exposure_y or exposure_z once.
    """
    if not element_ids:
        return {}

    elem_to_sect = _get_element_to_section_map(element_ids)
    if not elem_to_sect:
        return {}

    section_props_raw = get_section_properties_cached()
    exposures_df = compute_section_exposures(
        section_props_raw,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
        as_dataframe=True,
    )
    if exposures_df is None or exposures_df.empty:
        return {}

    try:
        exposures_df.index = exposures_df.index.astype(int)
    except ValueError:
        pass

    col = "exposure_z" if str(axis).lower() == "z" else "exposure_y"

    depth_by_eid: Dict[int, float] = {}
    for eid, sect_id in elem_to_sect.items():
        if sect_id in exposures_df.index:
            depth_by_eid[int(eid)] = float(exposures_df.loc[sect_id, col])

    return depth_by_eid


def build_pressure_plan_from_components(
    *,
    group_name: str,
    components_df: pd.DataFrame,
    component_map: Mapping[str, Tuple[str, str]],
    # {pressure_col: (udl_direction, axis)} where axis is "y" or "z"
    element_ids: list[int],
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
    load_case_col: str = "load_case",
    load_group_col: str = "load_group",
) -> pd.DataFrame:
    """
    Build a combined plan from a components_df where component columns are pressures (ksf).
    Converts pressure -> line load per element via exposure depth.
    """
    if components_df is None or components_df.empty:
        return pd.DataFrame()
    if not element_ids:
        return pd.DataFrame()

    # build the needed depth maps once
    depth_maps: Dict[str, Dict[int, float]] = {}
    for _, axis in component_map.values():
        axis = str(axis).lower()
        if axis not in depth_maps:
            depth_maps[axis] = _depth_map_for_axis(
                element_ids=element_ids,
                axis=axis,
                extra_exposure_y_default=extra_exposure_y_default,
                extra_exposure_y_by_id=extra_exposure_y_by_id,
            )

    plans: list[pd.DataFrame] = []

    for _, row in components_df.iterrows():
        lc = str(row.get(load_case_col, "")).strip()
        if not lc:
            continue
        lg = str(row.get(load_group_col) or lc)

        for p_col, (direction, axis) in component_map.items():
            p = float(row.get(p_col, 0.0))
            if abs(p) <= EPS:
                continue

            axis = str(axis).lower()
            depth_by_eid = depth_maps.get(axis) or {}
            if not depth_by_eid:
                continue

            plan = convert_pressure_to_line_loads_by_exposure_depth(
                group_name=group_name,
                load_case_name=lc,
                pressure=p,
                udl_direction=direction,
                depth_by_eid=depth_by_eid,
                load_group_name=lg,
            )
            if plan is not None and not plan.empty:
                plans.append(plan)

    return combine_plans(plans)


__all__ = [
    # quadrant + sign
    "parse_quadrant_from_load_case_name",
    "apply_quadrant_sign_convention",
    # cases + coeffs
    "normalize_and_validate_cases_df",
    "coeffs_by_angle",
    # plans
    "resolve_element_ids",
    "combine_plans",
    "build_line_load_plan_from_components",
    "build_pressure_plan_from_components",
]
