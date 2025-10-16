# core/analytical_model_classification/classify_elements.py

from midas import get_elements, get_nodes, ViewSelected
from midas import units as Units

from .calculate_deck_reference_height import calculate_deck_reference_height
from .identify_deck_elements import identify_deck_elements
from .get_superstructure_section_ids_with_typeandshape import get_superstructure_section_ids_with_typeandshape
from .filter_selected_elements import filter_selected_elements
from .cluster_vertical_elements import cluster_vertical_elements
from .process_pier_clusters import process_pier_clusters



def classify_elements(
    *,
    pier_radius: float = 10.0,          # comes from ControlData.geometry.pier_radius
    length_unit: str = "FT",            # app/UI length unit (e.g., FT, IN, M)
    suffix_above: str = "_SubAbove",    # from NamingRules.suffix_above
    pier_base_name: str = "Pier",       # optional: NamingRules.pier_base_name
):
    elements_in_model = get_elements()
    node_data = get_nodes()
    selected_elements = ViewSelected.view_selected_elements()
    filtered_elements = filter_selected_elements(elements_in_model, selected_elements)
    superstructure_sections = get_superstructure_section_ids_with_typeandshape()
    deck_elements = identify_deck_elements(filtered_elements, superstructure_sections)
    substructure_elements = {eid: elem for eid, elem in filtered_elements.items() if eid not in deck_elements}

    reference_height = calculate_deck_reference_height(deck_elements, node_data)

    # pass pier_radius with its unit into the clustering
    pier_clusters_raw = cluster_vertical_elements(
        substructure_elements,
        elements=elements_in_model,
        nodes=node_data,
        eps=pier_radius,
        eps_unit=length_unit,
        base_name=pier_base_name,   # optional; see change below
    )

    pier_clusters = process_pier_clusters(
        pier_clusters_raw,
        substructure_elements,
        reference_height,
        elements=elements_in_model,
        nodes=node_data,
        suffix_above=suffix_above,  # see change below
    )

    return {
        "deck_elements": deck_elements,
        "substructure_elements": substructure_elements,
        "pier_clusters": pier_clusters,
        "deck_reference_height": reference_height,        
        "model_unit": Units.get("DIST") or "FT",           
    }
