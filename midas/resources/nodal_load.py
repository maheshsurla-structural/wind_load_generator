# midas/resources/nodal_load.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Iterable, Tuple, Union, Literal
from midas.midas_api import MidasAPI


Number = Union[int, float]
NodeID = Union[int, str]
ItemID = Union[int, str]
MergeMode = Literal["replace", "append"]


class NodalLoadItem:
    """
    Represents ONE nodal load item inside:

        {
          "Assign": {
            "8": { "ITEMS": [ { ... }, ... ] }
          }
        }

    Keys mirror MIDAS keys:
      ID, LCNAME, GROUP_NAME, FX,FY,FZ, MX,MY,MZ
    """

    def __init__(
        self,
        *,
        ID: ItemID,
        LCNAME: str,
        GROUP_NAME: str = "",
        FX: Number = 0.0,
        FY: Number = 0.0,
        FZ: Number = 0.0,
        MX: Number = 0.0,
        MY: Number = 0.0,
        MZ: Number = 0.0,
    ):
        if LCNAME is None or not str(LCNAME).strip():
            raise ValueError("LCNAME is required for a nodal load item.")

        self.ID = ID
        self.LCNAME = str(LCNAME).strip()
        self.GROUP_NAME = (GROUP_NAME or "").strip()

        # forces
        self.FX = float(FX)
        self.FY = float(FY)
        self.FZ = float(FZ)

        # moments
        self.MX = float(MX)
        self.MY = float(MY)
        self.MZ = float(MZ)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ID": self.ID,
            "LCNAME": self.LCNAME,
            "GROUP_NAME": self.GROUP_NAME,
            "FX": self.FX,
            "FY": self.FY,
            "FZ": self.FZ,
            "MX": self.MX,
            "MY": self.MY,
            "MZ": self.MZ,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodalLoadItem":
        return cls(
            ID=data.get("ID"),
            LCNAME=data.get("LCNAME", ""),
            GROUP_NAME=data.get("GROUP_NAME", ""),
            FX=data.get("FX", 0.0),
            FY=data.get("FY", 0.0),
            FZ=data.get("FZ", 0.0),
            MX=data.get("MX", 0.0),
            MY=data.get("MY", 0.0),
            MZ=data.get("MZ", 0.0),
        )


class NodalLoadResource:
    """
    Resource interface for /db/CNLD (nodal loads).

    - GET /db/CNLD returns:
        { "CNLD": { "8": { "ITEMS": [ {...}, ... ] }, ... } }

    - PUT /db/CNLD expects:
        { "Assign": { "8": { "ITEMS": [ {...}, ... ] }, ... } }
    """

    PATH = "/db/CNLD"
    READ_KEY = "CNLD"

    # ----------------------------
    # Low-level HTTP
    # ----------------------------

    @classmethod
    def get_raw(cls) -> Dict[str, Any]:
        resp = MidasAPI("GET", cls.PATH) or {}
        return resp.get(cls.READ_KEY, {}) or {}

    @classmethod
    def put_raw(cls, assign_payload: Dict[str, Any]) -> Dict[str, Any]:
        # assign_payload MUST be {"Assign": {...}}
        return MidasAPI("PUT", cls.PATH, assign_payload)

    # ----------------------------
    # Payload builders
    # ----------------------------

    @staticmethod
    def build_assign_from_specs(
        specs: Iterable[Tuple[NodeID, NodalLoadItem]],
    ) -> Dict[str, Any]:
        """
        specs: iterable of (node_id, NodalLoadItem)

        Output:
          {
            "Assign": {
              "8": { "ITEMS": [ {...}, {...} ] },
              "9": { "ITEMS": [ {...} ] }
            }
          }
        """
        assign: Dict[str, Dict[str, Any]] = {}

        for node_id, item in specs:
            nkey = str(int(node_id))  # normalize "8", 8, "008" -> "8"
            if nkey not in assign:
                assign[nkey] = {"ITEMS": []}
            assign[nkey]["ITEMS"].append(item.to_dict())

        return {"Assign": assign}

    @classmethod
    def create_from_specs(
        cls,
        specs: Iterable[Tuple[NodeID, NodalLoadItem]],
    ) -> Dict[str, Any]:
        payload = cls.build_assign_from_specs(specs)
        return cls.put_raw(payload)

    # ----------------------------
    # Readback parsing
    # ----------------------------

    @classmethod
    def get_all_items(cls) -> Dict[int, List[NodalLoadItem]]:
        """
        Returns:
          { 8: [NodalLoadItem(...), ...], 9: [...], ... }
        """
        out: Dict[int, List[NodalLoadItem]] = {}
        raw = cls.get_raw()

        for node_id_str, node_block in raw.items():
            try:
                nid = int(str(node_id_str))
            except ValueError:
                continue

            items_raw = (node_block or {}).get("ITEMS", []) or []
            out[nid] = [NodalLoadItem.from_dict(d) for d in items_raw]

        return out

    # ----------------------------
    # Convenience: upsert per node
    # ----------------------------

    @classmethod
    def upsert_node_items(
        cls,
        node_id: NodeID,
        items: Iterable[NodalLoadItem],
        *,
        mode: MergeMode = "replace",
    ) -> Dict[str, Any]:
        """
        Replace or append nodal load items for ONE node.

        mode="replace":
          PUT {"Assign": {"8":{"ITEMS":[...]}}} (overwrites node's ITEMS in many MIDAS DBs)

        mode="append":
          Read existing, concatenate, then PUT combined list.
          (Safer if MIDAS treats PUT as full overwrite for that node.)
        """
        nkey = str(int(node_id))
        new_items = list(items)

        if mode not in ("replace", "append"):
            raise ValueError("mode must be 'replace' or 'append'.")

        if mode == "append":
            existing = cls.get_all_items().get(int(nkey), [])
            combined = existing + new_items
        else:
            combined = new_items

        assign = {
            "Assign": {
                nkey: {
                    "ITEMS": [it.to_dict() for it in combined]
                }
            }
        }
        return cls.put_raw(assign)

    @classmethod
    def next_item_id(cls, node_id: NodeID) -> int:
        """
        Convenience helper: returns 1 + max(ID) for that node (numeric IDs only).
        """
        nid = int(node_id)
        items = cls.get_all_items().get(nid, [])
        max_id = 0
        for it in items:
            try:
                max_id = max(max_id, int(it.ID))
            except Exception:
                pass
        return max_id + 1
