# gui/dialogs/control_data/models.py

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import List, ClassVar


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


# --------------------------- Skew coefficients (existing) ---------------------------

@dataclass
class SkewCoefficients:
    """Fixed-angle skew table. Angles are immutable and not persisted."""
    ANGLES: ClassVar[tuple[int, ...]] = (0, 15, 30, 45, 60)

    transverse: List[float] = field(default_factory=lambda: [1.000, 0.880, 0.820, 0.660, 0.340])
    longitudinal: List[float] = field(default_factory=lambda: [0.000, 0.120, 0.240, 0.320, 0.380])

    def __post_init__(self):
        n = len(self.ANGLES)
        if len(self.transverse) != n or len(self.longitudinal) != n:
            raise ValueError(
                f"SkewCoefficients must have {n} entries for transverse and longitudinal."
            )

    @property
    def angles(self) -> List[int]:
        # convenience accessor for UIs
        return list(self.ANGLES)

@dataclass
class WindLiveLoadCoefficients:
    """Table 3.8.1.3-1 — Wind Load Components on Live Load"""
    ANGLES: ClassVar[tuple[int, ...]] = (0, 15, 30, 45, 60)

    transverse: List[float] = field(
        default_factory=lambda: [0.100, 0.088, 0.082, 0.066, 0.034]
    )
    longitudinal: List[float] = field(
        default_factory=lambda: [0.000, 0.012, 0.024, 0.032, 0.038]
    )

    def __post_init__(self):
        n = len(self.ANGLES)
        if len(self.transverse) != n or len(self.longitudinal) != n:
            raise ValueError(
                f"WindLiveLoadCoefficients must have {n} entries for transverse and longitudinal."
            )

    @property
    def angles(self) -> List[int]:
        return list(self.ANGLES)


# --- Wind / aerodynamic settings (existing) ---

@dataclass
class LoadSettings:
    """Wind or aerodynamic load-related coefficients."""
    gust_factor: float = 1.00

    # Split drag coefficient
    superstructure_drag_coefficient: float = 1.30
    substructure_drag_coefficient: float = 1.60

    crash_barrier_depth: float = 0.0            # length
    skew: SkewCoefficients = field(default_factory=SkewCoefficients)
    wind_live: WindLiveLoadCoefficients = field(default_factory=WindLiveLoadCoefficients)



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
            "version": 7,  # bump: split drag coefficient into super/sub
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

        # Accept both shapes:
        # - new (naming includes simplified 'wind')
        # - old (with now-removed angle/text fields) → gracefully ignore
        naming_in = data.get("naming", {}) or {}
        wind_in = naming_in.get("wind", {}) or {}

        loads_in = data.get("loads", {}) or {}

        skew_in = loads_in.get("skew", {}) or {}
        defaults_t = [1.000, 0.880, 0.820, 0.660, 0.340]
        defaults_l = [0.000, 0.120, 0.240, 0.320, 0.380]
        N = len(SkewCoefficients.ANGLES)
        t_in = list(skew_in.get("transverse", defaults_t) or defaults_t)
        g_in = list(skew_in.get("longitudinal", defaults_l) or defaults_l)
        # enforce completeness; if not exact length, use defaults
        t = t_in if len(t_in) == N else defaults_t
        g = g_in if len(g_in) == N else defaults_l

        # wind load on live load (new table)
        wind_live_in = loads_in.get("wind_live", {}) or {}
        wl_defaults_t = [0.100, 0.088, 0.082, 0.066, 0.034]
        wl_defaults_l = [0.000, 0.012, 0.024, 0.032, 0.038]
        M = len(WindLiveLoadCoefficients.ANGLES)

        wl_t_in = list(wind_live_in.get("transverse", wl_defaults_t) or wl_defaults_t)
        wl_l_in = list(wind_live_in.get("longitudinal", wl_defaults_l) or wl_defaults_l)

        wl_t = wl_t_in if len(wl_t_in) == M else wl_defaults_t
        wl_l = wl_l_in if len(wl_l_in) == M else wl_defaults_l

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

            loads=LoadSettings(
                gust_factor=float(loads_in.get("gust_factor", 1.00)),
                superstructure_drag_coefficient=float(loads_in.get("superstructure_drag_coefficient", 1.30)),
                substructure_drag_coefficient=float(loads_in.get("substructure_drag_coefficient", 1.60)),
                crash_barrier_depth=float(loads_in.get("crash_barrier_depth", 0.0)),
                skew=SkewCoefficients(transverse=t, longitudinal=g),
                wind_live=WindLiveLoadCoefficients(
                    transverse=wl_t,
                    longitudinal=wl_l,
                ),
            ),

            length_unit=lu,
            force_unit=fu,
        )
