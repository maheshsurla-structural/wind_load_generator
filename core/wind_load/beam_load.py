# core/wind_load/beam_load.py
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from collections import defaultdict
from typing import Any, Dict, List, Sequence, Tuple, Iterable, Optional

import logging
import numpy as np
import pandas as pd

from midas import elements, get_section_properties
from midas.resources.element_beam_load import BeamLoadItem, BeamLoadResource

from core.wind_load.debug import DebugSink
from core.wind_load.groups import get_structural_group_element_ids


logger = logging.getLogger(__name__)
EPS = 1e-9


# =============================================================================
# Domain: exposures
# =============================================================================

def compute_section_exposures(
    section_properties,
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: dict | None = None,
    as_dataframe: bool = True,
) -> pd.DataFrame | dict:
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
            (extra_exposure_y_by_id.get(pid, extra_exposure_y_default) for pid in pids_arr),
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
        return df

    return {pids_arr[i]: (float(exposure_y[i]), float(exposure_z[i])) for i in range(pids_arr.size)}


# =============================================================================
# Cached MIDAS reads + mapping helpers
# =============================================================================

@lru_cache(maxsize=1)
def _get_all_elements_cached() -> dict:
    return elements.get_all() or {}

@lru_cache(maxsize=1)
def get_section_properties_cached():
    return get_section_properties()

def _get_element_to_section_map(element_ids: Sequence[int]) -> Dict[int, int]:
    out: Dict[int, int] = {}
    all_elem_data = _get_all_elements_cached()

    for eid in element_ids:
        edata = all_elem_data.get(str(int(eid)))
        if not edata:
            continue

        sect_id = edata.get("SECT")
        if sect_id is None:
            continue

        try:
            out[int(eid)] = int(sect_id)
        except (TypeError, ValueError):
            continue

    return out

