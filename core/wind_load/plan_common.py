# core/wind_load/plan_common.py
from __future__ import annotations

from typing import Dict, Mapping, Tuple
import pandas as pd

from core.wind_load.groups import get_group_element_ids
from core.wind_load.beam_load import (
    build_uniform_load_beam_load_plan_for_group,
    build_uniform_pressure_beam_load_plan_from_depths,
    _get_element_to_section_map,
    get_section_properties_cached,
)
from core.wind_load.compute_section_exposures import compute_section_exposures


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

            plan = build_uniform_pressure_beam_load_plan_from_depths(
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
    "resolve_element_ids",
    "combine_plans",
    "build_line_load_plan_from_components",
    "build_pressure_plan_from_components",
]
