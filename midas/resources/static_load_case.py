from __future__ import annotations
from typing import Dict, Any, Optional, Iterable, Tuple
from .base import MapResource


# ---------------------------------------------------------------------------
# All available static load types (from MIDAS docs / your screenshots)
# Key = short MIDAS code ("D"), value = human label ("Dead Load")
# ---------------------------------------------------------------------------
STATIC_LOAD_TYPES: Dict[str, str] = {
    # 1 ~ 10
    "USER": "User Defined Load",
    "D": "Dead Load",
    "DC": "Dead Load of Component and Attachments",
    "DW": "Dead Load of Wearing Surfaces and Utilities",
    "DD": "Down Drag",
    "EP": "Earth Pressure",
    "EANN": "Active Earth Pressure for Native Ground of Non-cohesive Soil",
    "EANC": "Active Earth Pressure for Native Ground of Cohesive Soil",
    "EAMN": "Active Earth Pressure for Made Ground of Non-cohesive Soil",
    "EAMC": "Active Earth Pressure for Made Ground of Cohesive Soil",

    # 11 ~ 20
    "EPNN": "Passive Earth Pressure for Native Ground of Non-cohesive Soil",
    "EPNC": "Passive Earth Pressure for Native Ground of Cohesive Soil",
    "EPMN": "Passive Earth Pressure for Made Ground of Non-cohesive Soil",
    "EPMC": "Passive Earth Pressure for Made Ground of Cohesive Soil",
    "EH": "Horizontal Earth Pressure",
    "EV": "Vertical Earth Pressure",
    "ES": "Earth Surcharge Load",
    "EL": "Locked in Erection Stresses",
    "LS": "Live Load Surcharge",
    "LSC": "Trailer or Crawler Induced Surcharge",

    # 21 ~ 30
    "L": "Live Load",
    "LC": "Trailer or Crawler Induced Live Load",
    "LP": "Overload Live Load",
    "IL": "Live Load Impact",
    "ILP": "Overload Live Load Impact",
    "CF": "Centrifugal Force",
    "BRK": "Braking Load",
    "BK": "Longitudinal Force from Live Load",
    "CRL": "Crowd Load",
    "PS": "Prestress",

    # 31 ~ 40
    "B": "Buoyancy",
    "WP": "Ground Water Pressure",
    "FP": "Fluid Pressure",
    "SF": "Stream Flow Pressure",
    "WPR": "Wave Pressure",
    "W": "Wind Load on Structure",
    "WL": "Wind Load on Live Load",
    "STL": "Settlement",
    "CR": "Creep",
    "SH": "Shrinkage",

    # 41 ~ 50
    "T": "Temperature",
    "TPG": "Temperature Gradient",
    "CO": "Collision Load",
    "CT": "Vehicular Collision Force",
    "CV": "Vessel Collision Force",
    "E": "Earthquake",
    "FR": "Friction",
    "IP": "Ice Pressure",
    "CS": "Construction Stage Load",
    "ER": "Erection Load",

    # 51 ~ 60
    "RS": "Rib Shortening",
    "GE": "Grade Effect",
    "LR": "Roof Live Load",
    "S": "Snow Load",
    "R": "Rain Load",
    "LF": "Longitudinal Force",
    "RF": "RAKING Force",
    "GD": "Movement of Foundation",
    "SHV": "Soil Heaving",
    "DRL": "Derailment Load",

    # 61 ~ 67
    "WA": "Across Wind Load",
    "WT": "Torsional Wind Load",
    "EVT": "Vertical Earthquake",
    "EEP": "Earthquake Earth Pressure",
    "EX": "Explosion Load",
    "I": "Imperfection Load",
    "EE": "Earthquake for Elastic",
}


