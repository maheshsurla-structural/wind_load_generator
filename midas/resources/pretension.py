# midas/resources/pretension.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from midas.midas_api import MidasAPI


@dataclass
class PretensionItem:
    ID: int
    LCNAME: str
    GROUP_NAME: str
    TENSION: float

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PretensionItem":
        return cls(
            ID=int(d.get("ID", 0)),
            LCNAME=str(d.get("LCNAME", "")).strip(),
            GROUP_NAME=str(d.get("GROUP_NAME", "")).strip(),
            TENSION=float(d.get("TENSION", 0.0)),
        )


class PretensionResource:
    """
    /db/PTNS (pretension table)

    GET /db/PTNS -> { "PTNS": { "<elem_id>": { "ITEMS": [ ... ] }, ... } }
    PUT /db/PTNS -> { "Assign": { "<elem_id>": { "ITEMS": [ ... ] } } }  (not needed here)
    """
    PATH = "/db/PTNS"
    READ_KEY = "PTNS"

    @classmethod
    def get_raw(cls) -> Dict[str, Any]:
        resp = MidasAPI("GET", cls.PATH) or {}
        return resp.get(cls.READ_KEY, {}) or {}

    @classmethod
    def get_items_for_element(cls, elem_id: int) -> List[PretensionItem]:
        raw = cls.get_raw()
        block = raw.get(str(int(elem_id)), {}) or {}
        items = block.get("ITEMS", []) or []
        return [PretensionItem.from_dict(x) for x in items]
