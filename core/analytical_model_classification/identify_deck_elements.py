def identify_deck_elements(filtered_elements, superstructure_sections):
    """Identify deck elements by matching SECT property with superstructure section IDs."""
    return {eid: elem for eid, elem in filtered_elements.items() if str(elem["SECT"]) in superstructure_sections}