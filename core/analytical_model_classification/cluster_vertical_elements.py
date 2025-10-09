from midas import get_elements, get_nodes, get_distance_unit, get_query_element
from sklearn.cluster import DBSCAN
from .convert_distance_from_ft import convert_distance_from_ft
import numpy as np

def cluster_vertical_elements(piers, elements=None, nodes=None):
    if elements is None:
        elements = get_elements()
    if nodes is None:
        nodes = get_nodes()
    dist_unit = get_distance_unit()
    eps = convert_distance_from_ft(10, dist_unit)
    centroids = []
    element_ids = []
    for eid in piers:
        info = get_query_element(eid, elements=elements, nodes=nodes)
        if not info:
            continue
        centroids.append(info["Centroid"])
        element_ids.append(eid)
    if not centroids:
        return {}
    clustering = DBSCAN(eps=eps, min_samples=1).fit(np.array(centroids))
    clusters = {}
    for eid, label in zip(element_ids, clustering.labels_):
        clusters.setdefault(f"Pier {label+1}", []).append(eid)
    return clusters