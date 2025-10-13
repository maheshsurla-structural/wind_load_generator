# core/unit_manager.py
from typing import Optional
from gui.unit_system import UnitSystem

# Singleton instance
__UNITS: Optional[UnitSystem] = None

def get_unit_manager() -> UnitSystem:
    """Return the global UnitSystem instance (creates on first use)."""
    global __UNITS
    if __UNITS is None:
        __UNITS = UnitSystem(length_symbol="FT", force_symbol="KIPS")
    return __UNITS

def set_units(*, length: Optional[str] = None, force: Optional[str] = None) -> UnitSystem:
    """Programmatic update; emits unitsChanged exactly like UI would."""
    u = get_unit_manager()
    if length:
        u.set_length(length)
    if force:
        u.set_force(force)
    return u
