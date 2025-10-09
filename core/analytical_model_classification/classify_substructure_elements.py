from midas import get_nodes

def classify_substructure_elements(substructure_elements, reference_height, node_data=None):
    if node_data is None:
        node_data = get_nodes()
    node_data = node_data.get("NODE", {}) if "NODE" in node_data else node_data
    substructure_above_deck = {}
    substructure_below_deck = {}
    for eid, elem in substructure_elements.items():
        node_heights = [node_data[str(nid)]["Z"] for nid in elem["NODE"] if str(nid) in node_data]
        if not node_heights:
            continue
        if max(node_heights) >= reference_height:
            substructure_above_deck[eid] = elem
        else:
            substructure_below_deck[eid] = elem
    return substructure_above_deck, substructure_below_deck