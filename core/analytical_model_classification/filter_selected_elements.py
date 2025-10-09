def filter_selected_elements(elements_in_model, selected_elements):
    """Filter elements in the model based on user selection."""
    selected_str_ids = set(map(str, selected_elements))  # Convert to string for matching
    return {eid: elem for eid, elem in elements_in_model.items() if eid in selected_str_ids}