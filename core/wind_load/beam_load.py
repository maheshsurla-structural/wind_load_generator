# core/wind_load/beam_load.py

"""
Build and apply wind beam line-loads to MIDAS.

This module provides two main steps:

1) Build "plan" DataFrames (pure data, no MIDAS write)
2) Apply a plan to MIDAS (/db/bmld)

Key implementation detail:
- /db/bmld stores loads per ELEMENT under ITEMS[].
- When writing, we *merge existing ITEMS + new ITEMS* per element to avoid accidental overwrites.
- IDs can be assigned:
    a) globally (start_id provided), or
    b) per-element (default when start_id is None).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence, Dict, List, Any, Tuple
from collections import defaultdict
import numpy as np
import pandas as pd

# MIDAS API: model data + beam load resource
from midas import elements, get_section_properties
from midas.resources.element_beam_load import BeamLoadItem, BeamLoadResource

# Project helpers: debug + group->elements resolution
from core.wind_load.debug import DebugSink
from core.wind_load.groups import get_group_element_ids


# =============================================================================
# Section exposure helper
# =============================================================================

def compute_section_exposures(
    section_properties,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: dict | None = None,
    as_dataframe: bool = True,
) -> pd.DataFrame | dict:
    """
    Compute local Y and Z exposure depths for all section properties.

    Parameters
    ----------
    section_properties : list
        List of section property data rows (e.g., from MIDAS export).
    extra_exposure_y_default : float, optional
        Default additional exposure to add in the local Y direction.
    extra_exposure_y_by_id : dict, optional
        Optional mapping {property_id: extra_exposure_y} for per-section overrides.
    as_dataframe : bool, optional
        If True, returns a pandas DataFrame indexed by property_id;
        if False, returns a dictionary {property_id: (exposure_y, exposure_z)}.

    Returns
    -------
    pandas.DataFrame | dict
        Exposure data for all sections.
    """
    # Column indices in the MIDAS section property table
    COL_ID, COL_LEFT, COL_RIGHT, COL_TOP, COL_BOTTOM = 1, 11, 12, 13, 14

    property_ids, left_vals, right_vals, top_vals, bottom_vals = [], [], [], [], []

    for row in section_properties or []:
        if len(row) <= COL_BOTTOM:
            continue
        try:
            property_ids.append(row[COL_ID])
            left_vals.append(float(row[COL_LEFT]))
            right_vals.append(float(row[COL_RIGHT]))
            top_vals.append(float(row[COL_TOP]))
            bottom_vals.append(float(row[COL_BOTTOM]))
        except (TypeError, ValueError):
            continue

    if not property_ids:
        return pd.DataFrame(columns=["exposure_y", "exposure_z"]) if as_dataframe else {}

    # Convert to numpy arrays
    property_ids = np.asarray(property_ids, dtype=object)
    left_vals = np.asarray(left_vals, dtype=float)
    right_vals = np.asarray(right_vals, dtype=float)
    top_vals = np.asarray(top_vals, dtype=float)
    bottom_vals = np.asarray(bottom_vals, dtype=float)

    # Apply extra exposure (per-property or global)
    if extra_exposure_y_by_id:
        extra_y = np.fromiter(
            (extra_exposure_y_by_id.get(pid, extra_exposure_y_default) for pid in property_ids),
            dtype=float,
            count=property_ids.size,
        )
    else:
        extra_y = np.full(property_ids.size, extra_exposure_y_default, dtype=float)

    # Compute exposures
    exposure_y = top_vals + bottom_vals + extra_y
    exposure_z = left_vals + right_vals

    if as_dataframe:
        df = pd.DataFrame(
            {"exposure_y": exposure_y, "exposure_z": exposure_z},
            index=property_ids,
        )
        df.index.name = "property_id"
        return df

    return {property_ids[i]: (exposure_y[i], exposure_z[i]) for i in range(property_ids.size)}


# =============================================================================
# Cached MIDAS reads
# =============================================================================

@lru_cache(maxsize=1)
def _get_all_elements_cached() -> dict:
    """
    Cached snapshot of /db/ELEM for this Python process.
    Avoids repeated elements.get_all() calls.
    """
    return elements.get_all() or {}


@lru_cache(maxsize=1)
def get_section_properties_cached():
    """
    Cached wrapper around midas.get_section_properties().
    All callers share a single MIDAS /db/SECT read.
    """
    return get_section_properties()


# =============================================================================
# Beam load ID + element->section helpers
# =============================================================================

def _next_id_by_element_from_raw(raw: Dict[str, Any]) -> Dict[int, int]:
    """Per-element next ID map from raw /db/bmld: {eid: max(ID)+1}."""
    out: Dict[int, int] = {}
    for elem_id_str, elem_block in (raw or {}).items():
        try:
            eid = int(elem_id_str)
        except (TypeError, ValueError):
            continue

        items = (elem_block or {}).get("ITEMS", []) or []
        max_id = 0
        for it in items:
            try:
                max_id = max(max_id, int(it.get("ID", 0)))
            except (TypeError, ValueError):
                continue

        out[eid] = (max_id + 1) if max_id > 0 else 1
    return out


def _get_element_to_section_map(element_ids: List[int]) -> Dict[int, int]:
    """
    Return {element_id: section_id} for each element in element_ids.
    Uses /db/ELEM via midas.elements.get_all() (cached).
    """
    out: Dict[int, int] = {}
    all_elem_data = _get_all_elements_cached()

    for eid in element_ids:
        edata = all_elem_data.get(str(eid))
        if not edata:
            continue

        sect_id = edata.get("SECT")  # adjust if your key differs
        if sect_id is None:
            continue

        try:
            out[int(eid)] = int(sect_id)
        except (TypeError, ValueError):
            continue

    return out


# =============================================================================
# STEP 1: Build plan DataFrames (no MIDAS write)
# =============================================================================

def build_uniform_pressure_beam_load_plan_from_depths(
    *,
    group_name: str,
    load_case_name: str,
    pressure: float,
    udl_direction: str,
    depth_by_eid: Dict[int, float],
    load_group_name: str | None = None,
) -> pd.DataFrame:
    """
    Given pressure (ksf) and per-element exposure depth (ft),
    produce a plan with line_load = pressure * depth (k/ft).
    """
    rows: list[dict] = []

    for eid, depth in depth_by_eid.items():
        q = pressure * depth  # ksf * ft = k/ft
        if abs(q) < 1e-9:
            continue

        rows.append(
            {
                "element_id": int(eid),
                "line_load": float(q),
                "load_case": load_case_name,
                "load_direction": udl_direction,
                "load_group": load_group_name or load_case_name,
                "group_name": group_name,
            }
        )

    plan_df = pd.DataFrame(rows)
    if not plan_df.empty:
        plan_df.sort_values("element_id", inplace=True)
        plan_df.reset_index(drop=True, inplace=True)
    return plan_df


def build_uniform_pressure_beam_load_plan_for_group(
    group_name: str,
    load_case_name: str,
    pressure: float,
    *,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
    exposure_axis: str = "y",
    udl_direction: str = "GZ",
    load_group_name: str = "",
) -> pd.DataFrame:
    """
    High-level helper: resolve elements, sections, exposures from MIDAS
    then call build_uniform_pressure_beam_load_plan_from_depths().
    """
    element_ids = get_group_element_ids(group_name)
    elem_to_sect = _get_element_to_section_map(list(element_ids))

    section_props_raw = get_section_properties_cached()
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

    depth_col = "exposure_z" if exposure_axis.lower() == "z" else "exposure_y"

    depth_by_eid: Dict[int, float] = {}
    for eid, sect_id in elem_to_sect.items():
        if sect_id in exposures_df.index:
            depth_by_eid[int(eid)] = float(exposures_df.loc[sect_id, depth_col])

    return build_uniform_pressure_beam_load_plan_from_depths(
        group_name=group_name,
        load_case_name=load_case_name,
        pressure=pressure,
        udl_direction=udl_direction,
        depth_by_eid=depth_by_eid,
        load_group_name=load_group_name or load_case_name,
    )


def build_uniform_load_beam_load_plan_for_group(
    *,
    group_name: str,
    load_case_name: str,
    line_load: float,
    udl_direction: str,
    load_group_name: str | None = None,
    element_ids: Sequence[int] | None = None,
    eccentricity: float = 0.0,
) -> pd.DataFrame:
    """
    Build a plan where line_load is already k/ft for all elements.
    """
    if element_ids is None:
        element_ids = get_group_element_ids(group_name)

    element_ids = [int(e) for e in element_ids]

    rows: list[dict] = []
    for eid in element_ids:
        rows.append(
            {
                "element_id": int(eid),
                "line_load": float(line_load),
                "load_case": load_case_name,
                "load_direction": udl_direction,
                "load_group": load_group_name or load_case_name,
                "group_name": group_name,
                "eccentricity": float(eccentricity),
            }
        )

    plan_df = pd.DataFrame(rows)
    if not plan_df.empty:
        plan_df.sort_values("element_id", inplace=True)
        plan_df.reset_index(drop=True, inplace=True)
    return plan_df


# =============================================================================
# STEP 2: Apply plan to MIDAS (safe merge-per-element write)
# =============================================================================

def apply_beam_load_plan_to_midas(
    plan_df: pd.DataFrame,
    *,
    max_items_per_put: int = 5000,   # Option B: limit total ITEMS per request
    debug: DebugSink | None = None,
    debug_label: str = "ALL_WIND",
    replace_existing_for_plan_load_cases: bool = True,
    aggregate_duplicates: bool = True,
) -> pd.DataFrame:
    """
    Structured + safe apply:

    1) Read existing /db/bmld once
    2) Build per-element next ID map once (MIDAS IDs are unique within element)
    3) Iterate the plan in load-case order (easy to reason about)
       - allocate IDs per element
       - build BeamLoadItem objects
       - store as new_by_eid[eid] (element -> list[BeamLoadItem])
    4) Merge per element once (optional safe replace for only plan cases)
    5) PUT in batches of elements, limiting sum(ITEMS) <= max_items_per_put
       - never splits an element across PUTs
       - an element is sent at most once per run

    Parameters
    ----------
    plan_df : pd.DataFrame
        Required cols: element_id, line_load, load_case, load_direction, load_group
        Optional: eccentricity
    max_items_per_put : int
        Upper bound on total ITEM records in a single PUT request.
    replace_existing_for_plan_load_cases : bool
        If True, remove existing items whose LCNAME is in the plan's load cases.
    aggregate_duplicates : bool
        If True, combines duplicate rows by summing line_load for identical
        (element_id, load_case, load_direction, load_group, eccentricity).

    Returns
    -------
    pd.DataFrame
        The (sorted/possibly-aggregated) plan_df actually applied.
    """
    if plan_df is None or plan_df.empty:
        print("[apply_beam_load_plan_to_midas] plan_df is empty; nothing to send.")
        return plan_df

    required = {"element_id", "line_load", "load_case", "load_direction", "load_group"}
    missing = required - set(plan_df.columns)
    if missing:
        raise ValueError(f"plan_df missing required columns: {sorted(missing)}")

    max_items_per_put = max(int(max_items_per_put), 1)

    # -----------------------------
    # 0) Normalize + (optional) aggregate duplicates
    # -----------------------------
    df = plan_df.copy()

    # normalize strings early
    df["load_case"] = df["load_case"].astype(str).str.strip()
    df["load_direction"] = df["load_direction"].astype(str).str.strip()
    df["load_group"] = df["load_group"].astype(str).str.strip()

    if "eccentricity" not in df.columns:
        df["eccentricity"] = 0.0
    df["eccentricity"] = pd.to_numeric(df["eccentricity"], errors="coerce").fillna(0.0)

    df["element_id"] = pd.to_numeric(df["element_id"], errors="coerce")
    df["line_load"] = pd.to_numeric(df["line_load"], errors="coerce")

    df = df.dropna(subset=["element_id", "line_load"])
    df["element_id"] = df["element_id"].astype(int)

    if aggregate_duplicates:
        key_cols = ["element_id", "load_case", "load_direction", "load_group", "eccentricity"]
        df = (
            df.groupby(key_cols, as_index=False, sort=False)["line_load"]
            .sum()
        )

    # stable ordering for "case-by-case" building
    df = df.sort_values(
        ["load_case", "load_direction", "element_id"],
        kind="stable",
    ).reset_index(drop=True)

    if debug and debug.enabled:
        debug.dump_plan(df, label=debug_label, split_per_case=True)

    # -----------------------------
    # 1) Read existing /db/bmld once
    # -----------------------------
    raw_existing = BeamLoadResource.get_raw() or {}

    existing_items_by_eid: Dict[int, List[Dict[str, Any]]] = {}
    for eid_str, elem_block in (raw_existing or {}).items():
        try:
            eid = int(eid_str)
        except (TypeError, ValueError):
            continue
        existing_items_by_eid[eid] = list(((elem_block or {}).get("ITEMS", []) or []))

    # -----------------------------
    # 2) Build per-element next-id map once (YOUR helper)
    # -----------------------------
    next_id_by_eid = _next_id_by_element_from_raw(raw_existing)

    def alloc_id(eid: int) -> int:
        nxt = next_id_by_eid.get(eid, 1)
        next_id_by_eid[eid] = nxt + 1
        return nxt

    # For safe replace: all load cases present in this plan
    plan_cases = set(df["load_case"].astype(str).str.strip())

    # -----------------------------
    # 3) Build NEW items in load-case order, but store grouped by element
    # -----------------------------
    new_by_eid: Dict[int, List[BeamLoadItem]] = defaultdict(list)

    # Build items case-by-case (your preferred mental model)
    for lcname, lc_df in df.groupby("load_case", sort=False):
        lcname = str(lcname).strip()
        if not lcname:
            continue

        for row in lc_df.itertuples(index=False):
            eid = int(getattr(row, "element_id"))
            q = float(getattr(row, "line_load"))
            if abs(q) < 1e-9:
                continue

            direction = str(getattr(row, "load_direction"))
            ldgr = str(getattr(row, "load_group"))

            ecc = float(getattr(row, "eccentricity", 0.0))
            use_ecc = abs(ecc) > 1e-9

            item = BeamLoadItem(
                ID=alloc_id(eid),          # ✅ per-element ID allocation
                LCNAME=lcname,
                GROUP_NAME=ldgr,
                CMD="BEAM",
                TYPE="UNILOAD",
                DIRECTION=direction,
                USE_PROJECTION=False,
                USE_ECCEN=use_ecc,
                D=[0, 1, 0, 0],
                P=[q, q, 0, 0],
                ECCEN_TYPE=1,
                ECCEN_DIR="GZ",
                I_END=ecc,
                J_END=ecc,
            )
            new_by_eid[eid].append(item)

    if not new_by_eid:
        print("[apply_beam_load_plan_to_midas] All loads ~0; nothing to send.")
        return df

    touched_eids = sorted(new_by_eid.keys())

    # -----------------------------
    # 4) Merge per element ONCE (optional safe replace)
    # -----------------------------
    merged_items_by_eid: Dict[int, List[Dict[str, Any]]] = {}
    merged_size_by_eid: Dict[int, int] = {}

    for eid in touched_eids:
        existing = existing_items_by_eid.get(eid, [])

        if replace_existing_for_plan_load_cases and plan_cases:
            existing = [
                it for it in existing
                if str(it.get("LCNAME", "")).strip() not in plan_cases
            ]

        merged = list(existing)
        merged.extend(it.to_dict() for it in new_by_eid[eid])

        merged_items_by_eid[eid] = merged
        merged_size_by_eid[eid] = len(merged)

    # -----------------------------
    # 5) PUT in batches of elements such that sum(ITEMS) <= max_items_per_put
    #    Never split an element across PUTs.
    # -----------------------------
    sent_new = 0
    req = 0
    idx = 0

    while idx < len(touched_eids):
        batch: List[int] = []
        batch_items = 0

        while idx < len(touched_eids):
            eid = touched_eids[idx]
            elem_items = merged_size_by_eid[eid]

            # If single element exceeds limit, still send it alone
            if not batch and elem_items > max_items_per_put:
                batch = [eid]
                batch_items = elem_items
                idx += 1
                break

            # If adding would exceed limit, stop here
            if batch and (batch_items + elem_items > max_items_per_put):
                break

            batch.append(eid)
            batch_items += elem_items
            idx += 1

        assign = {str(eid): {"ITEMS": merged_items_by_eid[eid]} for eid in batch}

        req += 1
        new_count = sum(len(new_by_eid[eid]) for eid in batch)
        print(
            f"[apply_beam_load_plan_to_midas] PUT {req}: "
            f"{len(batch)} elements, {batch_items} ITEMS, {new_count} NEW (limit={max_items_per_put})"
        )

        if debug and debug.enabled:
            batch_specs: List[Tuple[int, BeamLoadItem]] = []
            for eid in batch:
                batch_specs.extend((eid, it) for it in new_by_eid[eid])

            debug.dump_chunk_specs(
                batch_specs,
                label=debug_label,
                chunk_index=req,
                reason=f"element-batched items<= {max_items_per_put}",
            )

        BeamLoadResource.put_raw({"Assign": assign})

        sent_new += new_count

    print(f"[apply_beam_load_plan_to_midas] Done. Sent {sent_new} new beam load items.")
    return df


__all__ = [
    "compute_section_exposures",
    "get_section_properties_cached",
    "_get_element_to_section_map",
    "build_uniform_pressure_beam_load_plan_from_depths",
    "build_uniform_pressure_beam_load_plan_for_group",
    "build_uniform_load_beam_load_plan_for_group",
    "apply_beam_load_plan_to_midas",
]
