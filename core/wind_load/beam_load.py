# core/wind_load/beam_load.py
from __future__ import annotations

from functools import lru_cache
from typing import Sequence, Dict, List

import numpy as np
import pandas as pd

from midas import elements, get_section_properties
from midas.resources.element_beam_load import BeamLoadItem, BeamLoadResource

from core.wind_load.debug import DebugSink
from core.wind_load.groups import get_group_element_ids


# =============================================================================
# Section exposure helper (moved from compute_section_exposures.py)
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

    for row in section_properties:
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

def _get_next_beam_load_id() -> int:
    """
    Look at /db/bmld and return max(ITEM.ID) + 1.
    If there are no existing beam loads, return 1.
    """
    raw = BeamLoadResource.get_raw() or {}

    max_id = 0
    for elem_block in raw.values():
        items = (elem_block or {}).get("ITEMS", []) or []
        for item_dict in items:
            try:
                i = int(item_dict.get("ID", 0))
            except (TypeError, ValueError):
                continue
            if i > max_id:
                max_id = i

    return max_id + 1 if max_id > 0 else 1


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
    elem_to_sect = _get_element_to_section_map(element_ids)

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
# STEP 2: Apply plan to MIDAS
# =============================================================================

def apply_beam_load_plan_to_midas(
    plan_df: pd.DataFrame,
    *,
    start_id: int | None = None,
    chunk_size: int = 5000,
    debug: DebugSink | None = None,
    debug_label: str = "ALL_WIND",
) -> pd.DataFrame:
    """
    Take a plan DataFrame with columns:
      ['element_id', 'line_load', 'load_case', 'load_direction', 'load_group']
    and send them as BeamLoadItem specs to MIDAS.

    IMPORTANT:
      - Chunking is done **between load cases only**.
      - A single load_case is never split across two requests.
    """
    if plan_df is None or plan_df.empty:
        print("[apply_beam_load_plan_to_midas] plan_df is empty; nothing to send.")
        return plan_df

    if start_id is None:
        start_id = _get_next_beam_load_id()

    plan_df = plan_df.sort_values(
        ["load_case", "load_direction", "element_id"],
        kind="stable",
    ).reset_index(drop=True)

    if debug and debug.enabled:
        debug.dump_plan(plan_df, label=debug_label, split_per_case=True)

    total_rows = len(plan_df)
    print(
        f"[apply_beam_load_plan_to_midas] Starting IDs at {start_id}, "
        f"preparing {total_rows} beam loads in chunks of ~{chunk_size} rows, "
        f"but never splitting a load case..."
    )

    next_id = start_id
    sent = 0
    chunk_index = 0
    current_specs: list[tuple[int, BeamLoadItem]] = []

    def _send_specs(specs: list[tuple[int, BeamLoadItem]], *, reason: str = "") -> None:
        nonlocal sent, chunk_index
        if not specs:
            return

        chunk_index += 1
        print(
            f"[apply_beam_load_plan_to_midas] "
            f"Sending chunk of {len(specs)} specs to MIDAS..."
            + (f" ({reason})" if reason else "")
        )

        if debug and debug.enabled:
            debug.dump_chunk_specs(
                specs,
                label=debug_label,
                chunk_index=chunk_index,
                reason=reason,
            )

        BeamLoadResource.create_from_specs(specs)
        sent += len(specs)

    for lcname, lc_df in plan_df.groupby("load_case", sort=False):
        lc_specs: list[tuple[int, BeamLoadItem]] = []

        for _, row in lc_df.iterrows():
            element_id = int(row["element_id"])
            q = float(row["line_load"])
            if abs(q) < 1e-9:
                continue

            ldgr = str(row["load_group"])
            direction = str(row["load_direction"])

            ecc = float(row.get("eccentricity", 0.0))
            use_ecc = abs(ecc) > 1e-9
            ecc_dir = "GZ"

            item = BeamLoadItem(
                ID=next_id,
                LCNAME=str(lcname),
                GROUP_NAME=ldgr,
                CMD="BEAM",
                TYPE="UNILOAD",
                DIRECTION=direction,
                USE_PROJECTION=False,
                USE_ECCEN=use_ecc,
                D=[0, 1, 0, 0],
                P=[q, q, 0, 0],
                ECCEN_TYPE=1,
                ECCEN_DIR=ecc_dir,
                I_END=ecc,
                J_END=ecc,
            )
            lc_specs.append((element_id, item))
            next_id += 1

        if not lc_specs:
            print(
                f"[apply_beam_load_plan_to_midas] "
                f"All loads ~0 for load case {lcname}; skipping."
            )
            continue

        if current_specs and (len(current_specs) + len(lc_specs) > chunk_size):
            _send_specs(current_specs, reason=f"before load case {lcname}")
            current_specs = []

        if len(lc_specs) > chunk_size:
            _send_specs(lc_specs, reason=f"large_case:{lcname}")
        else:
            current_specs.extend(lc_specs)

    if current_specs:
        _send_specs(current_specs, reason="final")

    print(
        f"[apply_beam_load_plan_to_midas] Done. Sent {sent} specs "
        f"({total_rows} plan rows, some may have been skipped as ~0)."
    )

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
