# tests\pretension_to_nodal.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional, Literal
import numpy as np

from core.geometry.midas_element_local_axes import MidasElementLocalAxes
from midas.resources.nodal_load import NodalLoadResource, NodalLoadItem


MergeMode = Literal["replace", "append"]


@dataclass(frozen=True)
class PretensionAsNodalResult:
    elem_id: int
    n1: int
    n2: int
    ex: np.ndarray            # (3,)
    F_n1: np.ndarray          # (3,) global force at node 1
    F_n2: np.ndarray          # (3,) global force at node 2


def _extract_n1_n2_from_elem_record(elem_rec: dict) -> Tuple[int, int]:
    raw_ids = elem_rec.get("NODE", None)
    if not isinstance(raw_ids, (list, tuple)):
        raise ValueError(f"Element record has no valid NODE list: {elem_rec}")

    node_ids = [int(n) for n in raw_ids if isinstance(n, (int, float)) and n > 0]
    if len(node_ids) < 2:
        raise ValueError(f"Element has <2 valid node ids: {elem_rec}")

    return node_ids[0], node_ids[1]


def compute_equivalent_nodal_forces_for_pretension(
    elem_id: int,
    pretension: float,
    *,
    helper: Optional[MidasElementLocalAxes] = None,
    debug: bool = False,
) -> PretensionAsNodalResult:
    """
    Equivalent nodal forces for a PRETENSIONED CABLE/TRUSS as it acts on the STRUCTURE.

    pretension > 0 => tension
    Forces pull the two end nodes toward each other:
      F@N1 = +P * ex
      F@N2 = -P * ex
    """
    if helper is None:
        helper = MidasElementLocalAxes.from_midas(debug=debug)

    elem_rec = helper.get_element(elem_id)
    n1, n2 = _extract_n1_n2_from_elem_record(elem_rec)

    axes = helper.compute_local_axes_for_element(elem_id)
    ex = np.asarray(axes.ex, dtype=float)
    ex /= np.linalg.norm(ex)

    P = float(pretension)

    # ✅ Correct sign for "cable pulls nodes toward each other"
    F_n1 = +P * ex
    F_n2 = -P * ex

    if debug:
        helper.printer(f"[Pretension] elem={elem_id}, P={P}")
        helper.printer(f"  n1={n1}, n2={n2}")
        helper.printer(f"  ex={ex}")
        helper.printer(f"  F@n1={F_n1}  (FX,FY,FZ)")
        helper.printer(f"  F@n2={F_n2}  (FX,FY,FZ)")
        helper.printer(f"  check sum={F_n1 + F_n2} (should be ~0)")

    return PretensionAsNodalResult(
        elem_id=int(elem_id),
        n1=n1,
        n2=n2,
        ex=ex,
        F_n1=F_n1,
        F_n2=F_n2,
    )


def apply_pretension_as_nodal_load(
    elem_id: int,
    pretension: float,
    *,
    lcname: str = "Nodal Load",
    group_name: str = "",          # ✅ avoid MIDAS error unless group exists
    mode: MergeMode = "append",
    debug: bool = False,
) -> PretensionAsNodalResult:
    """
    Computes and writes equivalent nodal loads for pretension:
      - one CNLD item at n1
      - one CNLD item at n2
      - moments are zero (truss/cable)
    """
    helper = MidasElementLocalAxes.from_midas(debug=debug)
    res = compute_equivalent_nodal_forces_for_pretension(
        elem_id, pretension, helper=helper, debug=debug
    )

    item1 = NodalLoadItem(
        ID=NodalLoadResource.next_item_id(res.n1),
        LCNAME=lcname,
        GROUP_NAME=group_name,
        FX=float(res.F_n1[0]),
        FY=float(res.F_n1[1]),
        FZ=float(res.F_n1[2]),
        MX=0.0, MY=0.0, MZ=0.0,
    )

    item2 = NodalLoadItem(
        ID=NodalLoadResource.next_item_id(res.n2),
        LCNAME=lcname,
        GROUP_NAME=group_name,
        FX=float(res.F_n2[0]),
        FY=float(res.F_n2[1]),
        FZ=float(res.F_n2[2]),
        MX=0.0, MY=0.0, MZ=0.0,
    )

    NodalLoadResource.upsert_node_items(res.n1, [item1], mode=mode)
    NodalLoadResource.upsert_node_items(res.n2, [item2], mode=mode)

    return res
