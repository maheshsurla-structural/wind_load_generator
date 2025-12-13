# core/wind_load/wind_pipeline.py
from __future__ import annotations

from typing import Any
import pandas as pd

from core.wind_load.debug_utils import summarize_plan
from core.wind_load.beam_load import apply_beam_load_plan_to_midas

from core.wind_load.live_wind_loads import build_live_wind_plans_for_deck_groups
from core.wind_load.structural_wind_loads import build_structural_wind_plans_for_deck_groups
from core.wind_load.substructure_wind_loads import build_substructure_wind_plans_for_groups


def get_midas_geometry() -> tuple[dict, dict]:
    """
    Safely fetch MIDAS model geometry.

    Returns
    -------
    (elements_in_model, nodes_in_model)
        Both are dicts. If MIDAS is unavailable, returns ({}, {}).
    """
    try:
        from midas import elements as midas_elements, nodes as midas_nodes
        return (midas_elements.get() or {}), (midas_nodes.get() or {})
    except Exception:
        return {}, {}


def get_structural_groups_df(wind_db: Any) -> pd.DataFrame:
    """
    Normalize wind_db.structural_groups into a DataFrame that contains:
      - 'Group'
      - 'Member Type' (defaulted to 'Deck' if missing)

    Supports structural_groups being a dict[str, dict] or a pandas DataFrame.
    """
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
    """
    Split structural groups into (deck_groups, substructure_groups) based on 'Member Type'.
    """
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
    """
    Returns
    -------
    (wl_df, ws_df, allow_ws)

    wl_df:
        wind_db.wl_cases if present, else empty DataFrame.
    ws_df:
        wind_db.ws_cases if present AND has columns {'Case','Angle','Value'}, else empty
        DataFrame with those columns.
    allow_ws:
        True only if wind_db.wind_pressures exists and is a non-empty DataFrame.
    """
    wl_df = getattr(wind_db, "wl_cases", None)
    if wl_df is None:
        wl_df = pd.DataFrame()

    raw_ws_df = getattr(wind_db, "ws_cases", None)
    if raw_ws_df is None:
        raw_ws_df = pd.DataFrame()

    if {"Case", "Angle", "Value"}.issubset(raw_ws_df.columns):
        ws_df = raw_ws_df
    else:
        ws_df = pd.DataFrame(columns=["Case", "Angle", "Value"])

    wind_pressures = getattr(wind_db, "wind_pressures", None)
    allow_ws = isinstance(wind_pressures, pd.DataFrame) and (not wind_pressures.empty)

    return wl_df, ws_df, allow_ws


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
    Build WL plans for deck groups and, if allow_ws is True, WS plans for deck + substructure.

    Returns
    -------
    (all_plans, flags)
      all_plans: list of DataFrames (each a beam load plan chunk)
      flags: dict with keys {'wl','ws_deck','ws_sub'} indicating what was built
    """
    flags = {"wl": False, "ws_deck": False, "ws_sub": False}
    all_plans: list[pd.DataFrame] = []

    # --- WL (live wind) for deck groups ---
    wl_plans, flags["wl"] = build_live_wind_plans_for_deck_groups(
        deck_groups=deck_groups,
        wind_live=wind_live,
        wl_cases_df=wl_df,
        group_members=group_members,
        elements_in_model=elements_in_model,
        nodes_in_model=nodes_in_model,
        dbg=dbg,
    )
    all_plans.extend(wl_plans)

    # --- WS (structural wind) for deck + substructure ---
    if allow_ws:
        ws_deck_plans, flags["ws_deck"] = build_structural_wind_plans_for_deck_groups(
            deck_groups=deck_groups,
            skew=skew,
            ws_cases_df=ws_df,
            wind_pressures_df=wind_pressures_df,
            group_members=group_members,
            elements_in_model=elements_in_model,
            nodes_in_model=nodes_in_model,
            dbg=dbg,
        )
        all_plans.extend(ws_deck_plans)

        ws_sub_plans, flags["ws_sub"] = build_substructure_wind_plans_for_groups(
            sub_groups=sub_groups,
            ws_cases_df=ws_df,
            wind_pressures_df=wind_pressures_df,
            group_members=group_members,
            elements_in_model=elements_in_model,
            nodes_in_model=nodes_in_model,
            dbg=dbg,
            extra_exposure_y_default=0.0,
            extra_exposure_y_by_id=None,
        )
        all_plans.extend(ws_sub_plans)

    return all_plans, flags


def apply_plans_to_midas(
    all_plans: list[pd.DataFrame],
    dbg=None,
    debug_enabled: bool = False,
) -> None:
    """
    Concatenate all plan chunks, sort for stable application, optionally summarize, then apply to MIDAS.
    """
    if not all_plans:
        return

    combined = pd.concat(all_plans, ignore_index=True)
    combined.sort_values(["load_case", "element_id"], inplace=True)
    combined.reset_index(drop=True, inplace=True)

    if debug_enabled:
        summarize_plan(
            combined,
            label="ALL_WIND",
            dump_csv_per_case=False,
            write_log=True,
            print_summary=False,
        )

    apply_beam_load_plan_to_midas(combined, debug=dbg, debug_label="ALL_WIND")


def status_message(flags: dict) -> str:
    """
    Human-friendly message describing which load types were applied.
    """
    wl = flags.get("wl", False)
    ws = flags.get("ws_deck", False) or flags.get("ws_sub", False)

    if wl and ws:
        return "WL applied to deck groups; WS applied to deck and/or substructure groups."
    if wl:
        return "Live wind (WL) loads assigned to deck groups. WS was skipped."
    if ws:
        return "Structural wind (WS) loads assigned to deck and/or substructure groups."
    return "No wind loads were assigned (no WL/WS components)."
