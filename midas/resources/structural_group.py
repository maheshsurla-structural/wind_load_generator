# midas/resources/structural_group.py
from typing import Dict, Any, Optional, Iterable, Union, Tuple
from .base import MapResource

class StructuralGroup(MapResource):
    READ_KEY = "GRUP"
    PATH = "/db/GRUP"

    # ------------------------------- Internal Helpers -------------------------------

    @staticmethod
    def _normalize_e_list(e_list: Union[str, Iterable[int], Iterable[str]]) -> Union[str, list[int]]:
        """
        MIDAS accepts E_LIST as a list of element IDs (ints). Your previous working
        code sent a list, so we keep that behavior. If a string is provided, we pass
        it through unchanged (caller takes responsibility for formatting).
        """
        if isinstance(e_list, str):
            return e_list.strip()

        # Convert any iterable of numbers/strings into a concrete list[int]
        try:
            normalized = [int(x) for x in e_list]  # list, not generator / not joined string
        except TypeError:
            raise ValueError("E_LIST must be a string or an iterable of IDs.")
        except ValueError:
            raise ValueError("E_LIST iterable must contain only integers (or strings of ints).")

        return normalized

    # ------------------------------- Lookup Methods ---------------------------------

    @classmethod
    def get_id_by_name(cls, name: str) -> Optional[str]:
        all_groups = cls.get_all()
        for k, entry in all_groups.items():
            if entry.get("NAME") == name:
                return k
        return None

    # ------------------------------- Key Management ---------------------------------

    @classmethod
    def next_key(cls) -> str:
        all_groups = cls.get_all()
        if not all_groups:
            return "1"
        nums = [int(k) for k in all_groups.keys() if str(k).isdigit()]
        return str(max(nums) + 1) if nums else "1"

    # ------------------------------- Create / Update --------------------------------

    @classmethod
    def create(cls, name: str, e_list: Union[str, Iterable[int], Iterable[str]]) -> Dict[str, Any]:
        if not name or not name.strip():
            raise ValueError("Structural group name is required.")
        
        e_list_norm = cls._normalize_e_list(e_list)
        if (isinstance(e_list_norm, list) and not e_list_norm) or (isinstance(e_list_norm, str) and not e_list_norm):
            raise ValueError("Element list is empty.")

        if cls.get_id_by_name(name) is not None:
            raise RuntimeError(f"Structural group name '{name}' already exists.")

        key = cls.next_key()
        entry = {"NAME": name, "E_LIST": e_list_norm}
        # ✅ ensure key is string
        return cls.set_all({str(key): entry})


    @classmethod
    def upsert(cls, name: str, e_list: Union[str, Iterable[int], Iterable[str]]) -> Dict[str, Any]:
        if not name or not name.strip():
            raise ValueError("Structural group name is required.")
        
        e_list_norm = cls._normalize_e_list(e_list)
        if (isinstance(e_list_norm, list) and not e_list_norm) or (isinstance(e_list_norm, str) and not e_list_norm):
            raise ValueError("Element list is empty.")

        existing_id = cls.get_id_by_name(name)
        key = existing_id if existing_id is not None else cls.next_key()

        entry = {"NAME": name, "E_LIST": e_list_norm}
        # ✅ ensure key is string
        return cls.set_all({str(key): entry})


    # --------------------------------- DEBUG WRAP ---------------------------------
    @classmethod
    def set_all(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Override MapResource.set_all to provide clearer debugging if the MIDAS PUT fails.
        """
        try:
            return super().set_all(payload)
        except Exception as exc:
            # Helpful while debugging payload shape or network response
            raise RuntimeError(
                f"PUT {cls.PATH} failed for payload={payload!r}: {exc}"
            )

    @classmethod
    def bulk_upsert(cls, entries: Iterable[Tuple[str, Iterable[int] | str]]) -> Dict[str, Any]:
        """
        Upsert many groups in ONE request.
        entries: iterable of (name, e_list) pairs
        """
        # 1) Read existing only once
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

        # 2) Build one big Assign payload
        assign: Dict[str, Any] = {}
        next_id = max_id + 1

        for name, e_list in entries:
            if not name or not name.strip():
                raise ValueError("Structural group name is required.")
            e_list_norm = cls._normalize_e_list(e_list)
            if (isinstance(e_list_norm, list) and not e_list_norm) or (isinstance(e_list_norm, str) and not e_list_norm):
                raise ValueError(f"Element list is empty for group '{name}'.")

            name = name.strip()
            key = name_to_id.get(name)
            if key is None:
                key = str(next_id)
                next_id += 1

            assign[key] = {"NAME": name, "E_LIST": e_list_norm}

        # 3) Single PUT with all assignments
        if not assign:
            return {}  # nothing to do
        return cls.set_all(assign)       


    # ------------------------------- Element Access ---------------------------------

    @staticmethod
    def _to_int_list(e_list: Any) -> list[int]:
        """
        Normalize MIDAS E_LIST (may be list[int] or space-separated str) into list[int].
        Returns [] for missing/empty.
        """
        if not e_list:
            return []
        if isinstance(e_list, str):
            return [int(x) for x in e_list.split() if x.strip().isdigit()]
        # assume iterable
        return [int(x) for x in e_list]

    @classmethod
    def get_elements_by_name(cls, name: str) -> list[int]:
        """
        Return the element IDs in the group whose NAME == name.
        [] if not found or empty.
        """
        all_groups = cls.get_all()
        for entry in all_groups.values():
            if (entry.get("NAME") or "").strip() == name:
                return cls._to_int_list(entry.get("E_LIST"))
        return []


    @classmethod
    def get_elements_by_id(cls, group_id: Union[str, int]) -> list[int]:
        """
        Return the element IDs in the group with the given numeric key (e.g., "3").
        [] if not found or empty.
        """
        entry = cls.get_all().get(str(group_id))
        return cls._to_int_list(entry.get("E_LIST")) if entry else []


    # @classmethod
    # def name_to_elements(cls) -> Dict[str, list[int]]:
    #     """
    #     Return a mapping { group_name: [element_ids...] } for all groups.
    #     """
    #     out: Dict[str, list[int]] = {}
    #     for entry in cls.get_all().values():
    #         name = (entry.get("NAME") or "").strip()
    #         if name:
    #             out[name] = cls._to_int_list(entry.get("E_LIST"))
    #     return out

    # @classmethod
    # def id_to_elements(cls) -> Dict[str, list[int]]:
    #     """
    #     Return a mapping { group_id: [element_ids...] } for all groups.
    #     """
    #     out: Dict[str, list[int]] = {}
    #     for k, entry in cls.get_all().items():
    #         out[str(k)] = cls._to_int_list(entry.get("E_LIST"))
    #     return out

    # @classmethod
    # def get_by_name(cls, name: str) -> Optional[Dict[str, Any]]:
    #     all_groups = cls.get_all()
    #     for entry in all_groups.values():
    #         if entry.get("NAME") == name:
    #             return entry
    #     return None