def _validate_axis(exposure_axis: str) -> str:
    ax = str(exposure_axis).strip().lower()
    if ax not in {"y", "z"}:
        raise ValueError(f"exposure_axis must be 'y' or 'z', got {exposure_axis!r}")
    return ax


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
) -> pd.DataFrame:
    rows: list[dict] = []

    for eid, depth in (depth_by_eid or {}).items():
        q = float(pressure) * float(depth)  # ksf * ft = k/ft
        if abs(q) < EPS:
            continue
        rows.append(
            {
                "element_id": int(eid),
                "line_load": float(q),
                "load_case": str(load_case_name),
                "load_direction": str(udl_direction),
                "load_group": str(load_group_name or load_case_name),
                "group_name": str(group_name),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values("element_id", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def resolve_depths_for_group(
    *,
    group_name: str,
    exposure_axis: str = "y",
    extra_exposure_y_default: float = 0.0,
    extra_exposure_y_by_id: Dict[int, float] | None = None,
) -> Dict[int, float]:
    ax = _validate_axis(exposure_axis)

    element_ids = list(get_structural_group_element_ids(group_name))
    elem_to_sect = _get_element_to_section_map(element_ids)

    section_props_raw = get_section_properties_cached()
    exposures_df = compute_section_exposures(
        section_props_raw,
        extra_exposure_y_default=extra_exposure_y_default,
        extra_exposure_y_by_id=extra_exposure_y_by_id,
        as_dataframe=True,
    )

    # Normalize index types for reliable membership checks
    try:
        exposures_df.index = exposures_df.index.astype(int)
    except ValueError:
        pass

    depth_col = "exposure_z" if ax == "z" else "exposure_y"

    depth_by_eid: Dict[int, float] = {}
    for eid, sect_id in elem_to_sect.items():
        if sect_id in exposures_df.index:
            depth_by_eid[int(eid)] = float(exposures_df.loc[sect_id, depth_col])

    return depth_by_eid

# def build_uniform_pressure_beam_load_plan(
#     *,
#     group_name: str,
#     load_case_name: str,
#     pressure: float,
#     udl_direction: str = "GZ",
#     load_group_name: str | None = None,
#     exposure_axis: str = "y",
#     extra_exposure_y_default: float = 0.0,
#     extra_exposure_y_by_id: Dict[int, float] | None = None,
# ) -> pd.DataFrame:
#     depth_by_eid = resolve_depths_for_group(
#         group_name=group_name,
#         exposure_axis=exposure_axis,
#         extra_exposure_y_default=extra_exposure_y_default,
#         extra_exposure_y_by_id=extra_exposure_y_by_id,
#     )
#     return convert_pressure_to_line_loads_by_exposure_depth(
#         group_name=group_name,
#         load_case_name=load_case_name,
#         pressure=pressure,
#         udl_direction=udl_direction,
#         depth_by_eid=depth_by_eid,
#         load_group_name=load_group_name or load_case_name,
#     )


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
    if element_ids is None:
        element_ids = get_structural_group_element_ids(group_name)

    rows: list[dict] = []
    for eid in [int(e) for e in element_ids]:
        rows.append(
            {
                "element_id": eid,
                "line_load": float(line_load),
                "load_case": str(load_case_name),
                "load_direction": str(udl_direction),
                "load_group": str(load_group_name or load_case_name),
                "group_name": str(group_name),
                "eccentricity": float(eccentricity),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df.sort_values("element_id", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


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

def _normalize_plan_df(plan_df: pd.DataFrame, aggregate_duplicates: bool) -> pd.DataFrame:
    required = {"element_id", "line_load", "load_case", "load_direction", "load_group"}
    missing = required - set(plan_df.columns)
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

    df = df.sort_values(["load_case", "load_direction", "element_id"], kind="stable").reset_index(drop=True)
    return df

def apply_beam_load_plan_to_midas(
    plan_df: pd.DataFrame,
    *,
    max_items_per_put: int = 5000,
    debug: DebugSink | None = None,
    debug_label: str = "WIND_ASSIGN",
    replace_existing_for_plan_load_cases: bool = True,
    aggregate_duplicates: bool = True,
    resource: Any = BeamLoadResource,   # dependency injection hook
) -> pd.DataFrame:
    """
    Apply a beam-load plan to MIDAS (/db/bmld) using safe merge-per-element writes.

    DEBUG BEHAVIOR (as requested):
      - No per-case plan dumps
      - No per-chunk dumps
      - If debug.enabled and debug has dump_apply_payload(), write exactly ONE JSON at the end
        containing the exact PUT payload(s) sent to MIDAS.
    """
    if plan_df is None or plan_df.empty:
        logger.info("apply_beam_load_plan_to_midas: plan_df empty; nothing to send.")
        return plan_df

    max_items_per_put = max(int(max_items_per_put), 1)
    df = _normalize_plan_df(plan_df, aggregate_duplicates=aggregate_duplicates)

    # -----------------------------
    # 1) Read existing /db/bmld once
    # -----------------------------
    raw_existing = resource.get_raw() or {}

    existing_items_by_eid: Dict[int, List[Dict[str, Any]]] = {}
    for eid_str, elem_block in raw_existing.items():
        try:
            eid = int(eid_str)
        except (TypeError, ValueError):
            continue
        existing_items_by_eid[eid] = list(((elem_block or {}).get("ITEMS", []) or []))

    # -----------------------------
    # 2) Per-element next-id map once
    # -----------------------------
    next_id_by_eid = _next_id_by_element_from_raw(raw_existing)

    def alloc_id(eid: int) -> int:
        nxt = next_id_by_eid.get(eid, 1)
        next_id_by_eid[eid] = nxt + 1
        return nxt

    plan_cases = set(df["load_case"].astype(str).str.strip())

    # -----------------------------
    # 3) Build NEW items (grouped by element)
    # -----------------------------
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
    total_new_rows = sum(len(v) for v in new_by_eid.values())

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
    # 5) PUT in batches: sum(ITEMS) <= max_items_per_put
    #    Never split an element across PUTs.
    # -----------------------------
    sent_new = 0
    req = 0
    idx = 0

    # ✅ Collect exact payloads sent to MIDAS (for ONE final debug JSON)
    put_payloads_for_debug: list[dict] = []

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
        sent_preview = sent_new + new_count

        print(
            f"[apply_beam_load_plan_to_midas] PUT #{req} | "
            f"elements={len(batch)} | "
            f"NEW={new_count} (cum {sent_preview}/{total_new_rows}) | "
            f"TOTAL ITEMS={batch_items} | "
            f"limit={max_items_per_put}",
            flush=True,
        )

        payload = {"Assign": assign}

        # ✅ store the exact payloads (only if debug enabled)
        if debug is not None and getattr(debug, "enabled", False):
            put_payloads_for_debug.append(payload)

        resource.put_raw(payload)
        sent_new += new_count

    # ✅ dump ONE file at the end (if available)
    if debug is not None and getattr(debug, "enabled", False):
        dump_fn = getattr(debug, "dump_apply_payload", None)
        if callable(dump_fn):
            try:
                dump_fn(label=debug_label, put_payloads=put_payloads_for_debug)
            except Exception:
                # debug must never break apply
                pass

    logger.info(
        "apply_beam_load_plan_to_midas done. Sent %s new items across %s requests.",
        sent_new,
        req,
    )
    return df




__all__ = [
    "compute_section_exposures",
    "get_section_properties_cached",
    "_get_element_to_section_map",
    "resolve_depths_for_group",
    "convert_pressure_to_line_loads_by_exposure_depth",
    # "build_uniform_pressure_beam_load_plan",
    "build_uniform_load_beam_load_plan_for_group",
    "apply_beam_load_plan_to_midas",
]
