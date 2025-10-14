# gui\dialogs\control_data_folder\pages\loads.py

from __future__ import annotations
from PySide6.QtWidgets import QWidget, QFormLayout, QDoubleSpinBox
from .base import ControlDataPage
from ..models import ControlDataModel, LoadSettings

class LoadsPage(QWidget, ControlDataPage):
    title = "Loads"

    def __init__(self, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)

        self.spin_gust = QDoubleSpinBox()
        self.spin_gust.setRange(0.5, 3.0); self.spin_gust.setSingleStep(0.05); self.spin_gust.setValue(1.00)

        self.spin_drag = QDoubleSpinBox()
        self.spin_drag.setRange(0.1, 5.0); self.spin_drag.setSingleStep(0.05); self.spin_drag.setValue(1.20)

        form.addRow("Gust Factor", self.spin_gust)
        form.addRow("Drag Coefficient", self.spin_drag)

    # ---- ControlDataPage API ----
    def get_length_labels(self): return []
    def get_force_labels(self):  return []

    def set_state_from_model(self, model: ControlDataModel) -> None:
        l = model.loads
        self.spin_gust.setValue(l.gust_factor)
        self.spin_drag.setValue(l.drag_coefficient)

    def apply_to_model(self, model: ControlDataModel) -> None:
        model.loads = LoadSettings(
            gust_factor=self.spin_gust.value(),
            drag_coefficient=self.spin_drag.value(),
        )

    def validate(self) -> tuple[bool, str]:
        return True, ""  # nothing special here

    def on_units_changed(self, units, prev_len: str, new_len: str, prev_force: str, new_force: str) -> None:
        pass  # nothing to do for this page
