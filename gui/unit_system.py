# gui/unit_system.py
from PySide6.QtCore import QObject, Signal
from core.units import convert_length, convert_force

class UnitSystem(QObject):
    """
    Global unit manager; emits unitsChanged(length, force) when either changes.
    """
    unitsChanged = Signal(str, str)

    def __init__(self, length_symbol: str = "FT", force_symbol: str = "KIPS"):
        super().__init__()
        self._length = length_symbol.upper()
        self._force  = force_symbol.upper()

    # ---- properties ----
    @property
    def length(self) -> str:
        return self._length

    @property
    def force(self) -> str:
        return self._force

    # ---- setters emit ----
    def set_length(self, symbol: str) -> None:
        s = symbol.upper()
        if s != self._length:
            print("[UnitSystem] set_length ->", s)  # debug
            self._length = s
            self.unitsChanged.emit(self._length, self._force)

    def set_force(self, symbol: str) -> None:
        s = symbol.upper()
        if s != self._force:
            print("[UnitSystem] set_force  ->", s)  # debug
            self._force = s
            self.unitsChanged.emit(self._length, self._force)

    # ---- base conversions (M, N as base) ----
    def from_base_length(self, meters: float) -> float:
        return convert_length(meters, "M", self._length)

    def to_base_length(self, value: float) -> float:
        return convert_length(value, self._length, "M")

    def from_base_force(self, newtons: float) -> float:
        return convert_force(newtons, "N", self._force)

    def to_base_force(self, value: float) -> float:
        return convert_force(value, self._force, "N")

    # ---- any-to-any convenience ----
    def convert_length_between(self, value: float, from_unit: str, to_unit: str) -> float:
        return convert_length(value, from_unit.upper(), to_unit.upper())

    def convert_force_between(self, value: float, from_unit: str, to_unit: str) -> float:
        return convert_force(value, from_unit.upper(), to_unit.upper())


# ======================================================================
# Helper mixin for auto-updating widgets when units change
# ======================================================================

class UnitAwareMixin:
    """
    Simple: bind once; update labels in update_units.
    (This matches your previously working approach.)
    """
    _units: UnitSystem | None = None

    def bind_units(self, units: UnitSystem | None) -> None:
        self._units = units
        if units is None:
            return
        # initial sync
        self.update_units(units.length, units.force)
        # subscribe
        units.unitsChanged.connect(self._on_units_changed_proxy)

    def _on_units_changed_proxy(self, length_unit: str, force_unit: str):
        self.update_units(length_unit, force_unit)

    def update_units(self, length_unit: str, force_unit: str) -> None:
        for lab in getattr(self, "length_unit_labels", []):
            lab.setText(length_unit)
        for lab in getattr(self, "force_unit_labels", []):
            lab.setText(force_unit)
