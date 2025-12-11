# core/wind_load/group_cache.py
from __future__ import annotations

from functools import lru_cache
from typing import List
from midas.resources.structural_group import StructuralGroup


@lru_cache(maxsize=512)
def get_group_element_ids(group_name: str) -> List[int]:
    """
    Cached wrapper around StructuralGroup.get_elements_by_name().

    Returns a list of int element IDs for the given group.
    If the group has no elements, returns [].

    MIDAS is only hit once per group name in this Python process.
    """
    ids = StructuralGroup.get_elements_by_name(group_name) or []
    return [int(e) for e in ids]
