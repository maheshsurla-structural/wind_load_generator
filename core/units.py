# core/units.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

@dataclass(frozen=True)
class Unit:
    symbol: str
    to_base: float
    offset: float = 0.0
    aliases: Tuple[str, ...] = ()

class UnitRegistry:
    def __init__(self, units: Iterable[Unit], *, base_symbol: str):
        self._units: Dict[str, Unit] = {}
        self._base: str = base_symbol.upper()
        for u in units:
            for key in (u.symbol, *u.aliases):
                k = key.upper()
                if k in self._units:
                    raise ValueError(f"Duplicate unit key: {key}")
                self._units[k] = u
        if self._base not in self._units:
            raise ValueError(f"Base unit '{base_symbol}' not present.")

    def normalize(self, u: str) -> Unit:
        try:
            return self._units[u.upper()]
        except KeyError as e:
            raise ValueError(
                f"Unknown unit '{u}'. Options: {sorted({x.symbol for x in self._units.values()})}"
            ) from e

    def convert(self, value: float, from_unit: str, to_unit: str) -> float:
        u_from = self.normalize(from_unit)
        u_to   = self.normalize(to_unit)
        in_base = (value + u_from.offset) * u_from.to_base
        return (in_base / u_to.to_base) - u_to.offset

# Length (base: M) -> only MM, CM, M, IN, FT
LENGTH = UnitRegistry(
    units=(
        Unit("M",  1.0,    aliases=("METER", "METERS")),
        Unit("CM", 0.01,   aliases=("CENTIMETER", "CENTIMETERS")),
        Unit("MM", 0.001,  aliases=("MILLIMETER", "MILLIMETERS")),
        Unit("IN", 0.0254, aliases=("INCH", "INCHES")),
        Unit("FT", 0.3048, aliases=("FOOT", "FEET")),
    ),
    base_symbol="M",
)

# Force (base: N) -> only KGF, TONF, N, KN, LBF, KIP
FORCE = UnitRegistry(
    units=(
        Unit("N",   1.0),
        Unit("KN",  1000.0),
        Unit("LBF", 4.4482216152605, aliases=("LB", "POUND", "POUNDS")),
        Unit("KIP", 4448.2216152605, aliases=("KIPS",)),
        Unit("KGF", 9.80665),
        Unit("TONF", 9806.65, aliases=("TF", "TON-FORCE")),
    ),
    base_symbol="N",
)

def convert_length(v: float, from_u: str, to_u: str) -> float:
    return LENGTH.convert(v, from_u, to_u)

def convert_force(v: float, from_u: str, to_u: str) -> float:
    return FORCE.convert(v, from_u, to_u)
