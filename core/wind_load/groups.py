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
def _get_all_groups_cached() -> dict[str, Any]:
    """
    One-shot snapshot of /db/GRUP for this Python process.

    StructuralGroup.get_all() hits MIDAS once; the result is then reused
    for all later lookups.
    """
    raw = StructuralGroup.get_all() or {}
    return {str(k): v for k, v in raw.items()}


@lru_cache(maxsize=512)
def get_group_element_ids(group_name: str) -> list[int]:
    """
    Cached lookup: return element IDs for the given structural group name.

    Uses the in-memory /db/GRUP snapshot from _get_all_groups_cached(),
    so we only ever do ONE GET /db/GRUP per Python process.
    """
    group_name = str(group_name or "").strip()
    if not group_name:
        return []

    all_groups = _get_all_groups_cached()

    # Find the group entry with this NAME
    for entry in all_groups.values():
        name = (entry.get("NAME") or "").strip()
        if name != group_name:
            continue

        e_list = entry.get("E_LIST")
        if not e_list:
            return []

        # normalize to list[int] (same logic as StructuralGroup._to_int_list)
        if isinstance(e_list, str):
            return [int(x) for x in e_list.split() if x.strip().isdigit()]

        out: list[int] = []
        for x in e_list:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                pass
        return out

    return []


def clear_group_cache() -> None:
    """Optional helper (useful in tests / interactive sessions)."""
    _get_all_groups_cached.cache_clear()
    get_group_element_ids.cache_clear()


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
    "get_group_element_ids",
    "clear_group_cache",
    "build_plans_for_groups",
]
