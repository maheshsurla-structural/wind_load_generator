# core/geometry/midas_element_local_axes.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional, Callable

from midas import elements as midas_elements, nodes as midas_nodes

from core.geometry.element_local_axes import (
    compute_element_local_axes,
    LocalAxes,
)


# ---------------------------------------------------------------------------
# Low-level helpers (pure functions, no MIDAS side-effects)
# ---------------------------------------------------------------------------

def _normalise_elements_dict(
    elements_in_model: Dict[str, Any] | None,
) -> Dict[str, Dict[str, Any]]:
    """
    Return a dict mapping element-id (as *string*) -> element record.

    Handles both of these common layouts from MIDAS:

        {"1": {...}, "2": {...}, ...}
        {"ELEM": {"1": {...}, "2": {...}, ...}}
    """
    if elements_in_model is None:
        elements_in_model = {}

    if "ELEM" in elements_in_model and isinstance(elements_in_model["ELEM"], dict):
        elements_in_model = elements_in_model["ELEM"]

    # Type hint: assume leaf values are dicts
    return elements_in_model  # type: ignore[return-value]


def _normalise_nodes_dict(
    nodes_in_model: Dict[str, Any] | None,
) -> Dict[str, Dict[str, Any]]:
    """
    Return a dict mapping node-id (as *string*) -> node record.

    Handles both of these layouts:

        {"1": {"X":..., "Y":..., "Z":...}, ...}
        {"NODE": {"1": {"X":..., "Y":..., "Z":...}, ...}}
    """
    if nodes_in_model is None:
        nodes_in_model = {}

    if "NODE" in nodes_in_model and isinstance(nodes_in_model["NODE"], dict):
        nodes_in_model = nodes_in_model["NODE"]

    return nodes_in_model  # type: ignore[return-value]


def _extract_node_coords(node_record: Dict[str, Any]) -> Tuple[float, float, float]:
    """
    Convert a node record to (x, y, z) floats.

    Assumes MIDAS-style keys "X", "Y", "Z".
    """
    try:
        x = float(node_record["X"])
        y = float(node_record["Y"])
        z = float(node_record["Z"])
    except KeyError as exc:
        raise KeyError(
            f"Node record missing coordinate {exc.args[0]!r}: {node_record}"
        ) from exc

    return x, y, z


def _extract_element_node_ids(elem_record: Dict[str, Any]) -> Tuple[int, int]:
    """
    Extract (n1_id, n2_id) from an element record.

    In your model, `elem_record["NODE"]` is a list of node IDs (ints),
    possibly including 0 as a dummy. We follow the same pattern as
    get_query_element: keep > 0 and take the first two.
    """
    if "NODE" not in elem_record:
        raise KeyError(f"Element record has no 'NODE' field: {elem_record}")

    raw_ids = elem_record["NODE"]

    if not isinstance(raw_ids, (list, tuple)):
        raise TypeError(f"Element 'NODE' field is not list/tuple: {raw_ids!r}")

    node_ids = [nid for nid in raw_ids if isinstance(nid, (int, float)) and nid > 0]

    if len(node_ids) < 2:
        raise ValueError(
            f"Element has fewer than 2 valid node IDs (>0): {elem_record}"
        )

    n1_id, n2_id = int(node_ids[0]), int(node_ids[1])
    return n1_id, n2_id


# ---------------------------------------------------------------------------
# Core abstraction: MidasElementLocalAxes
# ---------------------------------------------------------------------------

