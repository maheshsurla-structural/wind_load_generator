from midas import get_elements, get_nodes, get_query_element
from midas import units as Units
from sklearn.cluster import DBSCAN
from unit_manager.converter import convert_length
import numpy as np

def cluster_vertical_elements(piers, elements=None, nodes=None, eps=10.0):

    if elements is None:
        elements = get_elements()
    if nodes is None:
        nodes = get_nodes()

    # READ ONCE from MIDAS via the new class (fallback to 'FT' if empty)
    dist_unit = Units.get("DIST") or "FT"

    # convert your eps (defined in feet) into the model’s distance unit
    eps_in_model_units = convert_length(eps, from_sym="FT", to_sym=dist_unit)

    centroids, element_ids = [], []
    for eid in piers:
        info = get_query_element(eid, elements=elements, nodes=nodes)
        if not info:
            continue
        centroids.append(info["Centroid"])
        element_ids.append(eid)

    if not centroids:
        return {}

    clustering = DBSCAN(eps=eps_in_model_units, min_samples=1).fit(np.array(centroids))

    clusters = {}
    for eid, label in zip(element_ids, clustering.labels_):
        clusters.setdefault(f"Pier {label+1}", []).append(eid)
    return clusters