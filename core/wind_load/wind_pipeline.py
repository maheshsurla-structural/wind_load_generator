# core/wind_load/wind_pipeline.py
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Tuple
import pandas as pd


from core.wind_load.debug import summarize_plan
from core.wind_load.beam_load import apply_beam_load_plan_to_midas

from core.wind_load.live_wind_loads import build_wl_beam_load_plans_for_deck_groups
from core.wind_load.structural_wind_loads import build_structural_wind_plans_for_deck_groups
from core.wind_load.substructure_wind_loads import build_substructure_wind_plans_for_groups

from core.wind_load.wind_common import normalize_and_validate_cases_df, combine_plans


# ---------------------------------------------------------------------------
# Geometry + group helpers
# ---------------------------------------------------------------------------

def get_midas_geometry() -> tuple[dict, dict]:
    """Safely fetch MIDAS model geometry."""
    try:
        from midas import elements as midas_elements, nodes as midas_nodes
        return (midas_elements.get() or {}), (midas_nodes.get() or {})
    except Exception:
        return {}, {}


def get_structural_groups_df(wind_db: Any) -> pd.DataFrame:
    groups_raw = getattr(wind_db, "structural_groups", None)
    if groups_raw is None:
        raise ValueError("No structural groups found in wind database.")

    if isinstance(groups_raw, dict):
        rows: list[dict] = []
        for name, params in groups_raw.items():
            row = {"Group": name}
            row.update(params or {})
            rows.append(row)
        df = pd.DataFrame(rows)
    elif isinstance(groups_raw, pd.DataFrame):
        df = groups_raw
    else:
        raise TypeError("wind_db.structural_groups must be a dict or DataFrame.")

    if df is None or df.empty:
        raise ValueError("No structural groups found in wind database.")
    if "Group" not in df.columns:
        raise ValueError("structural_groups must contain a 'Group' column.")

    if "Member Type" not in df.columns:
        df = df.copy()
        df["Member Type"] = "Deck"

    return df


