# core/wind_load/beam_load.py
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from collections import defaultdict
from typing import Any, Dict, List, Sequence, Tuple, Mapping, Iterable, Optional

import logging
import numpy as np
import pandas as pd

from midas import elements, get_section_properties
from midas.resources.element_beam_load import BeamLoadItem, BeamLoadResource

from core.wind_load.debug import DebugSink
from core.wind_load.groups import get_structural_group_element_ids

logger = logging.getLogger(__name__)

EPS = 1e-9

# -----------------------------
# Plan schema (single source)
# -----------------------------
PLAN_REQUIRED_COLS = {"element_id", "line_load", "load_case", "load_direction", "load_group"}
PLAN_SORT_COLS = ["load_case", "load_direction", "element_id"]


# =============================================================================
# Cached MIDAS reads
# =============================================================================

@lru_cache(maxsize=1)
def _get_all_elements_cached() -> dict:
    return elements.get_all() or {}

@lru_cache(maxsize=1)
def get_section_properties_cached():
    return get_section_properties()


def _validate_axis(axis: str) -> str:
    ax = str(axis).strip().lower()
    if ax not in {"y", "z"}:
        raise ValueError(f"axis must be 'y' or 'z', got {axis!r}")
    return ax


def _get_element_to_section_map(element_ids: Sequence[int]) -> Dict[int, int]:
    """Map element_id -> section_id using cached /db/elem snapshot."""
    out: Dict[int, int] = {}
    all_elem = _get_all_elements_cached()

    for eid in element_ids:
        try:
            eid_i = int(eid)
        except (TypeError, ValueError):
            continue

        edata = all_elem.get(str(eid_i))
        if not edata:
            continue

        sect_id = edata.get("SECT")
        if sect_id is None:
            continue

        try:
            out[eid_i] = int(sect_id)
        except (TypeError, ValueError):
            continue

    return out


# =============================================================================
# Domain: exposures
# =============================================================================

def compute_section_exposures(
    section_properties: Iterable,
    *,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Optional[Dict[int, float]] = None,
    as_dataframe: bool = True,
) -> pd.DataFrame | Dict[Any, Tuple[float, float]]:
    """
    Compute local exposure depths for all section properties.

    Assumes a MIDAS section property row layout with:
      - property id at COL_ID
      - left/right/top/bottom offsets at COL_LEFT/COL_RIGHT/COL_TOP/COL_BOTTOM

    Returns:
      DataFrame indexed by property_id with columns: exposure_y, exposure_z
      or dict[property_id] = (exposure_y, exposure_z)
    """
    COL_ID, COL_LEFT, COL_RIGHT, COL_TOP, COL_BOTTOM = 1, 11, 12, 13, 14

    pids: list[Any] = []
    left: list[float] = []
    right: list[float] = []
    top: list[float] = []
    bottom: list[float] = []

    for row in section_properties or []:
        if not row or len(row) <= COL_BOTTOM:
            continue
        try:
            pid = row[COL_ID]
            pids.append(pid)
            left.append(float(row[COL_LEFT]))
            right.append(float(row[COL_RIGHT]))
            top.append(float(row[COL_TOP]))
            bottom.append(float(row[COL_BOTTOM]))
        except (TypeError, ValueError):
            continue

    if not pids:
        return pd.DataFrame(columns=["exposure_y", "exposure_z"]) if as_dataframe else {}

    pids_arr = np.asarray(pids, dtype=object)
    left_arr = np.asarray(left, dtype=float)
    right_arr = np.asarray(right, dtype=float)
    top_arr = np.asarray(top, dtype=float)
    bottom_arr = np.asarray(bottom, dtype=float)

    if extra_exposure_y_by_id:
        extra_y = np.fromiter(
            (extra_exposure_y_by_id.get(int(pid), extra_exposure_y_default) for pid in pids_arr),
            dtype=float,
            count=pids_arr.size,
        )
    else:
        extra_y = np.full(pids_arr.size, extra_exposure_y_default, dtype=float)

    exposure_y = top_arr + bottom_arr + extra_y
    exposure_z = left_arr + right_arr

    if as_dataframe:
        df = pd.DataFrame({"exposure_y": exposure_y, "exposure_z": exposure_z}, index=pids_arr)
        df.index.name = "property_id"
        # Normalize index for reliable .loc lookups where sect_id is int
        try:
            df.index = df.index.astype(int)
        except Exception:
            pass
        return df

    return {pids_arr[i]: (float(exposure_y[i]), float(exposure_z[i])) for i in range(pids_arr.size)}


