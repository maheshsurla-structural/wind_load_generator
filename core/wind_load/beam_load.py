# core/wind_load/beam_load.py

from __future__ import annotations
from typing import Dict, List, Any, Tuple
import pandas as pd

from midas.resources.structural_group import StructuralGroup
from core.wind_load.compute_section_exposures import compute_section_exposures
from midas.resources.element_beam_load import BeamLoadItem, BeamLoadResource


# -------------------------------------------------
# PROJECT HOOKS (you still need to implement these)
# -------------------------------------------------

def _get_element_to_section_map(element_ids: List[int]) -> Dict[int, int]:
    """
    MUST BE IMPLEMENTED BY YOU.

    Return { element_id: section_id } for each element in element_ids.

    We need this because wind load is applied per element, but the exposure
    depth is computed per section property.
    """
    raise NotImplementedError


def _get_all_section_properties_raw() -> List[List[Any]]:
    """
    MUST BE IMPLEMENTED BY YOU.

    Return the raw section properties table (the thing you already pass into
    compute_section_exposures). Each row must satisfy:

        row[1]  = section/property ID
        row[11] = LEFT
        row[12] = RIGHT
        row[13] = TOP
        row[14] = BOTTOM
    """
    raise NotImplementedError


# -------------------------------------------------
# STEP 1: Build the per-element wind load plan
# -------------------------------------------------

def build_beam_load_plan_for_group(
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
    Build the wind UDL plan for a structural group but DO NOT touch MIDAS yet.

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
    section_props_raw = _get_all_section_properties_raw()
    exposures_df = compute_section_exposures(
        section_props_raw,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
        as_dataframe=True,
    )

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
# STEP 2: Take that plan and actually PUT beam loads to MIDAS
# -------------------------------------------------

def apply_wind_load_to_midas_for_group(
    group_name: str,
    load_case_name: str,
    pressure: float,
    *,
    load_group_name: str = "",
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
    exposure_axis: str = "y",
    udl_direction: str = "GZ",
) -> pd.DataFrame:
    """
    End-to-end function you call from the UI / workflow.

    What it does:
      1. Calls build_beam_load_plan_for_group(...) to compute UDL per element.
      2. Converts each row to BeamLoadItem.
      3. Sends them to MIDAS (/db/bmld) using BeamLoadResource.create_from_specs().
      4. Returns the plan DataFrame for logging / display.

    After this runs, the wind beam loads exist in the MIDAS model.
    """

    # STEP 1: math + bookkeeping
    plan_df = build_beam_load_plan_for_group(
        group_name=group_name,
        load_case_name=load_case_name,
        pressure=pressure,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
        exposure_axis=exposure_axis,
        udl_direction=udl_direction,
        load_group_name=load_group_name,
    )

    # Nothing to assign? bail out gracefully
    if plan_df.empty:
        return plan_df

    # STEP 2: turn rows into BeamLoadItem specs MIDAS understands
    specs: List[Tuple[int, BeamLoadItem]] = []

    for idx, row in plan_df.iterrows():
        element_id = int(row["element_id"])
        q = float(row["line_load"])  # final UDL we want to apply
        lcname = str(row["load_case"])
        ldgr = str(row["load_group"])
        direction = str(row["load_direction"])

        item = BeamLoadItem(
            ID=idx + 1,             # unique per batch
            LCNAME=lcname,          
            GROUP_NAME=ldgr,        
            CMD="BEAM",
            TYPE="UNILOAD",
            DIRECTION=direction,
            USE_PROJECTION=False,
            USE_ECCEN=False,
            D=[0, 1, 0, 0],         # [start, end, extra?, extra?] normalized to span
            P=[q, q, 0, 0],         # uniform load q over full length
            # all eccentric/additional flags default off, which matches your
            # simple UDL JSON example
        )

        specs.append((element_id, item))

    # STEP 3: single PUT to /db/bmld via BeamLoadResource
    BeamLoadResource.create_from_specs(specs)

    # STEP 4: return summary DataFrame for whoever called this
    return plan_df
