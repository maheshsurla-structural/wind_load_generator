# midas/resources/node.py
from __future__ import annotations
from typing import Dict, Any
from .base import MapResource

class Node(MapResource):

    READ_KEY = "NODE"
    PATH = "/db/NODE"

    @classmethod
    def set_all(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("Nodes is read-only; modifying /db/NODE via this API is not supported.")
