# midas/resources/load_group.py

from __future__ import annotations
from typing import Dict, Any, Optional, Iterable, Tuple
from .base import MapResource


class LoadGroup(MapResource):
    """
    MIDAS load groups (/db/LDGR)

    Shape (GET):
        {
            "LDGR": {
                "1": { "NAME": "SW" },
                "2": { "NAME": "WetConcrete" }
            }
        }

    Shape (PUT):
        {
            "Assign": {
                "1": { "NAME": "SW" },
                "2": { "NAME": "WetConcrete" }
            }
        }

    So this is a classic "map" resource → one to many.
    """

    READ_KEY = "LDGR"
    PATH = "/db/LDGR"

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    @classmethod
    def get_id_by_name(cls, name: str) -> Optional[str]:
        """
        Return the numeric key (as string) for a load group whose NAME matches.
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
        Find the next available numeric key, e.g. if existing keys are
        "1","2","5" → returns "6".
        """
        all_groups = cls.get_all()
        if not all_groups:
            return "1"

        nums = [int(k) for k in all_groups.keys() if str(k).isdigit()]
        return str(max(nums) + 1) if nums else "1"

    # ------------------------------------------------------------------
    # Create / Upsert
    # ------------------------------------------------------------------
    @classmethod
    def create(cls, name: str) -> Dict[str, Any]:
        """
        Create a brand-new load group. Fails if the name already exists.
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("Load group NAME is required.")

        if cls.get_id_by_name(name) is not None:
            raise RuntimeError(f"Load group with NAME='{name}' already exists.")

        key = cls.next_key()
        entry = {"NAME": name}

        # MapResource.set_all expects {"<id>": {...}}
        return cls.set_all({key: entry})

    @classmethod
    def upsert(cls, name: str) -> Dict[str, Any]:
        """
        Create or update a load group by NAME.
        If one exists → overwrite it (well, it's only NAME anyway).
        If not → create a new one.
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("Load group NAME is required.")

        existing_id = cls.get_id_by_name(name)
        key = existing_id if existing_id is not None else cls.next_key()

        entry = {"NAME": name}
        return cls.set_all({key: entry})

    # ------------------------------------------------------------------
    # Bulk (optional)
    # ------------------------------------------------------------------
    @classmethod
    def bulk_upsert(cls, names: Iterable[str] | Iterable[Tuple[str]]):
        """
        Upsert many load groups in ONE PUT.

        You can pass either:
            ["SW", "WetConcrete", "LL"]
        or
            [("SW",), ("WetConcrete",), ("LL",)]
        """
        existing = cls.get_all()  # {"1": {...}, "2": {...}}
        name_to_id: Dict[str, str] = {}
        max_id = 0

        # build map of current names → ids
        for k, v in existing.items():
            sk = str(k)
            if sk.isdigit():
                max_id = max(max_id, int(sk))
            n = (v.get("NAME") or "").strip()
            if n:
                name_to_id[n] = sk

        assign: Dict[str, Any] = {}
        next_id = max_id + 1

        for item in names:
            # support both "SW" and ("SW",)
            if isinstance(item, tuple) or isinstance(item, list):
                name = (item[0] if item else "").strip()
            else:
                name = (str(item) if item is not None else "").strip()

            if not name:
                raise ValueError("Load group NAME is required in bulk_upsert.")

            key = name_to_id.get(name)
            if key is None:
                key = str(next_id)
                next_id += 1

            assign[key] = {"NAME": name}

        if not assign:
            return {}
        return cls.set_all(assign)

    # ------------------------------------------------------------------
    # (Optional) nicer error if PUT fails
    # ------------------------------------------------------------------
    @classmethod
    def set_all(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return super().set_all(payload)
        except Exception as exc:
            raise RuntimeError(
                f"PUT {cls.PATH} failed for payload={payload!r}: {exc}"
            )
