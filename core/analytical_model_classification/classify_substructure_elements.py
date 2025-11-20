# core/analytical_model_classification/classify_substructure_elements.py

from midas import nodes


def classify_substructure_elements(
    substructure_elements,
    reference_height,
    node_data=None,
):
    # Pull node data if caller did not pass it
    if node_data is None:
        node_data = nodes.get_all()

    # Handle the case where nodes.get_all() returns {"NODE": {...}}
    if isinstance(node_data, dict) and "NODE" in node_data:
        node_data = node_data["NODE"]

    substructure_above_deck = {}
    substructure_below_deck = {}

    # If we have no reference height, we can't classify by height.
    # Safest behaviour: treat everything as "below deck" (or just return empty above/below).
    if reference_height is None:
        # Option A: everything goes below
        # return {}, dict(substructure_elements)

        # Option B (probably better for now): don't classify at all
        return {}, {}

    for eid, elem in substructure_elements.items():
        node_heights = []

        for nid in elem.get("NODE", []):
            # Ignore dummy node IDs like 0
            if nid <= 0:
                continue

            nd = node_data.get(str(nid))
            if not nd:
                continue

            z = nd.get("Z")
            if z is None:
                # Skip nodes whose Z is not defined
                continue

            node_heights.append(z)

        # If we couldn't get any valid heights for this element, skip it
        if not node_heights:
            continue

        max_z = max(node_heights)

        if max_z >= reference_height:
            substructure_above_deck[eid] = elem
        else:
            substructure_below_deck[eid] = elem

    return substructure_above_deck, substructure_below_deck
