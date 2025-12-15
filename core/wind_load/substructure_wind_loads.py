# core/wind_load/substructure_wind_loads.py
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Tuple, List
import math
from functools import lru_cache

import numpy as np
import pandas as pd

from wind_database import wind_db

from core.wind_load.debug import summarize_plan
from core.wind_load.beam_load import apply_beam_load_plan_to_midas
from core.wind_load.groups import get_group_element_ids, build_plans_for_groups

from core.geometry.midas_element_local_axes import MidasElementLocalAxes
from core.geometry.element_local_axes import LocalAxes

from core.wind_load.wind_common import (
    parse_quadrant_from_load_case_name,
    apply_quadrant_sign_convention,
    normalize_and_validate_cases_df,
    resolve_element_ids,
    build_pressure_plan_from_components,
)


# ---------------------------------------------------------------------------
# Pier-frame orientation helpers
# ---------------------------------------------------------------------------

_axes_helper: MidasElementLocalAxes | None = None


def _get_axes_helper() -> MidasElementLocalAxes:
    global _axes_helper
    if _axes_helper is None:
        _axes_helper = MidasElementLocalAxes.from_midas()
    return _axes_helper


@lru_cache(maxsize=128)
def _get_group_local_axes(group_name: str) -> LocalAxes:
    helper = _get_axes_helper()
    element_ids = get_group_element_ids(group_name)
    if not element_ids:
        raise RuntimeError(f"Group {group_name!r} has no elements in MIDAS.")
    return helper.compute_local_axes_for_element(int(element_ids[0]))


def _signed_angle_about_axis(
    v_from: np.ndarray,
    v_to: np.ndarray,
    axis: np.ndarray,
    *,
    tol: float = 1e-9,
) -> float:
    axis = np.asarray(axis, dtype=float)
    v_from = np.asarray(v_from, dtype=float)
    v_to = np.asarray(v_to, dtype=float)

    norm_axis = np.linalg.norm(axis)
    if norm_axis < tol:
        return 0.0
    axis = axis / norm_axis

    def _proj(v: np.ndarray) -> np.ndarray:
        v = v - np.dot(v, axis) * axis
        n = np.linalg.norm(v)
        if n < tol:
            return np.zeros(3)
        return v / n

    a = _proj(v_from)
    b = _proj(v_to)
    if not a.any() or not b.any():
        return 0.0

    cosang = float(np.clip(np.dot(a, b), -1.0, 1.0))
    sinang = float(np.dot(axis, np.cross(a, b)))
    return math.degrees(math.atan2(sinang, cosang))


@lru_cache(maxsize=256)
def _get_angle_offset_from_pier(group_name: str) -> float:
    pier_group = wind_db.get_pier_reference_for_group(group_name)
    if not pier_group or pier_group == group_name:
        return 0.0

    try:
        pier_axes = _get_group_local_axes(pier_group)
        grp_axes = _get_group_local_axes(group_name)
    except RuntimeError:
        return 0.0

    return _signed_angle_about_axis(pier_axes.ey, grp_axes.ey, pier_axes.ex)


# ---------------------------------------------------------------------------
# 1) Build components table (pressure in local Y/Z for substructure)
# ---------------------------------------------------------------------------

