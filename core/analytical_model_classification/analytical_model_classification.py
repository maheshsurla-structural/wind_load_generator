from typing import Dict, Any, List, Tuple, Optional
from math import floor
from midas import NodeData as NODES, ElementData as ELEMS, SectionProperties as SECTS, ViewSelect as VS

TAPERED_SHAPES = {
    "1CEL","2CEL","3CEL","NCEL","NCE2","PSCM","PSCI","PSCH","PSCT","PSCB",
    "VALU","CMPW","CP_B","CP_T","CSGB","CSGI","CSGT","CPCI","CPCT","CP_G","STLB","STLI"
}

class AnalyticalModelClassification:

    def __init__(self, *, pier_link_distance: float = 10.0):
         
        self.eps = float(pier_link_distance)

        # --------- load once (fast path) ---------
        self.nodes_raw: Dict[str, Any] = dict(NODES())
        self.elems_raw: Dict[str, Any] = dict(ELEMS())
        self.sects_raw: List[List[Any]] = list(SECTS())
        self.sel_eids: List[str] = VS.view_selected_elements() or []

        # flatten nodes: {"NODE": {...}} or flat => always flat
        self.nodes = self.nodes_raw.get("NODE", self.nodes_raw)

        # precompute node coords (string keys)
        self.node_xyz: Dict[str, Tuple[float, float, float]] = {}
        for nid, nd in self.nodes.items():
            try:
                self.node_xyz[str(nid)] = (float(nd["X"]), float(nd["Y"]), float(nd["Z"]))
            except Exception:
                pass

        # precompute super section id set
        self.super_sect_ids: set[str] = set()
        for r in self.sects_raw:
            if len(r) < 4: 
                continue
            sid, stype, shape = r[1], r[2], r[3]
            if stype in ("PSC","COMPOSITE") or (stype == "TAPERED" and shape in TAPERED_SHAPES):
                self.super_sect_ids.add(str(sid))

        # pick only selected elements
        sel_set = set(map(str, self.sel_eids))
        self.sel_elems: Dict[str, Any] = {str(eid): e for eid, e in self.elems_raw.items() if str(eid) in sel_set}

        # split deck vs substructure once
        self.deck: Dict[str, Any] = {eid: e for eid, e in self.sel_elems.items() if str(e.get("SECT")) in self.super_sect_ids}
        self.sub: Dict[str, Any]  = {eid: e for eid, e in self.sel_elems.items() if eid not in self.deck}

        # deck ref Z once
        self.deck_ref_Z: Optional[float] = self._max_deck_Z()

        # precompute centroids for substructure once
        self.sub_centroid: Dict[str, Tuple[float, float, float]] = {}
        for eid, e in self.sub.items():
            c = self._centroid_fast(e)
            if c:
                self.sub_centroid[eid] = c

    # ---------- helpers ----------
    @staticmethod
    def _elem_node_ids(e: Dict[str, Any]) -> List[str]:
        # return positive node ids as strings
        out = []
        for n in e.get("NODE", []) or []:
            if isinstance(n, (int, float)) and n > 0:
                out.append(str(int(n)))
        return out

    def _centroid_fast(self, elem: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
        ids = self._elem_node_ids(elem)
        if not ids: 
            return None
        sx = sy = sz = 0.0
        cnt = 0
        for nid in ids:
            p = self.node_xyz.get(nid)
            if p:
                sx += p[0]; sy += p[1]; sz += p[2]; cnt += 1
        if cnt == 0:
            return None
        return (sx / cnt, sy / cnt, sz / cnt)

    def _max_deck_Z(self) -> Optional[float]:
        zmax: Optional[float] = None
        for e in self.deck.values():
            for nid in self._elem_node_ids(e):
                p = self.node_xyz.get(nid)
                if p:
                    z = p[2]
                    zmax = z if zmax is None else (z if z > zmax else zmax)
        return zmax

    # ---------- spatial-hash clustering (O(n)) in XY ----------
    def _cluster_sub(self) -> Dict[str, List[str]]:
        if not self.sub_centroid:
            return {}

        g = self.eps  # grid size
        buckets: Dict[Tuple[int, int], List[str]] = {}

        # bucket by floor(x/g), floor(y/g)
        for eid, (x, y, _z) in self.sub_centroid.items():
            key = (floor(x / g), floor(y / g))
            buckets.setdefault(key, []).append(eid)

        # adjacent bucket connectivity (8-neighborhood)
        # union-find over element indices
        eids = list(self.sub_centroid.keys())
        idx = {eid: i for i, eid in enumerate(eids)}
        parent = list(range(len(eids)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        # build bucket -> elements list once
        bucket_to_ids: Dict[Tuple[int, int], List[str]] = {}
        for eid, (x, y, _z) in self.sub_centroid.items():
            key = (floor(x / g), floor(y / g))
            bucket_to_ids.setdefault(key, []).append(eid)

        # for each bucket, compare with itself + neighbors only
        from math import dist
        neighbors = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]

        for (bx, by), ids in bucket_to_ids.items():
            # gather candidates from neighbor buckets
            cand: List[str] = []
            for dx, dy in neighbors:
                cand.extend(bucket_to_ids.get((bx + dx, by + dy), []))
            # link all pairs within eps (still limited, because cand is small)
            for i in range(len(ids)):
                ci = self.sub_centroid[ids[i]]
                ii = idx[ids[i]]
                for j in range(i + 1, len(cand)):
                    cj = self.sub_centroid[cand[j]]
                    if dist(ci, cj) <= self.eps:
                        union(ii, idx[cand[j]])

        # collect sets
        groups: Dict[int, List[str]] = {}
        for eid in eids:
            groups.setdefault(find(idx[eid]), []).append(eid)

        # name them
        return {f"Pier {k+1}": v for k, v in enumerate(groups.values())}

    # ---------- per-cluster classification ----------
    def _process_clusters(self, clusters: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
        refZ = self.deck_ref_Z
        span_th = 0.3 * self.eps

        def vspan(e: Dict[str, Any]) -> float:
            zs: List[float] = []
            for nid in self._elem_node_ids(e):
                p = self.node_xyz.get(nid)
                if p:
                    zs.append(p[2])
            return (max(zs) - min(zs)) if zs else 0.0

        def cz(e: Dict[str, Any]) -> Optional[float]:
            c = self._centroid_fast(e)
            return c[2] if c else None

        out: Dict[str, Dict[str, Any]] = {}
        for label, ids in clusters.items():
            subset = {eid: self.sub[eid] for eid in ids if eid in self.sub}

            above, below = {}, {}
            for eid, e in subset.items():
                z = cz(e)
                (above if (refZ is not None and z is not None and z > refZ) else below)[eid] = e

            caps, piers = {}, {}
            for eid, e in below.items():
                (caps if vspan(e) <= span_th else piers)[eid] = e

            out[f"{label}_SubAbove"] = above
            out[f"{label}_PierCap"] = caps
            out[f"{label}_Pier"] = piers

        return out

    # ---------- one-shot API ----------
    def analyze_substructure(self) -> Dict[str, Any]:
        clusters = self._cluster_sub()
        return {
            "deck_elements": self.deck,
            "substructure_elements": self.sub,
            "pier_clusters": self._process_clusters(clusters),
        }
