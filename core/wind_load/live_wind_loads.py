# core/wind_load/live_wind_loads.py
from __future__ import annotations

from typing import Sequence, Iterable, Mapping
import pandas as pd

from core.wind_load.beam_load import apply_beam_load_plan_to_midas

from core.wind_load.wind_common import (
    parse_quadrant_from_load_case_name,
    apply_quadrant_sign_convention,
    normalize_and_validate_cases_df,
    coeffs_by_angle,
    resolve_element_ids,
    build_line_load_plan_from_components,
)

from core.wind_load.groups import build_plans_for_groups


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
    if wl_cases_df is None or wl_cases_df.empty:
        return pd.DataFrame(
            columns=["load_case", "load_group", "angle", "transverse", "longitudinal"]
        )

    wl_cases_df = normalize_and_validate_cases_df(wl_cases_df, df_name="wl_cases_df")

    angle_to_coeffs = coeffs_by_angle(
        angles=angles,
        transverse=transverse,
        longitudinal=longitudinal,
        table_name="wind_live",
    )

    rows: list[dict] = []
    for _, row in wl_cases_df.iterrows():
        ang = int(row["Angle"])
        lcname = str(row["Value"])

        base = angle_to_coeffs.get(ang)
        if base is None:
            continue

        base_t, base_l = base
        q = parse_quadrant_from_load_case_name(lcname)
        t, l = apply_quadrant_sign_convention(q, base_t, base_l)

        rows.append(
            {
                "load_case": lcname,
                "load_group": lcname,
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
    elements_in_model=None,
    nodes_in_model=None,
) -> pd.DataFrame:
    if components_df is None or components_df.empty:
        return pd.DataFrame()

    eids = resolve_element_ids(group_name, element_ids)
    if not eids:
        return pd.DataFrame()

    return build_line_load_plan_from_components(
        group_name=group_name,
        components_df=components_df,
        component_map={"transverse": "LY", "longitudinal": "LX"},
        element_ids=eids,
        eccentricity=eccentricity,
    )


# ---------------------------------------------------------------------------
# 3) Apply wrapper
# ---------------------------------------------------------------------------

def apply_wl_beam_loads_to_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    dbg=None,
    print_summary: bool = False,
) -> None:
    combined_plan = build_wl_beam_load_plan_for_group(group_name, components_df)

    if combined_plan is None or combined_plan.empty:
        print(f"[apply_wl_beam_loads_to_group] No loads for group {group_name}")
        return

    # ✅ No summarize_plan() (per your request: only final apply JSON)
    apply_beam_load_plan_to_midas(combined_plan, debug=dbg, debug_label=f"WL_{group_name}")



# ---------------------------------------------------------------------------
# 4) Build plans for multiple deck groups
# ---------------------------------------------------------------------------

def build_wl_beam_load_plans_for_deck_groups(
    *,
    deck_groups: Iterable[str],
    wind_live,
    wl_cases_df: pd.DataFrame,
    group_members: Mapping[str, list[int]] | None = None,
    elements_in_model: dict | None = None,
    nodes_in_model: dict | None = None,
    dbg=None,
) -> tuple[list[pd.DataFrame], bool]:
    angles = getattr(wind_live, "angles", None)
    if wl_cases_df is None or wl_cases_df.empty or not angles:
        return [], False

    components_df = build_wl_case_components_from_control_data(
        angles=angles,
        transverse=wind_live.transverse,
        longitudinal=wind_live.longitudinal,
        wl_cases_df=wl_cases_df,
    )
    if components_df.empty:
        return [], False

    return build_plans_for_groups(
        groups=deck_groups,
        group_members=group_members,
        dbg=dbg,
        label_prefix="WL_",
        dump_components=False,  # WL components same for all groups; dump once elsewhere if needed
        build_components_for_group=lambda _g: components_df,
        build_plan_for_group=lambda g, comp, eids: build_wl_beam_load_plan_for_group(
            group_name=g,
            components_df=comp,
            element_ids=eids,
            eccentricity=6.0,
            elements_in_model=elements_in_model,
            nodes_in_model=nodes_in_model,
        ),
    )


__all__ = [
    "build_wl_case_components_from_control_data",
    "build_wl_beam_load_plan_for_group",
    "apply_wl_beam_loads_to_group",
    "build_wl_beam_load_plans_for_deck_groups",
]
