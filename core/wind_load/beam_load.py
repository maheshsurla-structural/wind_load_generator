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
    max_items_per_put: int = 5000,   # Option B: cap total ITEMS per PUT
    debug: DebugSink | None = None,
    debug_label: str = "ALL_WIND",
    replace_existing_for_plan_load_cases: bool = True,
    dedupe_plan: bool = True,        # ✅ recommended if elements can overlap across groups
) -> pd.DataFrame:
    """
    Apply full plan to MIDAS using element-batched PUTs with a cap on total ITEMS.

    Guarantees:
      - An element is PUT at most once per run (never split across PUTs)
      - Request payload size is controlled by total ITEMS <= max_items_per_put (approx by count)
      - IDs are unique within each element (MIDAS behavior)
      - Optional "safe replace": only remove existing items whose LCNAME appears in this plan
      - Optional de-dupe: if the same (eid, case, dir, group, ecc) appears multiple times, sum line_load

    Required plan_df columns:
      element_id, line_load, load_case, load_direction, load_group
    Optional:
      eccentricity
    """
    if plan_df is None or plan_df.empty:
        print("[apply_beam_load_plan_to_midas] plan_df is empty; nothing to send.")
        return plan_df

    required = {"element_id", "line_load", "load_case", "load_direction", "load_group"}
    missing = required - set(plan_df.columns)
    if missing:
        raise ValueError(f"plan_df missing required columns: {sorted(missing)}")

    max_items_per_put = max(int(max_items_per_put), 1)

    # -------------------------
    # 0) Normalize + optional de-dupe
    # -------------------------
    df = plan_df.copy()

    # Ensure eccentricity column exists (and is numeric)
    if "eccentricity" not in df.columns:
        df["eccentricity"] = 0.0
    df["eccentricity"] = pd.to_numeric(df["eccentricity"], errors="coerce").fillna(0.0)

    # Normalize strings
    df["load_case"] = df["load_case"].astype(str).str.strip()
    df["load_direction"] = df["load_direction"].astype(str).str.strip()
    df["load_group"] = df["load_group"].astype(str).str.strip()

    # Make sure element_id + line_load are numeric
    df["element_id"] = pd.to_numeric(df["element_id"], errors="coerce")
    df["line_load"] = pd.to_numeric(df["line_load"], errors="coerce").fillna(0.0)

    # Drop invalid element_ids
    df = df[df["element_id"].notna()].copy()
    df["element_id"] = df["element_id"].astype(int)

    # Drop ~0 loads early
    EPS = 1e-9
    df = df[df["line_load"].abs() > EPS].copy()

    if df.empty:
        print("[apply_beam_load_plan_to_midas] All loads ~0; nothing to send.")
        return plan_df

    if dedupe_plan:
        # If the same element ends up with repeated rows (eg. overlapping groups),
        # sum line_load so MIDAS doesn't get duplicate ITEMS unintentionally.
        df = (
            df.groupby(
                ["element_id", "load_case", "load_direction", "load_group", "eccentricity"],
                as_index=False,
                sort=False,
            )["line_load"]
            .sum()
        )
        df = df[df["line_load"].abs() > EPS].copy()

        if df.empty:
            print("[apply_beam_load_plan_to_midas] All loads ~0 after dedupe; nothing to send.")
            return plan_df

    # Stable ordering (debug/repro)
    df = df.sort_values(["element_id", "load_case", "load_direction"], kind="stable").reset_index(drop=True)

    if debug and debug.enabled:
        # This splits per case in your DebugSink; harmless even though we send element-batched
        debug.dump_plan(df, label=debug_label, split_per_case=True)

    # ------------------------------------------------------------
    # 1) Read existing /db/bmld once
    # ------------------------------------------------------------
    raw_existing = BeamLoadResource.get_raw() or {}
    existing_items_by_eid: Dict[int, List[Dict[str, Any]]] = {}
    for eid_str, elem_block in raw_existing.items():
        try:
            eid = int(eid_str)
        except (TypeError, ValueError):
            continue
        existing_items_by_eid[eid] = list(((elem_block or {}).get("ITEMS", []) or []))

    # ------------------------------------------------------------
    # 2) Determine which load cases are in THIS plan (safe replace scope)
    # ------------------------------------------------------------
    plan_cases: set[str] = set(df["load_case"].astype(str).str.strip())

    # ------------------------------------------------------------
    # 3) Group PLAN rows by element (we'll create BeamLoadItems later)
    # ------------------------------------------------------------
    rows_by_eid: Dict[int, List[dict]] = defaultdict(list)
    for r in df.itertuples(index=False):
        rows_by_eid[int(r.element_id)].append(
            {
                "load_case": str(r.load_case).strip(),
                "load_group": str(r.load_group).strip(),
                "direction": str(r.load_direction).strip(),
                "line_load": float(r.line_load),
                "ecc": float(getattr(r, "eccentricity", 0.0) or 0.0),
            }
        )

    touched_eids = sorted(rows_by_eid.keys())
    if not touched_eids:
        print("[apply_beam_load_plan_to_midas] No touched elements; nothing to send.")
        return plan_df

    # ------------------------------------------------------------
    # Helper: next ID from an ITEMS list (after optional filtering!)
    # ------------------------------------------------------------
    def _next_id_from_items(items: List[Dict[str, Any]]) -> int:
        m = 0
        for it in items or []:
            try:
                m = max(m, int(it.get("ID", 0)))
            except (TypeError, ValueError):
                pass
        return (m + 1) if m > 0 else 1

    # ------------------------------------------------------------
    # 4) Pre-merge per element ONCE and compute merged ITEM counts
    #    - filter existing by plan cases (optional)
    #    - allocate IDs based on filtered existing (keeps IDs compact)
    # ------------------------------------------------------------
    merged_items_by_eid: Dict[int, List[Dict[str, Any]]] = {}
    merged_size_by_eid: Dict[int, int] = {}
    new_items_by_eid: Dict[int, List[BeamLoadItem]] = defaultdict(list)

    for eid in touched_eids:
        existing = list(existing_items_by_eid.get(eid, []) or [])

        if replace_existing_for_plan_load_cases and plan_cases:
            existing = [
                it for it in existing
                if str(it.get("LCNAME", "")).strip() not in plan_cases
            ]

        next_id = _next_id_from_items(existing)

        # Start merged list with kept existing
        merged = list(existing)

        # Append new items (assign IDs now)
        for row in rows_by_eid[eid]:
            q = float(row["line_load"])
            if abs(q) < EPS:
                continue

            lcname = row["load_case"]
            direction = row["direction"]
            ldgr = row["load_group"]

            ecc = float(row["ecc"])
            use_ecc = abs(ecc) > EPS

            item = BeamLoadItem(
                ID=next_id,
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
            next_id += 1

            new_items_by_eid[eid].append(item)
            merged.append(item.to_dict())

        if merged:
            merged_items_by_eid[eid] = merged
            merged_size_by_eid[eid] = len(merged)
        else:
            # If an element ends up with no items at all (unlikely), skip it
            merged_items_by_eid[eid] = []
            merged_size_by_eid[eid] = 0

    # Only keep elements that actually have something to PUT (merged items non-empty)
    touched_eids = [eid for eid in touched_eids if merged_size_by_eid.get(eid, 0) > 0]
    if not touched_eids:
        print("[apply_beam_load_plan_to_midas] No merged ITEMS to PUT; nothing to send.")
        return plan_df

    # ------------------------------------------------------------
    # 5) PUT in batches so sum(merged ITEMS) <= max_items_per_put
    #    IMPORTANT: never split an element across PUTs.
    # ------------------------------------------------------------
    sent_new = 0
    req = 0
    idx = 0

    while idx < len(touched_eids):
        batch: List[int] = []
        batch_items = 0

        while idx < len(touched_eids):
            eid = touched_eids[idx]
            elem_items = int(merged_size_by_eid[eid])

            # If one element alone exceeds limit, send it alone
            if not batch and elem_items > max_items_per_put:
                batch = [eid]
                batch_items = elem_items
                idx += 1
                break

            # If adding this element would exceed the limit, stop the batch
            if batch and (batch_items + elem_items > max_items_per_put):
                break

            batch.append(eid)
            batch_items += elem_items
            idx += 1

        assign = {str(eid): {"ITEMS": merged_items_by_eid[eid]} for eid in batch}

        req += 1
        print(
            f"[apply_beam_load_plan_to_midas] PUT {req}: "
            f"{len(batch)} elements, {batch_items} ITEMS (limit={max_items_per_put})"
        )

        if debug and debug.enabled:
            batch_specs: List[Tuple[int, BeamLoadItem]] = []
            for eid in batch:
                batch_specs.extend((eid, it) for it in new_items_by_eid.get(eid, []))
            debug.dump_chunk_specs(
                batch_specs,
                label=debug_label,
                chunk_index=req,
                reason=f"items<= {max_items_per_put}",
            )

        BeamLoadResource.put_raw({"Assign": assign})

        sent_new += sum(len(new_items_by_eid.get(eid, [])) for eid in batch)

    print(f"[apply_beam_load_plan_to_midas] Done. Sent {sent_new} new beam load items.")
    return plan_df





__all__ = [
    "compute_section_exposures",
    "get_section_properties_cached",
    "_get_element_to_section_map",
    "build_uniform_pressure_beam_load_plan_from_depths",
    "build_uniform_pressure_beam_load_plan_for_group",
    "build_uniform_load_beam_load_plan_for_group",
    "apply_beam_load_plan_to_midas",
]
