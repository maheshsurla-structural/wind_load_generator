# core/wind_load/group_cache.py
from __future__ import annotations

from functools import lru_cache
from typing import List, Dict, Any

from midas.resources.structural_group import StructuralGroup


@lru_cache(maxsize=1)
def _get_all_groups_cached() -> Dict[str, Any]:
    """
    One-shot snapshot of /db/GRUP for this Python process.

    StructuralGroup.get_all() hits MIDAS once; the result is then reused
    for all later lookups.
    """
    raw = StructuralGroup.get_all() or {}
    # normalize keys to str just in case
    return {str(k): v for k, v in raw.items()}


@lru_cache(maxsize=512)
def get_group_element_ids(group_name: str) -> List[int]:
    """
    Cached lookup: return element IDs for the given structural group name.

    Uses the in-memory /db/GRUP snapshot from _get_all_groups_cached(),
    so we only ever do ONE GET /db/GRUP per Python process.
    """
    all_groups = _get_all_groups_cached()

    # Find the group entry with this NAME
    for entry in all_groups.values():
        name = (entry.get("NAME") or "").strip()
        if name == group_name:
            e_list = entry.get("E_LIST")

            # normalize to list[int] (same logic as StructuralGroup._to_int_list)
            if not e_list:
                return []
            if isinstance(e_list, str):
                return [int(x) for x in e_list.split() if x.strip().isdigit()]
            return [int(x) for x in e_list]

    # not found
    return []
