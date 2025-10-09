from midas import get_elements, get_nodes, ViewSelected
from core.analytical_model_classification.calculate_deck_reference_height import calculate_deck_reference_height
from core.analytical_model_classification.identify_deck_elements import identify_deck_elements
from core.analytical_model_classification.get_superstructure_section_ids_with_typeandshape import get_superstructure_section_ids_with_typeandshape
from core.analytical_model_classification.filter_selected_elements import filter_selected_elements
from core.analytical_model_classification.cluster_vertical_elements import cluster_vertical_elements
from core.analytical_model_classification.process_pier_clusters import process_pier_clusters

def classify_elements():
    elements_in_model = get_elements()
    node_data = get_nodes()
    selected_elements = ViewSelected.view_selected_elements()
    filtered_elements = filter_selected_elements(elements_in_model, selected_elements)
    superstructure_sections = get_superstructure_section_ids_with_typeandshape()
    deck_elements = identify_deck_elements(filtered_elements, superstructure_sections)
    substructure_elements = {
        eid: elem for eid, elem in filtered_elements.items() if eid not in deck_elements
    }
    reference_height = calculate_deck_reference_height(deck_elements, node_data)
    pier_clusters_raw = cluster_vertical_elements(substructure_elements, elements=elements_in_model, nodes=node_data)
    pier_clusters = process_pier_clusters(pier_clusters_raw, substructure_elements, reference_height, elements=elements_in_model, nodes=node_data)

    return {
        "deck_elements": deck_elements,
        "substructure_elements": substructure_elements,
        "pier_clusters": pier_clusters
    }