# core/wind_load/group_runner.py
from __future__ import annotations

from typing import Callable, Iterable, Mapping, Any
import pandas as pd


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


__all__ = ["build_plans_for_groups"]