@dataclass
class ExposureResolver:
    """
    Resolves exposure depth maps for element IDs with caching.

    - Reads section properties once.
    - Computes exposures DF once.
    - Builds depth_by_eid quickly for any element list.
    """
    extra_exposure_y_default: float = 0.0
    extra_exposure_y_by_id: Optional[Dict[int, float]] = None

    _exposures_df: Optional[pd.DataFrame] = None

    def exposures_df(self) -> pd.DataFrame:
        if self._exposures_df is None:
            raw = get_section_properties_cached()
            self._exposures_df = compute_section_exposures(
                raw,
                extra_exposure_y_default=self.extra_exposure_y_default,
                extra_exposure_y_by_id=self.extra_exposure_y_by_id,
                as_dataframe=True,
            )
        return self._exposures_df

    def depth_map(self, *, element_ids: Sequence[int], axis: str) -> Dict[int, float]:
        ax = _validate_axis(axis)
        element_ids = [int(e) for e in element_ids or []]
        if not element_ids:
            return {}

        elem_to_sect = _get_element_to_section_map(element_ids)
        if not elem_to_sect:
            return {}

        df = self.exposures_df()
        if df is None or df.empty:
            return {}

        col = "exposure_z" if ax == "z" else "exposure_y"

        out: Dict[int, float] = {}
        for eid, sid in elem_to_sect.items():
            if sid in df.index:
                out[eid] = float(df.loc[sid, col])
        return out

    def depth_map_for_group(self, *, group_name: str, axis: str) -> Dict[int, float]:
        eids = get_structural_group_element_ids(group_name)
        return self.depth_map(element_ids=eids, axis=axis)


# =============================================================================
# STEP 1: Build plan DataFrames (pure-ish)
# =============================================================================

