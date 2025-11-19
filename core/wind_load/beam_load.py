# core/wind_load/beam_load.py

from __future__ import annotations
from typing import Sequence, Dict, List, Any, Tuple
import pandas as pd
from functools import lru_cache
from midas.resources.structural_group import StructuralGroup
from core.wind_load.compute_section_exposures import compute_section_exposures
from midas.resources.element_beam_load import BeamLoadItem, BeamLoadResource
from midas import elements, get_section_properties

# -------------------------------------------------
# PROJECT HOOKS (you still need to implement these)
# -------------------------------------------------

def _get_element_to_section_map(element_ids: List[int]) -> Dict[int, int]:
    """
    Return {element_id: section_id} for each element in element_ids.

    Uses /db/ELEM via midas.elements.get_all().
    Each element dict must contain the key "SECT" (or equivalent)
    referring to its assigned section/property ID.
    Elements missing that key are skipped.
    """
    out: Dict[int, int] = {}
    all_elem_data = elements.get_all()  # /db/ELEM dump

    for eid in element_ids:
        edata = all_elem_data.get(str(eid))
        if not edata:
            continue

        sect_id = edata.get("SECT")  # <-- adjust key name if different in your model
        if sect_id is None:
            continue

        try:
            out[int(eid)] = int(sect_id)
        except (TypeError, ValueError):
            continue

    return out


# -------------------------------------------------
# STEP 1: Build the per-element wind load plan
# -------------------------------------------------

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
    Low-level helper: given
        - pressure (ksf)
        - precomputed exposure depth per element (ft)
    build a beam-load plan DataFrame.

    This function does NOT talk to MIDAS. It just does:
        q = pressure * depth_by_eid[eid]
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

    from midas.resources.structural_group import StructuralGroup
    from midas import get_section_properties
    from core.wind_load.compute_section_exposures import compute_section_exposures

    element_ids = StructuralGroup.get_elements_by_name(group_name)
    elem_to_sect = _get_element_to_section_map(element_ids)

    section_props_raw = get_section_properties()
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


# -------------------------------------------------
# LINE LOAD plan (kips/ft directly)
# -------------------------------------------------

def build_uniform_load_beam_load_plan_for_group(
    *,
    group_name: str,
    load_case_name: str,
    line_load: float,
    udl_direction: str,
    load_group_name: str | None = None,
    element_ids: Sequence[int] | None = None,
    eccentricity: float = 0.0,           # ← NEW (ft, same units as model)
) -> pd.DataFrame:

    # 1) Resolve elements for this group
    if element_ids is None:
        element_ids = StructuralGroup.get_elements_by_name(group_name)

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
                "eccentricity": float(eccentricity),   # ← NEW
            }
        )

    plan_df = pd.DataFrame(rows)
    if not plan_df.empty:
        plan_df.sort_values("element_id", inplace=True)
        plan_df.reset_index(drop=True, inplace=True)
    return plan_df



# -------------------------------------------------
# STEP 2: Take that plan and actually PUT beam loads to MIDAS
# -------------------------------------------------

# -------------------------------------------------
# APPLY any beam-load plan to MIDAS
# -------------------------------------------------

def apply_beam_load_plan_to_midas(
    plan_df: pd.DataFrame,
    *,
    start_id: int = 1,
    chunk_size: int = 4000,   # NEW: limit number of BMLD rows per request
) -> pd.DataFrame:
    """
    Take a plan DataFrame with columns
        ['element_id', 'line_load', 'load_case', 'load_direction', 'load_group']
    and send them as BeamLoadItem specs to MIDAS.

    To avoid MIDAS silently dropping very large JSON payloads, the specs are
    sent in chunks of `chunk_size` items.
    """

    if plan_df is None or plan_df.empty:
        print("[apply_beam_load_plan_to_midas] plan_df is empty; nothing to send.")
        return plan_df

    total_rows = len(plan_df)
    print(
        f"[apply_beam_load_plan_to_midas] Preparing {total_rows} beam loads "
        f"in chunks of {chunk_size}..."
    )

    specs: List[Tuple[int, BeamLoadItem]] = []
    next_id = start_id
    sent = 0

    for _, row in plan_df.iterrows():
        element_id = int(row["element_id"])
        q = float(row["line_load"])
        if abs(q) < 1e-9:
            continue

        lcname = str(row["load_case"])
        ldgr = str(row["load_group"])
        direction = str(row["load_direction"])

        # Eccentricity (ft). If not present, assume 0.
        ecc = float(row.get("eccentricity", 0.0))
        use_ecc = abs(ecc) > 1e-9

        # For horizontal wind (LX/LY) we usually use vertical offset → "GZ"
        ecc_dir = "GZ"

        item = BeamLoadItem(
            ID=next_id,
            LCNAME=lcname,
            GROUP_NAME=ldgr,
            CMD="BEAM",
            TYPE="UNILOAD",
            DIRECTION=direction,
            USE_PROJECTION=False,
            USE_ECCEN=use_ecc,
            # full-length uniform load
            D=[0, 1, 0, 0],
            P=[q, q, 0, 0],
            # eccentricity block
            ECCEN_TYPE=1,      # distance type
            ECCEN_DIR=ecc_dir, # axis of eccentricity
            I_END=ecc,         # ecc at I-end
            J_END=ecc,         # ecc at J-end
        )

        specs.append((element_id, item))
        next_id += 1

        # If we've accumulated a full chunk, flush it to MIDAS
        if len(specs) >= chunk_size:
            print(
                f"[apply_beam_load_plan_to_midas] "
                f"Sending chunk of {len(specs)} specs to MIDAS..."
            )
            BeamLoadResource.create_from_specs(specs)
            sent += len(specs)
            specs.clear()

    # Flush any remaining specs
    if specs:
        print(
            f"[apply_beam_load_plan_to_midas] "
            f"Sending final chunk of {len(specs)} specs to MIDAS..."
        )
        BeamLoadResource.create_from_specs(specs)
        sent += len(specs)

    print(
        f"[apply_beam_load_plan_to_midas] Done. Sent {sent} specs "
        f"({total_rows} plan rows, some may have been skipped as ~0)."
    )

    return plan_df
