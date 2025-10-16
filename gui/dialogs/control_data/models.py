# gui\dialogs\control_data\models.py

from __future__ import annotations
from dataclasses import dataclass, asdict, field

@dataclass
class GeometrySettings:
    """Geometric parameters defining the structure's reference levels and Pier proximity radius."""

    reference_height: float = 0.0
    pier_radius: float = 10.0


@dataclass
class NamingRules:
    """Rules controlling how structural elements are named."""

    deck_name: str = "Deck"
    pier_base_name: str = "Pier"
    starting_index: int = 1
    suffix_above: str = "_SubAbove"
    suffix_below: str = "_SubBelow"


@dataclass
class LoadSettings:
    """Wind or aerodynamic load-related coefficients."""

    gust_factor: float = 1.00
    drag_coefficient: float = 1.20


@dataclass
class ControlDataModel:
    """Comprehensive model encapsulating geometry, naming, load settings, and unit preferences."""

    geometry: GeometrySettings = field(default_factory=GeometrySettings)
    naming: NamingRules = field(default_factory=NamingRules)
    loads: LoadSettings = field(default_factory=LoadSettings)
    length_unit: str = "FT"
    force_unit: str = "KIPS"

    def to_dict(self) -> dict:
        return {
            "geometry": asdict(self.geometry),
            "naming": asdict(self.naming),
            "loads": asdict(self.loads),
            "units": {"length": self.length_unit, "force": self.force_unit},
        }

    @staticmethod
    def from_dict(data: dict) -> "ControlDataModel":
        lu = data.get("units", {}).get("length", "FT")
        fu = (data.get("units", {}).get("force", "KIPS") or "").upper()
        if fu == "KIP":
            fu = "KIPS"
        return ControlDataModel(
            geometry=GeometrySettings(**data.get("geometry", {})),
            naming=NamingRules(**data.get("naming", {})),
            loads=LoadSettings(**data.get("loads", {})),
            length_unit=lu,
            force_unit=fu,
        )
