# unit_system.py

from PySide6.QtWidgets import QApplication, QComboBox, QLabel

from PySide6.QtCore import QObject, Signal

from typing import Optional, Sequence

class UnitSystem(QObject):

    # Signals when values change
    force_unit_signal = Signal(str)
    length_unit_signal = Signal(str)

    def __init__(self, force_unit, length_unit):

        super().__init__()
        self.force_unit = force_unit
        self.length_unit = length_unit

        self.force_unit.currentTextChanged.connect(self.force_unit_signal)
        self.length_unit.currentTextChanged.connect(self.length_unit_signal)

        # Register globally so any dialog can find this hub
        app = QApplication.instance()
        if app is not None:
            app.setProperty("unitSystem", self)


    # Read current units any time
    @property
    def force(self) -> str:
        return self.force_unit.currentText()

    @property
    def length(self) -> str:
        return self.length_unit.currentText()


def get_unit_system() -> Optional[UnitSystem]:
    """Fetch the global UnitSystem set by MainWindow."""
    app = QApplication.instance()
    return app.property("unitSystem") if app else None



class UnitAwareMixin:
    length_unit_labels: Sequence[QLabel] | None = None
    force_unit_labels: Sequence[QLabel] | None = None

    def bind_units(self) -> None:
        unit_system = get_unit_system()
        if not unit_system:
            return
        # keep a ref so we can disconnect later if needed
        self._unit_system = unit_system

        # Initial paint
        self.update_units(unit_system.force, unit_system.length)

        # IMPORTANT: connect to bound methods (Qt will auto-disconnect on deletion)
        unit_system.force_unit_signal.connect(self._on_force_unit_changed)
        unit_system.length_unit_signal.connect(self._on_length_unit_changed)

        # Belt & suspenders: if this object is destroyed, disconnect explicitly.
        # (Even though bound-method connections auto-disconnect, this guarantees cleanup
        #  in case someone overrides close behavior.)
        if isinstance(self, QObject):
            self.destroyed.connect(self._units_teardown)

    # Slots called by the UnitSystem signals
    def _on_force_unit_changed(self, value: str) -> None:
        # pull the current length from the hub to pass both values to update_units
        unit_system = getattr(self, "_unit_system", None) or get_unit_system()
        if unit_system:
            self.update_units(value, unit_system.length)

    def _on_length_unit_changed(self, value: str) -> None:
        unit_system = getattr(self, "_unit_system", None) or get_unit_system()
        if unit_system:
            self.update_units(unit_system.force, value)

    def _units_teardown(self, *args) -> None:
        """Disconnect signals when this dialog is going away."""
        unit_system = getattr(self, "_unit_system", None)
        if unit_system:
            try:
                unit_system.force_unit_signal.disconnect(self._on_force_unit_changed)
            except TypeError:
                pass
            try:
                unit_system.length_unit_signal.disconnect(self._on_length_unit_changed)
            except TypeError:
                pass
            self._unit_system = None

    def update_units(self, force_unit: str, length_unit: str) -> None:
        # Default behavior: update registered labels.
        if getattr(self, "length_unit_labels", None):
            for lbl in self.length_unit_labels:  # type: ignore[attr-defined]
                if lbl:  # lbl is a QObject; safe to call setText while alive
                    lbl.setText(length_unit)
        if getattr(self, "force_unit_labels", None):
            for lbl in self.force_unit_labels:   # type: ignore[attr-defined]
                if lbl:
                    lbl.setText(force_unit)