def split_groups(groups_df: pd.DataFrame) -> tuple[list[str], list[str]]:
    deck = (
        groups_df.loc[groups_df["Member Type"] == "Deck", "Group"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    sub = (
        groups_df.loc[
            groups_df["Member Type"].isin(["Pier", "Substructure – Above Deck"]),
            "Group",
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    return deck, sub


def get_case_tables_and_ws_flag(wind_db: Any) -> tuple[pd.DataFrame, pd.DataFrame, bool]:
    wl_df = getattr(wind_db, "wl_cases", None)
    if wl_df is None:
        wl_df = pd.DataFrame()

    raw_ws_df = getattr(wind_db, "ws_cases", None)
    if raw_ws_df is None:
        raw_ws_df = pd.DataFrame()

    # normalize schema: if not present, make empty with proper columns
    if {"Case", "Angle", "Value"}.issubset(raw_ws_df.columns):
        ws_df = raw_ws_df
    else:
        ws_df = pd.DataFrame(columns=["Case", "Angle", "Value"])

    wind_pressures = getattr(wind_db, "wind_pressures", None)
    allow_ws = isinstance(wind_pressures, pd.DataFrame) and (not wind_pressures.empty)

    return wl_df, ws_df, allow_ws


# ---------------------------------------------------------------------------
# Registry-based planner runner
# ---------------------------------------------------------------------------

PlanBuilder = Callable[[], tuple[list[pd.DataFrame], bool]]


def build_all_wind_plans(
    *,
    deck_groups: list[str],
    sub_groups: list[str],
    skew: Any,
    wl_df: pd.DataFrame,
    ws_df: pd.DataFrame,
    wind_pressures_df: pd.DataFrame,
    group_members: dict,
    elements_in_model: dict,
    nodes_in_model: dict,
    wind_live: Any,
    dbg=None,
    allow_ws: bool,
) -> tuple[list[pd.DataFrame], dict]:
    """
    Runs a registry of plan builders and merges results.

    Returns:
      (all_plans, flags)
        flags = {"wl": bool, "ws_deck": bool, "ws_sub": bool}
    """
    flags: dict[str, bool] = {"wl": False, "ws_deck": False, "ws_sub": False}
    all_plans: list[pd.DataFrame] = []

    # normalize case tables once (centralized)
    if wl_df is None:
        wl_df = pd.DataFrame()
    if ws_df is None:
        ws_df = pd.DataFrame(columns=["Case", "Angle", "Value"])

    # If ws_df has data, validate now so errors are not “per group”
    if not ws_df.empty:
        ws_df = normalize_and_validate_cases_df(ws_df, df_name="ws_cases_df")

    planners: list[tuple[str, bool, PlanBuilder]] = [
        (
            "wl",
            True,
            lambda: build_wl_beam_load_plans_for_deck_groups(
                deck_groups=deck_groups,
                wind_live=wind_live,
                wl_cases_df=wl_df,
                group_members=group_members,
                elements_in_model=elements_in_model,
                nodes_in_model=nodes_in_model,
                dbg=dbg,
            ),
        ),
        (
            "ws_deck",
            bool(allow_ws),
            lambda: build_structural_wind_plans_for_deck_groups(
                deck_groups=deck_groups,
                skew=skew,
                ws_cases_df=ws_df,
                wind_pressures_df=wind_pressures_df,
                group_members=group_members,
                elements_in_model=elements_in_model,
                nodes_in_model=nodes_in_model,
                dbg=dbg,
            ),
        ),
        (
            "ws_sub",
            bool(allow_ws),
            lambda: build_substructure_wind_plans_for_groups(
                sub_groups=sub_groups,
                ws_cases_df=ws_df,
                wind_pressures_df=wind_pressures_df,
                group_members=group_members,
                elements_in_model=elements_in_model,
                nodes_in_model=nodes_in_model,
                dbg=dbg,
                extra_exposure_y_default=0.0,
                extra_exposure_y_by_id=None,
            ),
        ),
    ]

    for key, enabled, fn in planners:
        if not enabled:
            flags[key] = False
            continue

        plans, any_applied = fn()
        flags[key] = bool(any_applied)

        if plans:
            all_plans.extend(plans)

    return all_plans, flags



def apply_plans_to_midas(
    all_plans,
    *,
    dbg=None,
    debug_enabled: bool = False,
    max_items_per_put: int = 6000,
    replace_existing_for_plan_load_cases: bool = True,
) -> None:
    """
    Apply ALL wind load plans to MIDAS in ONE apply call.

    Benefits:
      - only one /db/bmld read
      - fewer PUT requests overall
      - still safe: only replaces load cases present in the combined plan
      - chunks PUT payloads by total ITEMS <= max_items_per_put (never splits an element)

    Parameters
    ----------
    all_plans : list[pd.DataFrame]
        Plans returned by build_all_wind_plans()
    dbg : DebugSink | None
        Debug sink
    debug_enabled : bool
        If True, pass dbg into the apply function
    max_items_per_put : int
        Upper bound on total ITEMS sent per PUT request (Option B)
    replace_existing_for_plan_load_cases : bool
        If True, removes existing ITEMS whose LCNAME is in the combined plan load cases
    """
    plans = [p for p in (all_plans or []) if p is not None and not p.empty]
    if not plans:
        print("[apply_plans_to_midas] No plans to apply.")
        return

    combined = pd.concat(plans, ignore_index=True)

    print(
        f"[apply_plans_to_midas] Applying combined plan: "
        f"{len(combined)} rows, {combined['element_id'].nunique()} elements, "
        f"{combined['load_case'].nunique()} load cases"
    )

    apply_beam_load_plan_to_midas(
        combined,
        max_items_per_put=max_items_per_put,
        debug=dbg if debug_enabled else None,
        debug_label="ALL_WIND",
        replace_existing_for_plan_load_cases=replace_existing_for_plan_load_cases,
    )



def status_message(flags: dict) -> str:
    wl = bool(flags.get("wl", False))
    ws = bool(flags.get("ws_deck", False)) or bool(flags.get("ws_sub", False))

    if wl and ws:
        return "WL applied to deck groups; WS applied to deck and/or substructure groups."
    if wl:
        return "Live wind (WL) loads assigned to deck groups. WS was skipped."
    if ws:
        return "Structural wind (WS) loads assigned to deck and/or substructure groups."
    return "No wind loads were assigned (no WL/WS components)."
