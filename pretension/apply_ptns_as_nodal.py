# core/midas/apply_ptns_as_nodal.py
from __future__ import annotations

from typing import List, Optional
from dataclasses import dataclass

from core.geometry.midas_element_local_axes import MidasElementLocalAxes
from pretension.pretension_to_nodal import (
    compute_equivalent_nodal_forces_for_pretension,
)
from midas.resources.nodal_load import NodalLoadResource, NodalLoadItem
from midas.resources.pretension import PretensionResource, PretensionItem
from midas.resources.load_group import LoadGroup
from midas.resources.static_load_case import StaticLoadCase  # your /db/STLD resource


@dataclass(frozen=True)
class PTNSToNodalResult:
    elem_id: int
    source_lcname: str
    target_lcname: str
    tension: float
    n1: int
    n2: int


def ensure_load_case_exists(target_lcname: str, *, source_lcname: Optional[str] = None) -> None:
    """
    Create/Upsert a static load case for nodal verification.
    We try to copy TYPE from source if found; else default to PS.
    """
    load_type = "PS"  # Prestress default

    if source_lcname:
        # Try to find source case and copy its TYPE if it exists
        all_cases = StaticLoadCase.get_all()
        for v in all_cases.values():
            if (v.get("NAME") or "").strip() == source_lcname:
                load_type = (v.get("TYPE") or "PS")
                break

    StaticLoadCase.upsert(name=target_lcname, load_type=load_type, desc=f"Auto from {source_lcname or ''}".strip())


def ensure_load_group_exists(group_name: str) -> None:
    """
    If group_name is not empty, ensure it exists in /db/LDGR.
    (Prevents the CNLD GROUP_NAME 'does not exist' error.)
    """
    g = (group_name or "").strip()
    if not g:
        return
    # upsert is safe
    LoadGroup.upsert(g)


def apply_ptns_element_as_nodal(
    elem_id: int,
    *,
    suffix: str = "-nodal",
    mode: str = "append",
    use_group_from_ptns: bool = False,
    debug: bool = True,
) -> List[PTNSToNodalResult]:
    """
    For the given element:
      - read PTNS items for that element
      - for each item (LCNAME, GROUP_NAME, TENSION):
          create/ensure load case LCNAME + suffix
          convert TENSION to nodal loads
          write nodal loads to CNLD under the new load case
    """
    helper = MidasElementLocalAxes.from_midas(debug=debug)

    ptns_items: List[PretensionItem] = PretensionResource.get_items_for_element(elem_id)
    if not ptns_items:
        raise RuntimeError(f"No pretension (PTNS) items found for element {elem_id}")

    out: List[PTNSToNodalResult] = []

    for it in ptns_items:
        source_lc = it.LCNAME
        target_lc = f"{source_lc}{suffix}"

        # 1) Ensure the verification load case exists
        ensure_load_case_exists(target_lc, source_lcname=source_lc)

        # 2) Decide group name behavior
        if use_group_from_ptns:
            group_name = (it.GROUP_NAME or "").strip()
            ensure_load_group_exists(group_name)
        else:
            group_name = ""  # safest

        # 3) Compute equivalent nodal forces from tension
        res = compute_equivalent_nodal_forces_for_pretension(
            elem_id=elem_id,
            pretension=it.TENSION,
            helper=helper,
            debug=debug,
        )

        # 4) Write CNLD at n1 and n2, using target LCNAME
        item1 = NodalLoadItem(
            ID=NodalLoadResource.next_item_id(res.n1),
            LCNAME=target_lc,
            GROUP_NAME=group_name,
            FX=float(res.F_n1[0]), FY=float(res.F_n1[1]), FZ=float(res.F_n1[2]),
            MX=0.0, MY=0.0, MZ=0.0,
        )
        item2 = NodalLoadItem(
            ID=NodalLoadResource.next_item_id(res.n2),
            LCNAME=target_lc,
            GROUP_NAME=group_name,
            FX=float(res.F_n2[0]), FY=float(res.F_n2[1]), FZ=float(res.F_n2[2]),
            MX=0.0, MY=0.0, MZ=0.0,
        )

        NodalLoadResource.upsert_node_items(res.n1, [item1], mode=mode)
        NodalLoadResource.upsert_node_items(res.n2, [item2], mode=mode)

        out.append(
            PTNSToNodalResult(
                elem_id=elem_id,
                source_lcname=source_lc,
                target_lcname=target_lc,
                tension=it.TENSION,
                n1=res.n1,
                n2=res.n2,
            )
        )

    return out
