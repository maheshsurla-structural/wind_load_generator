# midas/resources/section.py
from __future__ import annotations
from typing import Dict, Any, List
from .base import MapResource
from midas.midas_api import MidasAPI


class Section(MapResource):
    """
    Direct interface to /db/SECT.

    This matches Element, Node, StructuralGroup style:
    - GET /db/SECT  -> { "SECT": { "1": {...}, "2": {...}, ... } }
    - PUT /db/SECT  -> { "Assign": { "1": {...}, "2": {...}, ... } }

    You automatically inherit:
        Section.get_all()  -> Dict[str, Dict[str, Any]]
        Section.set_all({...}) -> PUT partial updates

    If you do NOT want to allow editing sections through this API,
    you can override set_all the same way Element/Node did.
    """

    READ_KEY = "SECT"
    PATH = "/db/SECT"

    @classmethod
    def set_all(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sections are typically defined in MIDAS by section assignment dialogs,
        not by raw PUTs. If you want read-only behavior (recommended at first),
        block writes like Element/Node.
        """
        raise RuntimeError(
            "Sections are read-only via this API; modifying /db/SECT is not supported."
        )

    # Optional convenience helpers that mirror StructuralGroup style
    @classmethod
    def get_by_id(cls, section_id: int | str) -> Dict[str, Any]:
        """
        Return the raw section definition for a given section ID from /db/SECT.
        {} if not found.
        """
        return cls.get_all().get(str(section_id), {}) or {}

    @classmethod
    def ids(cls) -> List[int]:
        """
        Return all section IDs as ints.
        """
        return [
            int(k)
            for k in cls.get_all().keys()
            if str(k).strip().isdigit()
        ]


# ---------------------------------------------------------------------------
# Table-style helpers (report queries)
# ---------------------------------------------------------------------------

def get_section_table_raw() -> Dict[str, Any]:
    """
    Low-level helper that calls POST /post/TABLE exactly once and
    returns the whole JSON response.

    You usually shouldn't need this directly in downstream code.
    """
    request_body = {
        "Argument": {
            "TABLE_NAME": "SectionProperties",
            "TABLE_TYPE": "SECTIONALL",
        }
    }
    resp = MidasAPI("POST", "/post/TABLE", request_body)
    return resp or {}


def get_section_properties() -> List[List[Any]]:
    """
    High-level helper you already had, but now colocated here.

    Returns the DATA rows from the SectionProperties table.

    Shape: a list of rows (lists). Each row contains many columns:
    [Index, ID, ..., LEFT, RIGHT, TOP, BOTTOM, ...]
    Downstream code like exposures_numpy() iterates those rows by index.
    """
    resp = get_section_table_raw()
    table = resp.get("SectionProperties", {})
    data = table.get("DATA", [])
    # guarantee it's always a list
    return data if isinstance(data, list) else []