def convert_pressure_to_line_loads_by_exposure_depth(
    *,
    group_name: str,
    load_case_name: str,
    pressure: float,
    udl_direction: str,
    depth_by_eid: Dict[int, float],
    load_group_name: str | None = None,
    eccentricity: float = 0.0,
) -> pd.DataFrame:
    rows: list[dict] = []
    lc = str(load_case_name).strip()
    lg = str(load_group_name or lc).strip()

    for eid, depth in (depth_by_eid or {}).items():
        q = float(pressure) * float(depth)  # ksf * ft = k/ft
        if abs(q) < EPS:
            continue
        rows.append(
            {
                "element_id": int(eid),
                "line_load": float(q),
                "load_case": lc,
                "load_direction": str(udl_direction).strip(),
                "load_group": lg,
                "group_name": str(group_name).strip(),
                "eccentricity": float(eccentricity),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values("element_id", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def build_uniform_load_beam_load_plan_for_group(
    *,
    group_name: str,
    load_case_name: str,
    line_load: float,
    udl_direction: str,
    load_group_name: str | None = None,
    element_ids: Optional[Sequence[int]] = None,
    eccentricity: float = 0.0,
) -> pd.DataFrame:
    if element_ids is None:
        element_ids = get_structural_group_element_ids(group_name)

    lc = str(load_case_name).strip()
    lg = str(load_group_name or lc).strip()

    rows = [
        {
            "element_id": int(eid),
            "line_load": float(line_load),
            "load_case": lc,
            "load_direction": str(udl_direction).strip(),
            "load_group": lg,
            "group_name": str(group_name).strip(),
            "eccentricity": float(eccentricity),
        }
        for eid in (element_ids or [])
    ]

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values("element_id", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def combine_plans(plans: Sequence[pd.DataFrame]) -> pd.DataFrame:
    if not plans:
        return pd.DataFrame()
    out = pd.concat([p for p in plans if p is not None and not p.empty], ignore_index=True)
    if out.empty:
        return out
    out.sort_values(["load_case", "element_id"], inplace=True)
    out.reset_index(drop=True, inplace=True)
    return out


def build_line_load_plan_from_components(
    *,
    group_name: str,
    components_df: pd.DataFrame,
    component_map: Mapping[str, str],  # {component_col: "LX"/"LY"/...}
    element_ids: list[int],
    eccentricity: float = 0.0,
    load_case_col: str = "load_case",
    load_group_col: str = "load_group",
) -> pd.DataFrame:
    """
    components_df has component columns already as line load (k/ft).
    """
    if components_df is None or components_df.empty or not element_ids:
        return pd.DataFrame()

    plans: list[pd.DataFrame] = []

    # itertuples is faster and cleaner than iterrows
    for row in components_df.itertuples(index=False):
        d = row._asdict() if hasattr(row, "_asdict") else row.__dict__
        lc = str(d.get(load_case_col, "")).strip()
        if not lc:
            continue
        lg = str(d.get(load_group_col) or lc).strip()

        for col, direction in component_map.items():
            val = float(d.get(col, 0.0))
            if abs(val) <= EPS:
                continue

            plan = build_uniform_load_beam_load_plan_for_group(
                group_name=group_name,
                load_case_name=lc,
                line_load=val,
                udl_direction=direction,
                load_group_name=lg,
                element_ids=element_ids,
                eccentricity=eccentricity,
            )
            if not plan.empty:
                plans.append(plan)

    return combine_plans(plans)


def build_pressure_plan_from_components(
    *,
    group_name: str,
    components_df: pd.DataFrame,
    component_map: Mapping[str, Tuple[str, str]],
    # {pressure_col: (udl_direction, axis)} axis is "y" or "z"
    element_ids: list[int],
    resolver: Optional[ExposureResolver] = None,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Optional[Dict[int, float]] = None,
    eccentricity: float = 0.0,
    load_case_col: str = "load_case",
    load_group_col: str = "load_group",
) -> pd.DataFrame:
    """
    components_df has pressures (ksf). Convert pressure -> line load using exposure depth (ft).
    """
    if components_df is None or components_df.empty or not element_ids:
        return pd.DataFrame()

    if resolver is None:
        resolver = ExposureResolver(
            extra_exposure_y_default=extra_exposure_y_default,
            extra_exposure_y_by_id=extra_exposure_y_by_id,
        )

    # Build depth maps once per axis actually used
    depth_by_axis: Dict[str, Dict[int, float]] = {}
    for _, axis in component_map.values():
        ax = _validate_axis(axis)
        if ax not in depth_by_axis:
            depth_by_axis[ax] = resolver.depth_map(element_ids=element_ids, axis=ax)

    plans: list[pd.DataFrame] = []

    for row in components_df.itertuples(index=False):
        d = row._asdict() if hasattr(row, "_asdict") else row.__dict__
        lc = str(d.get(load_case_col, "")).strip()
        if not lc:
            continue
        lg = str(d.get(load_group_col) or lc).strip()

        for p_col, (direction, axis) in component_map.items():
            p = float(d.get(p_col, 0.0))
            if abs(p) <= EPS:
                continue

            depth_map = depth_by_axis.get(_validate_axis(axis)) or {}
            if not depth_map:
                continue

            plan = convert_pressure_to_line_loads_by_exposure_depth(
                group_name=group_name,
                load_case_name=lc,
                pressure=p,
                udl_direction=direction,
                depth_by_eid=depth_map,
                load_group_name=lg,
                eccentricity=eccentricity,
            )
            if not plan.empty:
                plans.append(plan)

    return combine_plans(plans)


# =============================================================================
# STEP 2: Apply plan to MIDAS
# =============================================================================

@dataclass(frozen=True)
class ApplyStats:
    requests: int
    elements_touched: int
    new_items_sent: int


def _next_id_by_element_from_raw(raw: Dict[str, Any]) -> Dict[int, int]:
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


def _normalize_plan_df(plan_df: pd.DataFrame, *, aggregate_duplicates: bool) -> pd.DataFrame:
    missing = PLAN_REQUIRED_COLS - set(plan_df.columns)
    if missing:
        raise ValueError(f"plan_df missing required columns: {sorted(missing)}")

    df = plan_df.copy()
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
        df = df.groupby(key_cols, as_index=False, sort=False)["line_load"].sum()

    df = df.sort_values(PLAN_SORT_COLS, kind="stable").reset_index(drop=True)
    return df


def apply_beam_load_plan_to_midas(
    plan_df: pd.DataFrame,
    *,
    max_items_per_put: int = 5000,
    debug: DebugSink | None = None,
    debug_label: str = "WIND_ASSIGN",
    replace_existing_for_plan_load_cases: bool = True,
    aggregate_duplicates: bool = True,
    progress: Optional[callable] = None,  # progress hook instead of print()
    resource: Any = BeamLoadResource,     # dependency injection hook
) -> pd.DataFrame:
    """
    Apply a beam-load plan to MIDAS (/db/bmld) using safe merge-per-element writes.

    Debug behavior:
      - If debug.enabled and debug.dump_apply_payload exists:
        dump exactly one JSON at the end with the exact PUT payload(s) sent.
    """
    if plan_df is None or plan_df.empty:
        logger.info("apply_beam_load_plan_to_midas: plan_df empty; nothing to send.")
        return plan_df

    max_items_per_put = max(int(max_items_per_put), 1)
    df = _normalize_plan_df(plan_df, aggregate_duplicates=aggregate_duplicates)

    raw_existing = resource.get_raw() or {}

    existing_items_by_eid: Dict[int, List[Dict[str, Any]]] = {}
    for eid_str, elem_block in raw_existing.items():
        try:
            eid = int(eid_str)
        except (TypeError, ValueError):
            continue
        existing_items_by_eid[eid] = list(((elem_block or {}).get("ITEMS", []) or []))

    next_id_by_eid = _next_id_by_element_from_raw(raw_existing)

    def alloc_id(eid: int) -> int:
        nxt = next_id_by_eid.get(eid, 1)
        next_id_by_eid[eid] = nxt + 1
        return nxt

    plan_cases = set(df["load_case"].astype(str).str.strip())

    new_by_eid: Dict[int, List[BeamLoadItem]] = defaultdict(list)

    for lcname, lc_df in df.groupby("load_case", sort=False):
        lcname = str(lcname).strip()
        if not lcname:
            continue

        for row in lc_df.itertuples(index=False):
            eid = int(getattr(row, "element_id"))
            q = float(getattr(row, "line_load"))
            if abs(q) < EPS:
                continue

            direction = str(getattr(row, "load_direction"))
            ldgr = str(getattr(row, "load_group"))

            ecc = float(getattr(row, "eccentricity", 0.0))
            use_ecc = abs(ecc) > EPS

            new_by_eid[eid].append(
                BeamLoadItem(
                    ID=alloc_id(eid),
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
            )

    if not new_by_eid:
        logger.info("apply_beam_load_plan_to_midas: all loads ~0; nothing to send.")
        return df

    touched_eids = sorted(new_by_eid.keys())
    total_new = sum(len(v) for v in new_by_eid.values())

    merged_items_by_eid: Dict[int, List[Dict[str, Any]]] = {}
    merged_size_by_eid: Dict[int, int] = {}

    for eid in touched_eids:
        existing = existing_items_by_eid.get(eid, [])
        if replace_existing_for_plan_load_cases and plan_cases:
            existing = [it for it in existing if str(it.get("LCNAME", "")).strip() not in plan_cases]

        merged = list(existing)
        merged.extend(it.to_dict() for it in new_by_eid[eid])
        merged_items_by_eid[eid] = merged
        merged_size_by_eid[eid] = len(merged)

    req = 0
    sent_new = 0
    idx = 0
    put_payloads_for_debug: list[dict] = []

    while idx < len(touched_eids):
        batch: list[int] = []
        batch_items = 0

        while idx < len(touched_eids):
            eid = touched_eids[idx]
            elem_items = merged_size_by_eid[eid]

            if not batch and elem_items > max_items_per_put:
                batch = [eid]
                batch_items = elem_items
                idx += 1
                break

            if batch and (batch_items + elem_items > max_items_per_put):
                break

            batch.append(eid)
            batch_items += elem_items
            idx += 1

        assign = {str(eid): {"ITEMS": merged_items_by_eid[eid]} for eid in batch}
        payload = {"Assign": assign}

        req += 1
        new_count = sum(len(new_by_eid[eid]) for eid in batch)
        sent_new += new_count

        if progress:
            progress(req=req, elements=len(batch), new=new_count, sent=sent_new, total_new=total_new, total_items=batch_items)

        if debug is not None and getattr(debug, "enabled", False):
            put_payloads_for_debug.append(payload)

        resource.put_raw(payload)

    if debug is not None and getattr(debug, "enabled", False):
        dump_fn = getattr(debug, "dump_apply_payload", None)
        if callable(dump_fn):
            try:
                dump_fn(label=debug_label, put_payloads=put_payloads_for_debug)
            except Exception:
                pass

    logger.info("apply_beam_load_plan_to_midas done. Sent %s new items across %s requests.", sent_new, req)
    return df


__all__ = [
    "ExposureResolver",
    "compute_section_exposures",
    "get_section_properties_cached",
    "build_uniform_load_beam_load_plan_for_group",
    "build_line_load_plan_from_components",
    "build_pressure_plan_from_components",
    "convert_pressure_to_line_loads_by_exposure_depth",
    "apply_beam_load_plan_to_midas",
]
