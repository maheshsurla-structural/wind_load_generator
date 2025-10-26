# midas\resources\element_beam_load.py

from __future__ import annotations
from typing import Any, Dict, List, Optional, Iterable, Union, Tuple
from midas.midas_api import MidasAPI


class BeamLoadItem:
    """
    Represents ONE beam load entry under an element in MIDAS /db/bmld.

    This maps 1:1 to the objects inside:
        {
            "Assign": {
                "115": {
                    "ITEMS": [
                        { ... this dict ... },
                        ...
                    ]
                }
            }
        }

    The attribute names intentionally mirror MIDAS keys so you don't have to
    mentally translate when debugging a payload.
    """

    def __init__(
        self,
        *,
        ID: Union[int, str],
        LCNAME: str,
        GROUP_NAME: str = "",
        CMD: str = "BEAM",
        TYPE: str = "UNILOAD",
        DIRECTION: str = "GZ",
        USE_PROJECTION: bool = False,
        USE_ECCEN: bool = False,
        D: Iterable[float] = (0, 1, 0, 0),
        P: Iterable[float] = (0, 0, 0, 0),
        # eccentricity block
        ECCEN_TYPE: int = 1,
        ECCEN_DIR: str = "GX",
        I_END: float = 0.0,
        J_END: float = 0.0,
        USE_J_END: Optional[bool] = None,
        # additional block (pressure/additional height)
        USE_ADDITIONAL: bool = False,
        ADDITIONAL_I_END: float = 0.0,
        ADDITIONAL_J_END: float = 0.0,
        USE_ADDITIONAL_J_END: Optional[bool] = None,
    ):
        # --- Basic load definition ---
        self.ID = ID
        self.LCNAME = LCNAME
        self.GROUP_NAME = GROUP_NAME
        self.CMD = CMD
        self.TYPE = TYPE
        self.DIRECTION = DIRECTION
        self.USE_PROJECTION = bool(USE_PROJECTION)
        self.USE_ECCEN = bool(USE_ECCEN)

        # normalize D and P to exactly 4 values (MIDAS style)
        D_list = list(D)
        D_list = (D_list + [0.0] * 4)[:4]
        P_list = list(P)
        P_list = (P_list + [0.0] * 4)[:4]

        self.D = D_list
        self.P = P_list

        # --- Eccentricity info ---
        self.ECCEN_TYPE = int(ECCEN_TYPE)
        self.ECCEN_DIR = ECCEN_DIR
        self.I_END = float(I_END)
        self.J_END = float(J_END)

        if USE_J_END is None:
            USE_J_END = (self.J_END != 0.0)
        self.USE_J_END = bool(USE_J_END)

        # --- Additional (pressure/additional height) info ---
        self.USE_ADDITIONAL = bool(USE_ADDITIONAL)
        self.ADDITIONAL_I_END = float(ADDITIONAL_I_END)
        self.ADDITIONAL_J_END = float(ADDITIONAL_J_END)

        if USE_ADDITIONAL_J_END is None:
            USE_ADDITIONAL_J_END = (self.ADDITIONAL_J_END != 0.0)
        self.USE_ADDITIONAL_J_END = bool(USE_ADDITIONAL_J_END)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert this item to the exact dict shape MIDAS expects inside ITEMS[].
        This matches the JSON examples you gave.
        """
        out: Dict[str, Any] = {
            "ID": self.ID,
            "LCNAME": self.LCNAME,
            "GROUP_NAME": self.GROUP_NAME,
            "CMD": self.CMD,
            "TYPE": self.TYPE,
            "DIRECTION": self.DIRECTION,
            "USE_PROJECTION": self.USE_PROJECTION,
            "USE_ECCEN": self.USE_ECCEN,
            "D": self.D,
            "P": self.P,
        }

        # Only include these if eccentricity is actually in use
        if self.USE_ECCEN:
            out.update(
                {
                    "ECCEN_TYPE": self.ECCEN_TYPE,
                    "ECCEN_DIR": self.ECCEN_DIR,
                    "I_END": self.I_END,
                    "J_END": self.J_END,
                    "USE_J_END": self.USE_J_END,
                }
            )

        # Your 2nd sample shows these additional keys even for TYPE="UNILOAD".
        # To stay consistent and predictable, we ALWAYS include them.
        out.update(
            {
                "USE_ADDITIONAL": self.USE_ADDITIONAL,
                "ADDITIONAL_I_END": self.ADDITIONAL_I_END,
                "ADDITIONAL_J_END": self.ADDITIONAL_J_END,
                "USE_ADDITIONAL_J_END": self.USE_ADDITIONAL_J_END,
            }
        )

        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BeamLoadItem":
        """
        Parse a dict from MIDAS GET /db/bmld back into a BeamLoadItem.
        """
        return cls(
            ID=data.get("ID"),
            LCNAME=data.get("LCNAME", ""),
            GROUP_NAME=data.get("GROUP_NAME", ""),
            CMD=data.get("CMD", "BEAM"),
            TYPE=data.get("TYPE", "UNILOAD"),
            DIRECTION=data.get("DIRECTION", "GZ"),
            USE_PROJECTION=data.get("USE_PROJECTION", False),
            USE_ECCEN=data.get("USE_ECCEN", False),
            D=data.get("D", [0, 1, 0, 0]),
            P=data.get("P", [0, 0, 0, 0]),
            ECCEN_TYPE=data.get("ECCEN_TYPE", 1),
            ECCEN_DIR=data.get("ECCEN_DIR", "GX"),
            I_END=data.get("I_END", 0.0),
            J_END=data.get("J_END", 0.0),
            USE_J_END=data.get("USE_J_END"),
            USE_ADDITIONAL=data.get("USE_ADDITIONAL", False),
            ADDITIONAL_I_END=data.get("ADDITIONAL_I_END", 0.0),
            ADDITIONAL_J_END=data.get("ADDITIONAL_J_END", 0.0),
            USE_ADDITIONAL_J_END=data.get("USE_ADDITIONAL_J_END"),
        )


class BeamLoadResource:
    """
    Resource interface for /db/bmld that matches the style
    of midas/resources/* and talks directly to MidasAPI.

    Key ideas:
    - GET /db/bmld returns something like:
        { "BMLD": {
            "115": { "ITEMS": [ {...}, {...} ] },
            "220": { "ITEMS": [ {...} ] }
        }}

    - PUT /db/bmld expects:
        { "Assign": {
            "115": { "ITEMS": [ {...}, {...} ] },
            "220": { "ITEMS": [ {...} ] }
        }}

    We expose helpers to:
    - read all existing beam loads into Python objects,
    - build an Assign payload from Python objects,
    - send that payload back to MIDAS.
    """

    PATH = "/db/bmld"
    READ_KEY = "BMLD"

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_raw(cls) -> Dict[str, Any]:
        """
        Raw GET to MIDAS.
        Returns the inner dict keyed by element IDs, or {} if none.
        """
        resp = MidasAPI("GET", cls.PATH) or {}
        return resp.get(cls.READ_KEY, {}) or {}

    @classmethod
    def put_raw(cls, assign_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Low-level PUT to MIDAS. You must pass a full {"Assign": {...}} payload.
        """
        return MidasAPI("PUT", cls.PATH, assign_payload)

    # ------------------------------------------------------------------
    # High-level builders
    # ------------------------------------------------------------------

    @staticmethod
    def build_assign_from_specs(
        specs: List[Tuple[int, BeamLoadItem]]
    ) -> Dict[str, Any]:
        """
        Take a list of (element_id, BeamLoadItem) pairs and group
        them into the {"Assign": {...}} structure required by PUT /db/bmld.

        Example input:
            [
                (115, BeamLoadItem(... ID=1, LCNAME="L", ...)),
                (115, BeamLoadItem(... ID=2, LCNAME="L2", ...)),
                (220, BeamLoadItem(... ID=1, LCNAME="L", ...)),
            ]

        Output:
            {
                "Assign": {
                    "115": {
                        "ITEMS": [
                            {...spec1...},
                            {...spec2...}
                        ]
                    },
                    "220": {
                        "ITEMS": [
                            {...spec3...}
                        ]
                    }
                }
            }
        """
        assign: Dict[str, Dict[str, Any]] = {}

        for element_id, item in specs:
            ekey = str(int(element_id))
            if ekey not in assign:
                assign[ekey] = {"ITEMS": []}
            assign[ekey]["ITEMS"].append(item.to_dict())

        return {"Assign": assign}

    @classmethod
    def create_from_specs(
        cls,
        specs: List[Tuple[int, BeamLoadItem]],
    ) -> Dict[str, Any]:
        """
        Convenience method:
        - Build the {"Assign": {...}} payload from your specs
        - PUT it to MIDAS in one call
        - Return MIDAS response

        This is the ONE call you make to 'send beam load to MIDAS'.
        """
        payload = cls.build_assign_from_specs(specs)
        return cls.put_raw(payload)

    # ------------------------------------------------------------------
    # Parsing existing model state (sync/readback)
    # ------------------------------------------------------------------

    @classmethod
    def get_all_items(cls) -> Dict[int, List[BeamLoadItem]]:
        """
        Read the model with GET /db/bmld and parse into Python objects.

        Returns:
            {
                115: [BeamLoadItem(...), BeamLoadItem(...)],
                220: [BeamLoadItem(...)]
            }
        """
        out: Dict[int, List[BeamLoadItem]] = {}
        raw = cls.get_raw()  # e.g. {"115":{"ITEMS":[{...},{...}]}, "220":{"ITEMS":[{...}]}}

        for elem_id_str, elem_block in raw.items():
            try:
                eid = int(elem_id_str)
            except ValueError:
                continue

            items_raw = elem_block.get("ITEMS", []) or []
            parsed_items: List[BeamLoadItem] = [
                BeamLoadItem.from_dict(item_dict) for item_dict in items_raw
            ]
            out[eid] = parsed_items

        return out
