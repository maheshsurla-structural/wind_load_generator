import math
from midas import get_nodes, get_elements

def get_query_element(element_id, elements=None, nodes=None):
    element_id = str(element_id)
    if elements is None:
        elements = get_elements()
    if nodes is None:
        nodes = get_nodes()
    element_data = elements.get(element_id)
    if not element_data:
        return None
    node_ids = [nid for nid in element_data['NODE'] if nid > 0]
    if len(node_ids) < 2:
        return None
    n1, n2 = node_ids[:2]
    coord1, coord2 = nodes.get(str(n1)), nodes.get(str(n2))
    if not coord1 or not coord2:
        return None
    dx = coord2["X"] - coord1["X"]
    dy = coord2["Y"] - coord1["Y"]
    dz = coord2["Z"] - coord1["Z"]
    length = math.sqrt(dx**2 + dy**2 + dz**2)
    if length == 0:
        return None
    angle_xy = math.degrees(math.asin(abs(dz) / length))
    angle_xz = math.degrees(math.asin(abs(dy) / length))
    angle_yz = math.degrees(math.asin(abs(dx) / length))
    cx = (coord1["X"] + coord2["X"]) / 2
    cy = (coord1["Y"] + coord2["Y"]) / 2
    return {
        "Element ID": element_id,
        "Type": element_data["TYPE"],
        "Material ID": element_data["MATL"],
        "Property ID": element_data["SECT"],
        "Beta Angle": element_data.get("ANGLE", 0),
        "Node Connectivity": node_ids,
        "Element Length": round(length, 3),
        "Angles to Global Planes [XY, XZ, YZ]": (
            round(angle_xy, 2), round(angle_xz, 2), round(angle_yz, 2)),
        "Centroid": [cx, cy]
    }