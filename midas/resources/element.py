# midas/resources/element.py
from __future__ import annotations
from typing import Dict, Any
from .base import MapResource

class Element(MapResource):

    READ_KEY = "ELEM"
    PATH = "/db/ELEM"

    @classmethod
    def set_all(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("Elements is read-only; modifying /db/ELEM via this API is not supported.")
