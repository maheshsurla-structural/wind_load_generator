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
    pier_frames = []   # NEW: list of {pier_group, cap_group, above_group}

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

        # Concrete group names for this cluster
        above_label = f"{label}{suffix_above}"
        cap_label   = f"{label}_PierCap"
        pier_label  = f"{label}_Pier"

        # Only register non-empty groups
        if sub_above:
            pier_clusters[above_label] = sub_above
        if pier_caps:
            pier_clusters[cap_label] = pier_caps
        if piers:
            pier_clusters[pier_label] = piers

        # Build one frame for this cluster if we have a pier (axes come from pier)
        if piers:
            frame = {
                "pier_group": pier_label,
                "cap_group": cap_label if pier_caps else None,
                "above_group": above_label if sub_above else None,
            }
            pier_frames.append(frame)

    # IMPORTANT: now we return *both*
    return pier_clusters, pier_frames
