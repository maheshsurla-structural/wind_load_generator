# core/wind_load/compute_section_exposures.py

import numpy as np
import pandas as pd


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

    # Otherwise, return as dictionary
    return {property_ids[i]: (exposure_y[i], exposure_z[i]) for i in range(property_ids.size)}