def build_substructure_wind_components_table(
    *,
    group_name: str,
    ws_cases_df: pd.DataFrame,
    wind_pressures_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    cols_out = [
        "load_case",
        "load_group",
        "angle",
        "design_angle",
        "base_case",
        "P",
        "p_local_y",
        "p_local_z",
    ]

    if wind_pressures_df is None:
        wind_pressures_df = wind_db.wind_pressures

    if (
        wind_pressures_df is None
        or wind_pressures_df.empty
        or ws_cases_df is None
        or ws_cases_df.empty
    ):
        return pd.DataFrame(columns=cols_out)

    group_name = str(group_name or "").strip()
    if not group_name:
        return pd.DataFrame(columns=cols_out)

    ws_cases_df = normalize_and_validate_cases_df(ws_cases_df, df_name="ws_cases_df")

    needed_p = {"Group", "Load Case", "Pz (ksf)"}
    if missing := needed_p - set(wind_pressures_df.columns):
        raise ValueError(f"wind_pressures_df missing columns: {missing}")

    # Pre-filter pressures for this group
    pz = wind_pressures_df.loc[
        wind_pressures_df["Group"] == group_name,
        ["Load Case", "Pz (ksf)"],
    ].copy()
    pz.rename(columns={"Load Case": "base_case", "Pz (ksf)": "P"}, inplace=True)
    pz = pz.drop_duplicates(subset=["base_case"], keep="first")
    p_by_base = {str(r["base_case"]).strip(): float(r["P"]) for _, r in pz.iterrows()}

    if not p_by_base:
        return pd.DataFrame(columns=cols_out)

    delta = _get_angle_offset_from_pier(group_name)

    rows: list[dict] = []
    for _, r in ws_cases_df.iterrows():
        base_case = str(r["Case"]).strip()
        lcname = str(r["Value"]).strip()
        if not base_case or not lcname:
            continue

        ang_design = float(r["Angle"])
        ang_eff = ang_design - delta
        theta = math.radians(ang_eff)

        P = p_by_base.get(base_case)
        if P is None:
            continue

        base_y = P * math.cos(theta)
        base_z = P * math.sin(theta)

        q = parse_quadrant_from_load_case_name(lcname)
        y_signed, z_signed = apply_quadrant_sign_convention(q, base_y, base_z)

        rows.append(
            {
                "load_case": lcname,
                "load_group": lcname,
                "angle": float(ang_eff),
                "design_angle": float(ang_design),
                "base_case": base_case,
                "P": float(P),
                "p_local_y": float(y_signed),
                "p_local_z": float(z_signed),
            }
        )

    out = pd.DataFrame(rows, columns=cols_out)
    if not out.empty:
        out.sort_values(["angle", "load_case"], inplace=True)
        out.reset_index(drop=True, inplace=True)
    return out


# ---------------------------------------------------------------------------
# 2) Build substructure WS beam-load plan (LY + LZ) using shared builder
# ---------------------------------------------------------------------------

def build_substructure_wind_beam_load_plan_for_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
    element_ids: list[int] | None = None,
    elements_in_model=None,
    nodes_in_model=None,
) -> pd.DataFrame:
    if components_df is None or components_df.empty:
        return pd.DataFrame()

    eids = resolve_element_ids(group_name, element_ids)
    if not eids:
        return pd.DataFrame()

    return build_pressure_plan_from_components(
        group_name=group_name,
        components_df=components_df,
        component_map={
            "p_local_y": ("LY", "y"),
            "p_local_z": ("LZ", "z"),
        },
        element_ids=eids,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
    )


# ---------------------------------------------------------------------------
# 3) Apply wrapper
# ---------------------------------------------------------------------------

def apply_substructure_wind_loads_to_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
    dbg=None,
    print_summary: bool = False,
) -> None:
    combined_plan = build_substructure_wind_beam_load_plan_for_group(
        group_name=group_name,
        components_df=components_df,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
    )

    if combined_plan is None or combined_plan.empty:
        print(f"[apply_substructure_wind_loads_to_group] No loads for {group_name}")
        return

    summarize_plan(combined_plan, label=f"WS_SUB_{group_name}", sink=dbg, print_summary=print_summary)
    apply_beam_load_plan_to_midas(combined_plan, debug=dbg, debug_label=f"WS_SUB_{group_name}")


# ---------------------------------------------------------------------------
# 4) Build plans for multiple substructure groups
# ---------------------------------------------------------------------------

def build_substructure_wind_plans_for_groups(
    *,
    sub_groups: Iterable[str],
    ws_cases_df: pd.DataFrame,
    wind_pressures_df: pd.DataFrame,
    group_members: Mapping[str, list[int]] | None = None,
    elements_in_model: dict | None = None,
    nodes_in_model: dict | None = None,
    dbg=None,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id=None,
) -> Tuple[List[pd.DataFrame], bool]:
    if ws_cases_df is None or ws_cases_df.empty:
        return [], False

    ws_cases_df = normalize_and_validate_cases_df(ws_cases_df, df_name="ws_cases_df")

    def _components_for_group(g: str) -> pd.DataFrame:
        return build_substructure_wind_components_table(
            group_name=g,
            ws_cases_df=ws_cases_df,
            wind_pressures_df=wind_pressures_df,
        )

    def _plan_for_group(g: str, comp: pd.DataFrame, eids: list[int] | None) -> pd.DataFrame:
        return build_substructure_wind_beam_load_plan_for_group(
            group_name=g,
            components_df=comp,
            extra_exposure_y_default=extra_exposure_y_default,
            extra_exposure_y_by_id=extra_exposure_y_by_id,
            element_ids=eids,
            elements_in_model=elements_in_model,
            nodes_in_model=nodes_in_model,
        )

    return build_plans_for_groups(
        groups=sub_groups,
        group_members=group_members,
        dbg=dbg,
        label_prefix="WS_SUB_",
        dump_components=True,
        build_components_for_group=_components_for_group,
        build_plan_for_group=_plan_for_group,
    )


__all__ = [
    "build_substructure_wind_components_table",
    "build_substructure_wind_beam_load_plan_for_group",
    "apply_substructure_wind_loads_to_group",
    "build_substructure_wind_plans_for_groups",
]
