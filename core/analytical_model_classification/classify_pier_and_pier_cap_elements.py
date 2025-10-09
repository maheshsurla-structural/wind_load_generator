# core/analytical_model_classification/classify_pier_and_pier_cap_elements.py

from midas import get_query_element, get_nodes, get_elements

def classify_pier_and_pier_cap_elements(substructure_below_deck, angle_xy_threshold=15, elements=None, nodes=None):
    if elements is None:
        elements = get_elements()
    if nodes is None:
        nodes = get_nodes()
    pier_caps = {}
    piers = {}
    for element_id in substructure_below_deck:
        info = get_query_element(element_id, elements=elements, nodes=nodes)
        if not info:
            continue
        angle_xy = info["Angles to Global Planes [XY, XZ, YZ]"][0]
        if angle_xy <= angle_xy_threshold:
            pier_caps[element_id] = substructure_below_deck[element_id]
        else:
            piers[element_id] = substructure_below_deck[element_id]
    return pier_caps, piers