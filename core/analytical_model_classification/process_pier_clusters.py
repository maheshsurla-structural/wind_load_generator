from midas import get_nodes, get_elements
from .classify_substructure_elements import classify_substructure_elements
from .classify_pier_and_pier_cap_elements import classify_pier_and_pier_cap_elements

def process_pier_clusters(pier_clusters_raw, substructure_elements, reference_height, nodes=None, elements=None):
    if elements is None:
        elements = get_elements()
    if nodes is None:
        nodes = get_nodes()
    pier_clusters = {}
    for label, elements_list in pier_clusters_raw.items():
        subset = {eid: substructure_elements[eid] for eid in elements_list}
        sub_above, sub_below = classify_substructure_elements(subset, reference_height, node_data=nodes)
        pier_caps, piers = classify_pier_and_pier_cap_elements(sub_below, elements=elements, nodes=nodes)
        pier_clusters[f"{label}_SubAbove"] = sub_above
        pier_clusters[f"{label}_PierCap"] = pier_caps
        pier_clusters[f"{label}_Pier"] = piers
    return pier_clusters