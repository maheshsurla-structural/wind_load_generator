from midas import elements, nodes, units, ViewSelected

from .calculate_deck_reference_height import calculate_deck_reference_height
from .identify_deck_elements import identify_deck_elements
from .get_superstructure_section_ids_with_typeandshape import get_superstructure_section_ids_with_typeandshape
from .filter_selected_elements import filter_selected_elements
from .cluster_vertical_elements import cluster_vertical_elements
from .process_pier_clusters import process_pier_clusters


def classify_elements(
    *,
    pier_radius: float = 10.0,
    length_unit: str = "FT",
    suffix_above: str = "_SubAbove",
    pier_base_name: str = "Pier",
):
    elements_in_model = elements.get_all()
    node_data = nodes.get_all()
    selected_elements = ViewSelected.view_selected_elements()

    filtered_elements = filter_selected_elements(elements_in_model, selected_elements)
    superstructure_sections = get_superstructure_section_ids_with_typeandshape()
    deck_elements = identify_deck_elements(filtered_elements, superstructure_sections)
    substructure_elements = {
        eid: elem
        for eid, elem in filtered_elements.items()
        if eid not in deck_elements
    }

    reference_height = calculate_deck_reference_height(deck_elements, node_data)

    pier_clusters_raw = cluster_vertical_elements(
        substructure_elements,
        elements_in_model=elements_in_model,   
        nodes_in_model=node_data,             
        eps=pier_radius,
        eps_unit=length_unit,
        base_name=pier_base_name,
    )

    pier_clusters = process_pier_clusters(
        pier_clusters_raw,
        substructure_elements,
        reference_height,
        elements_in_model=elements_in_model,  
        nodes_in_model=node_data,             
        suffix_above=suffix_above,
    )

    return {
        "deck_elements": deck_elements,
        "substructure_elements": substructure_elements,
        "pier_clusters": pier_clusters,
        "deck_reference_height": reference_height,
        "model_unit": units.get("DIST") or "FT",
    }
