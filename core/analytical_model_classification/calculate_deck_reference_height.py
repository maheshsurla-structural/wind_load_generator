def calculate_deck_reference_height(deck_elements, node_data):
    node_data = node_data.get("NODE", {}) if "NODE" in node_data else node_data
    deck_node_ids = {node for elem in deck_elements.values() for node in elem["NODE"] if node > 0}
    deck_heights = [node_data[str(node)]["Z"] for node in deck_node_ids if str(node) in node_data]
    return max(deck_heights) if deck_heights else None
