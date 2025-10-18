# gui/dialogs/control_data/models.py

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import List

# --------------------------- Geometry ---------------------------

@dataclass
class GeometrySettings:
    """Geometric parameters defining the structure's reference levels and Pier proximity radius."""
    reference_height: float = 0.0
    pier_radius: float = 10.0


# --------------------------- Wind-load naming (simplified) ---------------------------

CaseCode = str  # e.g., "III", "V", "I", "IV"

@dataclass
class AngleFormat:
    # simplified: only the prefix is configurable
    prefix: str = "Ang"

@dataclass
class TextFormat:
    # Tokens: {base}, {limit}, {case}, {angle_prefix}, {angle}
    # simplified: uppercase flag removed — users can bake case/style into template/prefix if desired
    template: str = "{base}_{limit}_{case}_{angle_prefix}_{angle}"

@dataclass
class LimitStateLabels:
    strength_label: str = "ULS"
    service_label: str = "SLS"

@dataclass
class CaseSets:
    strength_cases: List[CaseCode] = field(default_factory=lambda: ["III", "V"])
    service_cases: List[CaseCode] = field(default_factory=lambda: ["I", "IV"])

@dataclass
class BasePrefixes:
    wind_on_structure: str = "WS"
    wind_on_live_load: str = "WL"

@dataclass
class WindLoadNamingSettings:
    bases: BasePrefixes = field(default_factory=BasePrefixes)
    limit_state_labels: LimitStateLabels = field(default_factory=LimitStateLabels)
    cases: CaseSets = field(default_factory=CaseSets)
    angle: AngleFormat = field(default_factory=AngleFormat)
    text: TextFormat = field(default_factory=TextFormat)


# --------------------------- Structural naming (existing) ---------------------------

@dataclass
class NamingRules:
    """Rules controlling how structural elements are named."""
    deck_name: str = "Deck"
    pier_base_name: str = "Pier"
    starting_index: int = 1
    suffix_above: str = "_SubAbove"
    suffix_below: str = "_SubBelow"

    # wind naming lives here, so existing code using `naming.xxx` still works
    wind: WindLoadNamingSettings = field(default_factory=WindLoadNamingSettings)


# --------------------------- Wind / aerodynamic settings (existing) ---------------------------

@dataclass
class LoadSettings:
    """Wind or aerodynamic load-related coefficients."""
    gust_factor: float = 1.00
    drag_coefficient: float = 1.20


# --------------------------- Master control model (existing API retained) ---------------------------

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
            "version": 4,  # bump: wind naming simplification (removed fields)
            "geometry": asdict(self.geometry),
            "naming": asdict(self.naming),   # includes nested 'wind'
            "loads": asdict(self.loads),
            "units": {"length": self.length_unit, "force": self.force_unit},
        }

    @staticmethod
    def from_dict(data: dict) -> "ControlDataModel":
        lu = data.get("units", {}).get("length", "FT")
        fu = (data.get("units", {}).get("force", "KIPS") or "").upper()
        if fu == "KIP":
            fu = "KIPS"

        # Accept both shapes:
        # - new (naming includes simplified 'wind')
        # - old (with now-removed angle/text fields) → gracefully ignore
        naming_in = data.get("naming", {}) or {}
        wind_in = naming_in.get("wind", {}) or {}

        return ControlDataModel(
            geometry=GeometrySettings(**(data.get("geometry", {}) or {})),
            naming=NamingRules(
                deck_name=naming_in.get("deck_name", "Deck"),
                pier_base_name=naming_in.get("pier_base_name", "Pier"),
                starting_index=int(naming_in.get("starting_index", 1)),
                suffix_above=naming_in.get("suffix_above", "_SubAbove"),
                suffix_below=naming_in.get("suffix_below", "_SubBelow"),
                wind=WindLoadNamingSettings(
                    bases=BasePrefixes(**(wind_in.get("bases", {}) or {})),
                    limit_state_labels=LimitStateLabels(**(wind_in.get("limit_state_labels", {}) or {})),
                    cases=CaseSets(**(wind_in.get("cases", {}) or {})),
                    angle=AngleFormat(prefix=(wind_in.get("angle", {}) or {}).get("prefix", "Ang")),
                    text=TextFormat(
                        template=(wind_in.get("text", {}) or {}).get(
                            "template", "{base}_{limit}_{case}_{angle_prefix}_{angle}"
                        )
                    ),
                ),
            ),
            loads=LoadSettings(**(data.get("loads", {}) or {})),
            length_unit=lu,
            force_unit=fu,
        )
