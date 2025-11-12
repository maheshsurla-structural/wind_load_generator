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

def build_uniform_pressure_beam_load_plan_for_group(
    group_name: str,
    load_case_name: str,
    pressure: float,
    *,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
    exposure_axis: str = "y",   # "y" -> use exposure_y, "z" -> use exposure_z
    udl_direction: str = "GZ",  # "GX","GY","GZ","LX","LY","LZ" for MIDAS beam load dir
    load_group_name: str = "",
) -> pd.DataFrame:
    """
    Build a UDL plan from a UNIFORM PRESSURE (kips/ft^2) on a structural group.

    Returns a DataFrame with one row per element in the group:

        element_id          (int)   which element gets the load
        section_id          (int)   section property assigned to that element
        exposure_depth      (float) projected depth used for wind
        pressure            (float) input pressure
        line_load           (float) final UDL = pressure * exposure_depth
        load_case           (str)   name of the load case to apply
        load_direction      (str)   "GZ"/"GY"/etc for MIDAS
        load_group          (str)   load group name for MIDAS
        group_name          (str)   the structural group we started from
    """

    # 1. get all elements in this structural group
    element_ids = StructuralGroup.get_elements_by_name(group_name)

    # 2. map element -> section (property) ID
    elem_to_sect = _get_element_to_section_map(element_ids)

    # 3. compute exposure depths for ALL sections
    section_props_raw = get_section_properties()
    
    exposures_df = compute_section_exposures(
        section_props_raw,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
        as_dataframe=True,
    )



    # make sure index is int so it matches elem_to_sect values
    try:
        exposures_df.index = exposures_df.index.astype(int)
    except ValueError:
        pass  # fallback if some IDs aren't numeric

    # choose projection axis
    depth_col = "exposure_z" if exposure_axis.lower() == "z" else "exposure_y"

    rows: List[dict[str, Any]] = []

    for eid in element_ids:
        sect_id = elem_to_sect.get(eid)
        if sect_id is None:
            # No section assigned? skip
            continue
        if sect_id not in exposures_df.index:
            # Section not in exposure table? skip
            continue

        exposure_depth = float(exposures_df.loc[sect_id, depth_col])
        udl_value = pressure * exposure_depth  # final line load (force/length)

        rows.append(
            {
                "element_id": int(eid),
                "section_id": int(sect_id),
                "exposure_depth": exposure_depth,
                "pressure": pressure,
                "line_load": udl_value,
                "load_case": load_case_name,
                "load_direction": udl_direction,
                "load_group": load_group_name,
                "group_name": group_name,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values("element_id", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df

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
) -> pd.DataFrame:
    """
    Generic: take a plan DataFrame with columns
        ['element_id', 'line_load', 'load_case', 'load_direction', 'load_group']
    and send them as BeamLoadItem specs to MIDAS.

    start_id lets you control ID uniqueness if you ever batch multiple calls.
    """

    if plan_df is None or plan_df.empty:
        return plan_df

    specs: List[Tuple[int, BeamLoadItem]] = []

    for idx, row in plan_df.iterrows():
        element_id = int(row["element_id"])
        q = float(row["line_load"])
        if abs(q) < 1e-9:
            continue

        lcname = str(row["load_case"])
        ldgr = str(row["load_group"])
        direction = str(row["load_direction"])

        # NEW: eccentricity (ft). If not present, assume 0.
        ecc = float(row.get("eccentricity", 0.0))
        use_ecc = abs(ecc) > 1e-9

        # Choose an eccentricity axis:
        # for horizontal wind (LX/LY) you usually want vertical offset → "GZ"
        ecc_dir = "GZ"

        item = BeamLoadItem(
            ID=start_id + idx,
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
            ECCEN_TYPE=1,          # distance type
            ECCEN_DIR=ecc_dir,     # axis of eccentricity
            I_END=ecc,             # 6 ft at I-end
            J_END=ecc,             # 6 ft at J-end
            # USE_J_END is auto True if J_END != 0
        )
        specs.append((element_id, item))

    if specs:
        BeamLoadResource.create_from_specs(specs)

    return plan_df