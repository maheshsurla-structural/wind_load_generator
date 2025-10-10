# gui/unit_system.py
from PySide6.QtCore import QObject, Signal
from core.units import convert_length, convert_force

class UnitSystem(QObject):
    unitsChanged = Signal(str, str)  # (length_unit, force_unit)

    def __init__(self, length_symbol: str = "FT", force_symbol: str = "KIP"):
        super().__init__()
        self._length = length_symbol.upper()
        self._force  = force_symbol.upper()

    @property
    def length(self) -> str: return self._length
    @property
    def force(self)  -> str: return self._force

    def set_length(self, symbol: str):
        s = symbol.upper()
        if s != self._length:
            self._length = s
            self.unitsChanged.emit(self._length, self._force)

    def set_force(self, symbol: str):
        s = symbol.upper()
        if s != self._force:
            self._force = s
            self.unitsChanged.emit(self._length, self._force)

    # base conversions (M, N as base)
    def from_base_length(self, meters: float) -> float:
        return convert_length(meters, "M", self._length)

    def to_base_length(self, value: float) -> float:
        return convert_length(value, self._length, "M")

    def from_base_force(self, newtons: float) -> float:
        return convert_force(newtons, "N", self._force)

    def to_base_force(self, value: float) -> float:
        return convert_force(value, self._force, "N")


# ---- Optional helper: make any widget unit-aware ----
class UnitAwareMixin:
    """
    Call self.bind_units(units) in __init__ AFTER creating any labels and
    populating self.length_unit_labels / self.force_unit_labels (lists of QLabel).
    """
    def bind_units(self, units: UnitSystem | None):
        self._units = units
        if units is None:
            return
        # immediate sync + subscribe to future changes
        self.update_units(units.length, units.force)
        units.unitsChanged.connect(self._on_units_changed_proxy)

    def _on_units_changed_proxy(self, length_unit: str, force_unit: str):
        self.update_units(length_unit, force_unit)

    def update_units(self, length_unit: str, force_unit: str) -> None:
        # Default behavior: push text into any registered unit labels
        for lab in getattr(self, "length_unit_labels", []):
            lab.setText(length_unit)
        for lab in getattr(self, "force_unit_labels", []):
            lab.setText(force_unit)
