# core/analytical_model_classification/process_pier_clusters.py

from midas import elements, nodes
from .classify_substructure_elements import classify_substructure_elements
from .classify_pier_and_pier_cap_elements import (
    classify_pier_and_pier_cap_elements,
)


def process_pier_clusters(
    pier_clusters_raw,
    substructure_elements,
    reference_height,
    *,
    nodes_in_model=None,
    elements_in_model=None,
    suffix_above: str = "_SubAbove",   # from NamingRules
):
    # Load model data if caller didn't provide it
    if elements_in_model is None:
        elements_in_model = elements.get_all()
    if nodes_in_model is None:
        nodes_in_model = nodes.get_all()

    pier_clusters = {}

    for label, elements_list in pier_clusters_raw.items():
        # restrict substructure_elements to just this cluster's elements
        subset = {eid: substructure_elements[eid] for eid in elements_list}

        # classify which parts of that subset are above vs below deck
        sub_above, sub_below = classify_substructure_elements(
            subset,
            reference_height,
            node_data=nodes_in_model,
        )

        # within whatever is below deck, split pier caps vs piers
        pier_caps, piers = classify_pier_and_pier_cap_elements(
            sub_below,
            elements_in_model=elements_in_model,
            nodes_in_model=nodes_in_model,
        )

        pier_clusters[f"{label}{suffix_above}"] = sub_above
        pier_clusters[f"{label}_PierCap"] = pier_caps
        pier_clusters[f"{label}_Pier"] = piers

    return pier_clusters
