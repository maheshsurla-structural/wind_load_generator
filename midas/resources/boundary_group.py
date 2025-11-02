# midas/resources/boundary_group.py

from __future__ import annotations
from typing import Dict, Any, Optional, Iterable, Tuple
from .base import MapResource


class BoundaryGroup(MapResource):
    """
    MIDAS boundary groups (/db/BNGR)

    Your examples:

        # schema-like shape
        {
            "BNGR": {
                "NAME": "BoundaryGroupName",
                "AUTOTYPE": 0
            }
        }

        # actual PUT
        {
            "Assign": {
                "1": { "NAME": "fix1", "AUTOTYPE": 0 },
                "2": { "NAME": "fix2", "AUTOTYPE": 0 }
            }
        }

    So this is a classic "map" resource: many entries, each with its own key.
    That’s exactly what MapResource is for.
    """

    READ_KEY = "BNGR"
    PATH = "/db/BNGR"

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    @classmethod
    def get_id_by_name(cls, name: str) -> Optional[str]:
        """
        Return the numeric key (as string) for a boundary group whose NAME matches.
        """
        name = (name or "").strip()
        if not name:
            return None
        all_groups = cls.get_all()  # {"1": {...}, "2": {...}}
        for k, v in all_groups.items():
            if (v.get("NAME") or "").strip() == name:
                return k
        return None

    @classmethod
    def next_key(cls) -> str:
        """
        Find the next available numeric key, just like the other resources.
        """
        all_groups = cls.get_all()
        if not all_groups:
            return "1"
        nums = [int(k) for k in all_groups.keys() if str(k).isdigit()]
        return str(max(nums) + 1) if nums else "1"

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_autotype(autotype: Optional[int]) -> int:
        """
        According to the MIDAS note, using 0 is generally recommended.
        So if caller doesn't give anything, we default to 0.
        """
        if autotype is None:
            return 0
        return int(autotype)

    # ------------------------------------------------------------------
    # Create / Upsert
    # ------------------------------------------------------------------
    @classmethod
    def create(cls, name: str, autotype: Optional[int] = None) -> Dict[str, Any]:
        """
        Create a brand-new boundary group. Fails if the name already exists.

        name      -> "fix1"
        autotype  -> integer, usually 0 (Auto)
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("Boundary group NAME is required.")

        if cls.get_id_by_name(name) is not None:
            raise RuntimeError(f"Boundary group with NAME='{name}' already exists.")

        key = cls.next_key()
        entry = {
            "NAME": name,
            "AUTOTYPE": cls._normalize_autotype(autotype),
        }

        # MapResource.set_all expects {"<id>": {...}}
        return cls.set_all({key: entry})

    @classmethod
    def upsert(cls, name: str, autotype: Optional[int] = None) -> Dict[str, Any]:
        """
        Create or update a boundary group by NAME.
        If one exists -> overwrite AUTOTYPE.
        If not -> create a new one.
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("Boundary group NAME is required.")

        existing_id = cls.get_id_by_name(name)
        key = existing_id if existing_id is not None else cls.next_key()

        entry = {
            "NAME": name,
            "AUTOTYPE": cls._normalize_autotype(autotype),
        }

        return cls.set_all({key: entry})

    # ------------------------------------------------------------------
    # Bulk (optional)
    # ------------------------------------------------------------------
    @classmethod
    def bulk_upsert(
        cls,
        groups: Iterable[Tuple[str, Optional[int]]],
    ) -> Dict[str, Any]:
        """
        Upsert many boundary groups in ONE PUT.

        groups: iterable of (name, autotype)
        """
        existing = cls.get_all()  # {"1": {...}, "2": {...}}
        name_to_id: Dict[str, str] = {}
        max_id = 0

        for k, v in existing.items():
            sk = str(k)
            if sk.isdigit():
                max_id = max(max_id, int(sk))
            n = (v.get("NAME") or "").strip()
            if n:
                name_to_id[n] = sk

        assign: Dict[str, Any] = {}
        next_id = max_id + 1

        for name, autotype in groups:
            name = (name or "").strip()
            if not name:
                raise ValueError("Boundary group NAME is required in bulk_upsert.")

            key = name_to_id.get(name)
            if key is None:
                key = str(next_id)
                next_id += 1

            assign[key] = {
                "NAME": name,
                "AUTOTYPE": cls._normalize_autotype(autotype),
            }

        if not assign:
            return {}
        return cls.set_all(assign)