@dataclass
class MidasElementLocalAxes:
    """
    Helper for computing local axes for MIDAS beam elements.

    Responsibilities:
      - Hold normalised element and node dictionaries.
      - Provide convenience accessors to those tables.
      - Compute LocalAxes for a given element ID.
      - Optional structured debug logging.
    """

    elements: Dict[str, Dict[str, Any]]
    nodes: Dict[str, Dict[str, Any]]

    # Debugging controls
    debug: bool = False
    printer: Callable[[str], None] = print

    # ------------------------------------------------------------------ #
    # Constructors
    # ------------------------------------------------------------------ #

    @classmethod
    def from_midas(
        cls,
        *,
        debug: bool = False,
        printer: Callable[[str], None] = print,
    ) -> "MidasElementLocalAxes":
        """
        Build an instance by calling midas.elements.get_all() and
        midas.nodes.get_all(), then normalising the structure.
        """
        raw_elems = midas_elements.get_all() or {}
        raw_nodes = midas_nodes.get_all() or {}

        elems = _normalise_elements_dict(raw_elems)
        nds = _normalise_nodes_dict(raw_nodes)

        return cls(elements=elems, nodes=nds, debug=debug, printer=printer)

    # ------------------------------------------------------------------ #
    # Internal logging helper
    # ------------------------------------------------------------------ #

    def _log(self, msg: str) -> None:
        if self.debug:
            self.printer(msg)

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #

    def get_element(self, elem_id: int | str) -> Dict[str, Any]:
        eid_str = str(elem_id)
        elem = self.elements.get(eid_str)
        if not elem:
            raise KeyError(f"Element {eid_str} not found in MIDAS ELEM table.")
        return elem

    def get_node(self, node_id: int | str) -> Dict[str, Any]:
        nid_str = str(node_id)
        node = self.nodes.get(nid_str)
        if not node:
            raise KeyError(f"Node {nid_str} not found in MIDAS NODE table.")
        return node

    # ------------------------------------------------------------------ #
    # Geometry: element local axes
    # ------------------------------------------------------------------ #

    def compute_local_axes_for_element(
        self,
        elem_id: int | str,
        beta_deg: Optional[float] = None,
    ) -> LocalAxes:
        """
        Compute LocalAxes for a given beam element.

        - Uses N1→N2 from the element's NODE list.
        - Uses ANGLE (beta) from the element if not explicitly passed.
        """
        elem_rec = self.get_element(elem_id)
        n1_id, n2_id = _extract_element_node_ids(elem_rec)

        # Decide which beta we actually use
        if beta_deg is None:
            raw_beta = elem_rec.get("ANGLE", elem_rec.get("BETA", 0.0))
            beta_deg = float(raw_beta)
            beta_source = "element"
        else:
            beta_source = "argument"

        # Header line for this element
        self._log(
            f"[LocalAxes] Element {elem_id}: beta = {beta_deg}° ({beta_source})"
        )

        n1_rec = self.get_node(n1_id)
        n2_rec = self.get_node(n2_id)

        n1 = _extract_node_coords(n1_rec)
        n2 = _extract_node_coords(n2_rec)

        axes = compute_element_local_axes(n1, n2, beta_deg)

        # Detailed info
        self._log(f"  N1 id = {n1_id}, N2 id = {n2_id}")
        self._log(f"  N1 = {n1}")
        self._log(f"  N2 = {n2}")
        self._log(f"  ex = {axes.ex}")
        self._log(f"  ey = {axes.ey}")
        self._log(f"  ez = {axes.ez}")

        return axes



# ---------------------------------------------------------------------------
# Thin functional wrappers (for quick scripts / backwards compatibility)
# ---------------------------------------------------------------------------

def compute_local_axes_for_element(
    elem_id: int | str,
    beta_deg: Optional[float] = None,
    *,
    elements_in_model: Optional[Dict[str, Dict[str, Any]]] = None,
    nodes_in_model: Optional[Dict[str, Dict[str, Any]]] = None,
    debug: bool = False,
    printer: Callable[[str], None] = print,
) -> LocalAxes:
    """
    Convenience functional API that mirrors your previous signature.

    For many calls / higher performance, prefer creating a
    MidasElementLocalAxes instance once and reusing it.
    """
    if elements_in_model is None or nodes_in_model is None:
        helper = MidasElementLocalAxes.from_midas(debug=debug, printer=printer)
    else:
        helper = MidasElementLocalAxes(
            elements=_normalise_elements_dict(elements_in_model),
            nodes=_normalise_nodes_dict(nodes_in_model),
            debug=debug,
            printer=printer,
        )

    return helper.compute_local_axes_for_element(elem_id, beta_deg)


def debug_print_element_axes(
    elem_id: int | str,
    beta_deg: Optional[float] = None,
    *,
    elements_in_model: Optional[Dict[str, Dict[str, Any]]] = None,
    nodes_in_model: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """
    One-line helper: print ex, ey, ez and the transformation matrices.

    This builds a MidasElementLocalAxes helper with debug=True and uses it.
    """
    if elements_in_model is None or nodes_in_model is None:
        helper = MidasElementLocalAxes.from_midas(debug=True)
    else:
        helper = MidasElementLocalAxes(
            elements=_normalise_elements_dict(elements_in_model),
            nodes=_normalise_nodes_dict(nodes_in_model),
            debug=True,
        )

    axes = helper.compute_local_axes_for_element(elem_id, beta_deg)

    print(f"\n=== Local axes for element {elem_id} ===")
    print(f"ex (local x, N1->N2, global coords): {axes.ex}")
    print(f"ey (local y, global coords)        : {axes.ey}")
    print(f"ez (local z, global coords)        : {axes.ez}")
    print("\nT_gl_to_loc (GLOBAL -> LOCAL):")
    print(axes.T_gl_to_loc)
    print("\nT_loc_to_gl (LOCAL -> GLOBAL):")
    print(axes.T_loc_to_gl)
    print("=====================================\n")