class StaticLoadCase(MapResource):
    """
    MIDAS static load cases (/db/STLD)

    GET /db/STLD
    -> {
        "STLD": {
            "1": { "NAME": "DL", "TYPE": "D", "DESC": "DeadLoads" },
            "2": { "NAME": "LL", "TYPE": "L" }
        }
    }

    PUT /db/STLD
    -> { "Assign": { "1": {...}, "2": {...} } }

    This is fully analogous to StructuralGroup, Node, Element, etc.
    """
    READ_KEY = "STLD"
    PATH = "/db/STLD"

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    @classmethod
    def get_id_by_name(cls, name: str) -> Optional[str]:
        name = (name or "").strip()
        if not name:
            return None
        all_cases = cls.get_all()
        for k, v in all_cases.items():
            if (v.get("NAME") or "").strip() == name:
                return k
        return None

    @classmethod
    def next_key(cls) -> str:
        all_cases = cls.get_all()
        if not all_cases:
            return "1"
        nums = [int(k) for k in all_cases.keys() if str(k).isdigit()]
        return str(max(nums) + 1) if nums else "1"

    # ------------------------------------------------------------------
    # Validation / normalization
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_type(load_type: str) -> str:
        """
        Accepts things like 'D', 'Dead Load', or 'dead load' and
        returns the proper MIDAS code ('D').
        """
        if not load_type:
            raise ValueError("Static load case TYPE is required.")

        lt = load_type.strip()

        # 1) exact code
        if lt in STATIC_LOAD_TYPES:
            return lt

        # 2) try to map by label (case-insensitive)
        upper = lt.upper()
        lower = lt.lower()
        for code, label in STATIC_LOAD_TYPES.items():
            if lower == label.lower():
                return code
            # allow users to say e.g. "earthquake" -> "E"
            if lower == label.lower().replace(" ", ""):
                return code
            if upper == code.upper():
                return code

        raise ValueError(
            f"Unknown static load case TYPE '{load_type}'. "
            f"Known codes: {', '.join(sorted(STATIC_LOAD_TYPES.keys()))}"
        )

    # ------------------------------------------------------------------
    # Create / upsert
    # ------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        name: str,
        load_type: str,
        desc: str = "",
    ) -> Dict[str, Any]:
        """
        Create a BRAND NEW static load case.
        Fails if NAME already exists.
        """
        if not name or not name.strip():
            raise ValueError("Static load case NAME is required.")

        if cls.get_id_by_name(name) is not None:
            raise RuntimeError(f"Static load case with NAME='{name}' already exists.")

        st_code = cls._normalize_type(load_type)
        key = cls.next_key()
        entry = {
            "NAME": name.strip(),
            "TYPE": st_code,
        }
        if desc:
            entry["DESC"] = desc

        # {"Assign": {"<key>": {...}}}
        return cls.set_all({str(key): entry})

    @classmethod
    def upsert(
        cls,
        name: str,
        load_type: str,
        desc: str = "",
    ) -> Dict[str, Any]:
        """
        Create or update a static load case by NAME.
        If a case with that NAME exists, we overwrite its TYPE/DESC.
        """
        if not name or not name.strip():
            raise ValueError("Static load case NAME is required.")

        st_code = cls._normalize_type(load_type)
        existing_id = cls.get_id_by_name(name)
        key = existing_id if existing_id is not None else cls.next_key()

        entry = {
            "NAME": name.strip(),
            "TYPE": st_code,
        }
        if desc:
            entry["DESC"] = desc

        return cls.set_all({str(key): entry})

    # ------------------------------------------------------------------
    # Bulk (optional, mirrors StructuralGroup.bulk_upsert)
    # ------------------------------------------------------------------
    @classmethod
    def bulk_upsert(
        cls,
        cases: Iterable[Tuple[str, str, str | None]],
    ) -> Dict[str, Any]:
        """
        Upsert many static load cases in ONE PUT.

        cases: iterable of (name, type, desc)
        """
        existing = cls.get_all()
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

        for name, load_type, desc in cases:
            if not name or not name.strip():
                raise ValueError("Static load case NAME is required in bulk_upsert.")

            st_code = cls._normalize_type(load_type)
            name_clean = name.strip()
            key = name_to_id.get(name_clean)
            if key is None:
                key = str(next_id)
                next_id += 1

            entry = {
                "NAME": name_clean,
                "TYPE": st_code,
            }
            if desc:
                entry["DESC"] = desc
            assign[key] = entry

        if not assign:
            return {}
        return cls.set_all(assign)
