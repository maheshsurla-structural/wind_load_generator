# core/wind_load/groups.py
from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable, Iterable, Mapping

import pandas as pd
from midas.resources.structural_group import StructuralGroup


# ---------------------------------------------------------------------------
# Cached MIDAS group -> element lookup
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_all_structural_groups_cached() -> dict[str, Any]:
    """
    One-shot snapshot of /db/GRUP for this Python process.

    StructuralGroup.get_all() hits MIDAS once; the result is then reused
    for all later lookups.
    """
    raw = StructuralGroup.get_all() or {}
    return {str(k): v for k, v in raw.items()}


@lru_cache(maxsize=512)
def get_structural_group_element_ids(structural_group_name: str) -> list[int]:
    """
    Cached lookup: return element IDs for the given structural group name.

    Uses the in-memory /db/GRUP snapshot from _get_all_structural_groups_cached(),
    so we only ever do ONE GET /db/GRUP per Python process.
    """
    target_group_name = str(structural_group_name or "").strip()
    if not target_group_name:
        return []

    structural_group_records = _get_all_structural_groups_cached()

    # Find the group record with matching NAME
    for structural_group_record in structural_group_records.values():
        record_group_name = str(structural_group_record.get("NAME") or "").strip()
        if record_group_name != target_group_name:
            continue

        raw_element_list = structural_group_record.get("E_LIST")
        if not raw_element_list:
            return []

        # Normalize to list[int] (same logic as StructuralGroup._to_int_list)
        if isinstance(raw_element_list, str):
            # Example: "1 2 3"
            return [int(token) for token in raw_element_list.split() if token.strip().isdigit()]

        element_ids: list[int] = []
        for item in raw_element_list:
            try:
                element_ids.append(int(item))
            except (TypeError, ValueError):
                pass

        return element_ids

    return []


def clear_group_cache() -> None:
    """Optional helper (useful in tests / interactive sessions)."""
    _get_all_structural_groups_cached.cache_clear()
    get_structural_group_element_ids.cache_clear()


# ---------------------------------------------------------------------------
# Common “run for many groups” loop (plan runner)
# ---------------------------------------------------------------------------

def build_plans_for_groups(
    *,
    groups: Iterable[str],
    build_components_for_group: Callable[[str], pd.DataFrame],
    build_plan_for_group: Callable[[str, pd.DataFrame, list[int] | None], pd.DataFrame],
    group_members: Mapping[str, list[int]] | None = None,
    dbg: Any = None,
    label_prefix: str = "",
    dump_components: bool = False,
) -> tuple[list[pd.DataFrame], bool]:
    """
    Common loop:
      - iterate groups
      - build components
      - optionally dump components
      - build plan
      - optionally dump plan
    """
    group_members = group_members or {}

    plans: list[pd.DataFrame] = []
    any_applied = False

    for g in groups:
        group_name = str(g).strip()
        if not group_name:
            continue

        element_ids = group_members.get(group_name) or None

        comp = build_components_for_group(group_name)
        if comp is None or comp.empty:
            continue

        if dump_components and dbg is not None and getattr(dbg, "enabled", False):
            dump_fn = getattr(dbg, "dump_components", None)
            if callable(dump_fn):
                dump_fn(comp, label=f"{label_prefix}COMPONENTS_{group_name}")

        plan = build_plan_for_group(group_name, comp, element_ids)
        if plan is None or plan.empty:
            continue

        if dbg is not None and getattr(dbg, "enabled", False):
            dbg.dump_plan(plan, label=f"{label_prefix}{group_name}", split_per_case=True)

        plans.append(plan)
        any_applied = True

    return plans, any_applied


__all__ = [
    "get_structural_group_element_ids",
    "clear_group_cache",
    "build_plans_for_groups",
]
