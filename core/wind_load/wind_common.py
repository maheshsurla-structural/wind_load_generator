# core/wind_load/wind_common.py
from __future__ import annotations

from typing import Any, Sequence, Dict, Tuple
import re
import pandas as pd

from core.wind_load.groups import get_structural_group_element_ids
from core.wind_load.beam_load import (
    build_uniform_load_beam_load_plan_for_group,
    convert_pressure_to_line_loads_by_exposure_depth,
    _get_element_to_section_map,
    get_section_properties_cached,
)
from core.wind_load.beam_load import compute_section_exposures


# =============================================================================
# Quadrant helpers
# =============================================================================

_QUADRANT_RE = re.compile(r"(?:_Q|Q)([1-4])\b", re.I)
def parse_quadrant_from_load_case_name(name: str) -> int:
    """Parse Q1..Q4 from case name. Defaults to Q1 if missing."""
    m = _QUADRANT_RE.search(name or "")
    return int(m.group(1)) if m else 1


_QUAD_SIGNS: dict[int, tuple[int, int]] = {
    1: (+1, +1),
    2: (+1, -1),
    3: (-1, -1),
    4: (-1, +1),
}

def apply_quadrant_sign_convention(q: int, t: float, l: float) -> tuple[float, float]:
    """Apply quadrant signs to (t, l)."""
    ts, ls = _QUAD_SIGNS.get(int(q), _QUAD_SIGNS[1])
    return ts * float(t), ls * float(l)


# =============================================================================
# Case table normalization: Case/Angle/Value
# Used by WL + WS deck + WS sub
# =============================================================================

def normalize_and_validate_cases_df(
    df_in: pd.DataFrame,
    *,
    df_name: str = "cases_df",
) -> pd.DataFrame:
    """
    Expected columns: Case, Angle, Value
    - Angle numeric + integer-like -> int
    - Case/Value stripped and non-empty
    """
    needed = {"Case", "Angle", "Value"}
    missing = needed - set(df_in.columns)
    if missing:
        raise ValueError(f"{df_name} is missing columns: {missing}")

    df = df_in.copy()

    df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
    bad = df["Angle"].isna()
    if bad.any():
        raise ValueError(f"{df_name} has non-numeric Angle at rows: {df.index[bad].tolist()}")

    non_int = (df["Angle"] % 1 != 0)
    if non_int.any():
        raise ValueError(f"{df_name} has non-integer Angle at rows: {df.index[non_int].tolist()}")

    df["Angle"] = df["Angle"].astype(int)

    df["Case"] = df["Case"].astype(str).str.strip()
    df["Value"] = df["Value"].astype(str).str.strip()

    empty_case = df["Case"] == ""
    if empty_case.any():
        raise ValueError(f"{df_name} has empty Case at rows: {df.index[empty_case].tolist()}")

    empty_val = df["Value"] == ""
    if empty_val.any():
        raise ValueError(f"{df_name} has empty Value at rows: {df.index[empty_val].tolist()}")

    return df


# =============================================================================
# Coefficients normalization (angles, transverse, longitudinal)
# Used by WL coeffs + skew coeffs
# =============================================================================

CONTROL_ANGLES: tuple[int, ...] = (0, 15, 30, 45, 60)


def coeffs_by_angle(
    *,
    angles: Sequence[Any],
    transverse: Sequence[Any],
    longitudinal: Sequence[Any],
    table_name: str = "coeffs",
    require_unique_angles: bool = True,
) -> Dict[int, Tuple[float, float]]:
    """
    Returns {angle:int -> (T:float, L:float)}.

    Designed for Control Data usage where angles are fixed and non-editable:
    CONTROL_ANGLES = (0, 15, 30, 45, 60)
    """
    if angles is None:
        raise ValueError(f"{table_name}: angles is None")

    # Fail-fast: control angles must match exactly (catches wrong table/order/wiring).
    try:
        angs = tuple(int(a) for a in angles)
    except (TypeError, ValueError):
        raise ValueError(f"{table_name}: angles must be integer-like; got {list(angles)!r}")

    if require_unique_angles and angs != CONTROL_ANGLES:
        raise ValueError(f"{table_name}: angles must be exactly {list(CONTROL_ANGLES)} (got {list(angs)})")

    n = len(CONTROL_ANGLES)
    if not (len(transverse) == len(longitudinal) == n):
        raise ValueError(
            f"{table_name}: expected {n} transverse/longitudinal values "
            f"(got {len(transverse)}, {len(longitudinal)})"
        )

    def _to_float(x: Any, kind: str, i: int) -> float:
        if isinstance(x, str) and not x.strip():
            raise ValueError(f"{table_name}: blank {kind} at row {i} (angle={CONTROL_ANGLES[i]})")
        try:
            return float(x)
        except (TypeError, ValueError):
            raise ValueError(
                f"{table_name}: non-numeric {kind} at row {i} (angle={CONTROL_ANGLES[i]}): {x!r}"
            )

    return {
        CONTROL_ANGLES[i]: (_to_float(transverse[i], "transverse", i), _to_float(longitudinal[i], "longitudinal", i))
        for i in range(n)
    }






__all__ = [
    # quadrant + sign
    "parse_quadrant_from_load_case_name",
    "apply_quadrant_sign_convention",
    # cases + coeffs
    "normalize_and_validate_cases_df",
    "coeffs_by_angle",
    # plans
    "combine_plans",
    "build_line_load_plan_from_components",
    "build_pressure_plan_from_components",
]
