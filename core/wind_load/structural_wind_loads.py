# core/wind_load/structural_wind_loads.py
from __future__ import annotations

from typing import Sequence, Dict, Iterable, Mapping, Tuple, List
import pandas as pd

from wind_database import wind_db

from core.wind_load.beam_load import apply_beam_load_plan_to_midas
from core.wind_load.groups import get_structural_group_element_ids

from core.wind_load.wind_common import (
    parse_quadrant_from_load_case_name,
    apply_quadrant_sign_convention,
    normalize_and_validate_cases_df,
    coeffs_by_angle,
    build_pressure_plan_from_components,
)

from core.wind_load.groups import build_plans_for_groups


# ---------------------------------------------------------------------------
# 1) Build WS components (deck structural wind)
# ---------------------------------------------------------------------------

def build_structural_wind_components_table(
    *,
    wind_pressures_df: pd.DataFrame | None = None,
    group_name: str,
    angles: Sequence[int],
    transverse: Sequence[float],
    longitudinal: Sequence[float],
    ws_cases_df: pd.DataFrame,
) -> pd.DataFrame:
    cols_out = [
        "load_case",
        "load_group",
        "angle",
        "base_case",
        "Pz",
        "p_transverse",
        "p_longitudinal",
    ]

    if wind_pressures_df is None:
        wind_pressures_df = wind_db.wind_pressures

    if (
        ws_cases_df is None
        or ws_cases_df.empty
        or wind_pressures_df is None
        or wind_pressures_df.empty
    ):
        return pd.DataFrame(columns=cols_out)

    group_name = str(group_name or "").strip()
    if not group_name:
        return pd.DataFrame(columns=cols_out)

    ws_cases_df = normalize_and_validate_cases_df(ws_cases_df, df_name="ws_cases_df")

    angle_to_coeffs = coeffs_by_angle(
        angles=angles,
        transverse=transverse,
        longitudinal=longitudinal,
        table_name="skew",
    )

    needed_p = {"Group", "Load Case", "Pz (ksf)"}
    if missing := needed_p - set(wind_pressures_df.columns):
        raise ValueError(f"wind_pressures_df missing columns: {missing}")

    # Pressure lookup for this group
    pz = wind_pressures_df.loc[
        wind_pressures_df["Group"] == group_name,
        ["Load Case", "Pz (ksf)"],
    ].copy()
    pz.rename(columns={"Load Case": "base_case", "Pz (ksf)": "Pz"}, inplace=True)
    pz = pz.drop_duplicates(subset=["base_case"], keep="first")

    if pz.empty:
        return pd.DataFrame(columns=cols_out)

    p_by_base = {str(r["base_case"]).strip(): float(r["Pz"]) for _, r in pz.iterrows()}

    rows: list[dict] = []
    for _, r in ws_cases_df.iterrows():
        base_case = str(r["Case"]).strip()
        ang = int(r["Angle"])
        lcname = str(r["Value"]).strip()
        if not base_case or not lcname:
            continue

        Pz_val = p_by_base.get(base_case)
        if Pz_val is None:
            continue

        coeff = angle_to_coeffs.get(ang)
        if coeff is None:
            continue

        base_t, base_l = coeff
        q = parse_quadrant_from_load_case_name(lcname)
        t, l = apply_quadrant_sign_convention(q, base_t, base_l)

        rows.append(
            {
                "load_case": lcname,
                "load_group": lcname,
                "angle": ang,
                "base_case": base_case,
                "Pz": float(Pz_val),
                "p_transverse": float(Pz_val) * float(t),
                "p_longitudinal": float(Pz_val) * float(l),
            }
        )

    out = pd.DataFrame(rows, columns=cols_out)
    if not out.empty:
        out.sort_values(["angle", "load_case"], inplace=True)
        out.reset_index(drop=True, inplace=True)
    return out


# ---------------------------------------------------------------------------
# 2) Build WS beam-load plan using shared common builder
# ---------------------------------------------------------------------------

def build_structural_wind_beam_load_plan_for_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    exposure_axis: str = "y",
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
    element_ids: list[int] | None = None,
    elements_in_model=None,
    nodes_in_model=None,
) -> pd.DataFrame:
    if components_df is None or components_df.empty:
        return pd.DataFrame()


    if element_ids is None:
        eids = get_structural_group_element_ids(group_name)
    else:
        eids = [int(e) for e in element_ids]

    if not eids:
        return pd.DataFrame()

    axis = "z" if str(exposure_axis).lower() == "z" else "y"

    return build_pressure_plan_from_components(
        group_name=group_name,
        components_df=components_df,
        component_map={
            "p_transverse": ("LY", axis),
            "p_longitudinal": ("LX", axis),
        },
        element_ids=eids,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
    )


# ---------------------------------------------------------------------------
# 3) Apply wrapper
# ---------------------------------------------------------------------------

def apply_structural_wind_loads_to_group(
    group_name: str,
    components_df: pd.DataFrame,
    *,
    exposure_axis: str = "y",
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
    dbg=None,
    print_summary: bool = False,
) -> None:
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

    # ✅ No summarize_plan() (per your request: only final apply JSON)
    apply_beam_load_plan_to_midas(combined_plan, debug=dbg, debug_label=f"WS_{group_name}")



# ---------------------------------------------------------------------------
# 4) Build plans for multiple deck groups (WS deck only)
# ---------------------------------------------------------------------------

def build_structural_wind_plans_for_deck_groups(
    *,
    deck_groups: Iterable[str],
    skew,
    ws_cases_df: pd.DataFrame,
    wind_pressures_df: pd.DataFrame,
    group_members: Mapping[str, list[int]] | None = None,
    elements_in_model: dict | None = None,
    nodes_in_model: dict | None = None,
    dbg=None,
) -> Tuple[List[pd.DataFrame], bool]:
    if ws_cases_df is None or ws_cases_df.empty:
        return [], False

    ws_cases_df = normalize_and_validate_cases_df(ws_cases_df, df_name="ws_cases_df")

    def _components_for_group(g: str) -> pd.DataFrame:
        return build_structural_wind_components_table(
            group_name=g,
            angles=skew.angles,
            transverse=skew.transverse,
            longitudinal=skew.longitudinal,
            ws_cases_df=ws_cases_df,
            wind_pressures_df=wind_pressures_df,
        )

    def _plan_for_group(g: str, comp: pd.DataFrame, eids: list[int] | None) -> pd.DataFrame:
        return build_structural_wind_beam_load_plan_for_group(
            group_name=g,
            components_df=comp,
            exposure_axis="y",
            element_ids=eids,
            elements_in_model=elements_in_model,
            nodes_in_model=nodes_in_model,
        )

    return build_plans_for_groups(
        groups=deck_groups,
        group_members=group_members,
        dbg=dbg,
        label_prefix="WS_DECK_",
        dump_components=True,
        build_components_for_group=_components_for_group,
        build_plan_for_group=_plan_for_group,
    )


__all__ = [
    "build_structural_wind_components_table",
    "build_structural_wind_beam_load_plan_for_group",
    "apply_structural_wind_loads_to_group",
    "build_structural_wind_plans_for_deck_groups",
]
