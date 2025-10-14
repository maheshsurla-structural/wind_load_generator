# unit_manager\converter.py

_LENGTH_TO_M = {
    "MM": 0.001,
    "CM": 0.01,
    "M": 1.0,
    "IN": 0.0254,
    "FT": 0.3048,
}

_FORCE_TO_N = {
    "N": 1.0,
    "KN": 1_000.0,
    "LBF": 4.4482216152605,
    "KIPS": 4448.2216152605,
    "KGF": 9.80665,
    "TONF": 9_806.65,  # metric ton-force
}

def convert_length(value: float, from_sym: str, to_sym: str) -> float:
    f = _LENGTH_TO_M[from_sym.upper()]
    t = _LENGTH_TO_M[to_sym.upper()]
    return value * f / t

def convert_force(value: float, from_sym: str, to_sym: str) -> float:
    f = _FORCE_TO_N[from_sym.upper()]
    t = _FORCE_TO_N[to_sym.upper()]
    return value * f / t
