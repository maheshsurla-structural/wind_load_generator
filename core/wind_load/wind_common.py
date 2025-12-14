# core/wind_load/wind_common.py
from __future__ import annotations

from typing import Any, Sequence, Dict, Tuple
import re
import pandas as pd

# ----------------------------
# Quadrant helpers
# ----------------------------

_QUADRANT_RE = re.compile(r"(?:_Q|Q)([1-4])\b", re.I)

_QUAD_SIGNS: dict[int, tuple[int, int]] = {
    1: (+1, +1),
    2: (+1, -1),
    3: (-1, -1),
    4: (-1, +1),
}

def parse_quadrant_from_load_case_name(name: str) -> int:
    """Parse Q1..Q4 from case name. Defaults to Q1 if missing."""
    m = _QUADRANT_RE.search(name or "")
    return int(m.group(1)) if m else 1

def apply_quadrant_sign_convention(q: int, t: float, l: float) -> tuple[float, float]:
    """Apply quadrant signs to (t, l)."""
    ts, ls = _QUAD_SIGNS.get(int(q), _QUAD_SIGNS[1])
    return ts * float(t), ls * float(l)

# ----------------------------
# Case table normalization: Case/Angle/Value
# Used by WL + WS deck + WS sub
# ----------------------------

def normalize_and_validate_cases_df(df_in: pd.DataFrame, *, df_name: str = "cases_df") -> pd.DataFrame:
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

# ----------------------------
# Coefficients normalization (angles, transverse, longitudinal)
# Used by WL coeffs + skew coeffs
# ----------------------------

def coeffs_by_angle(
    *,
    angles: Sequence[Any],
    transverse: Sequence[Any],
    longitudinal: Sequence[Any],
    table_name: str = "coeffs",
    require_unique_angles: bool = True,
) -> Dict[int, Tuple[float, float]]:
    """
    Returns {angle:int -> (T:float, L:float)}
    """
    if angles is None:
        raise ValueError(f"{table_name}: angles is None")

    if not (len(angles) == len(transverse) == len(longitudinal)):
        raise ValueError(
            f"{table_name}: angles/transverse/longitudinal must have same length "
            f"(got {len(angles)}, {len(transverse)}, {len(longitudinal)})"
        )

    df = pd.DataFrame({"Angle": list(angles), "T": list(transverse), "L": list(longitudinal)})

    df["Angle"] = pd.to_numeric(df["Angle"], errors="coerce")
    bad = df["Angle"].isna()
    if bad.any():
        raise ValueError(f"{table_name}: non-numeric angle at rows: {df.index[bad].tolist()}")

    non_int = (df["Angle"] % 1 != 0)
    if non_int.any():
        raise ValueError(f"{table_name}: non-integer angle at rows: {df.index[non_int].tolist()}")

    df["Angle"] = df["Angle"].astype(int)

    df["T"] = pd.to_numeric(df["T"], errors="coerce")
    bad_t = df["T"].isna()
    if bad_t.any():
        raise ValueError(f"{table_name}: non-numeric transverse at rows: {df.index[bad_t].tolist()}")

    df["L"] = pd.to_numeric(df["L"], errors="coerce")
    bad_l = df["L"].isna()
    if bad_l.any():
        raise ValueError(f"{table_name}: non-numeric longitudinal at rows: {df.index[bad_l].tolist()}")

    if require_unique_angles:
        dup = df["Angle"].duplicated(keep=False)
        if dup.any():
            counts = df.loc[dup, "Angle"].value_counts().sort_index().to_dict()
            raise ValueError(f"{table_name}: duplicate angles found: {counts}")

    return {
        int(a): (float(t), float(l))
        for a, t, l in zip(df["Angle"].tolist(), df["T"].tolist(), df["L"].tolist())
    }
