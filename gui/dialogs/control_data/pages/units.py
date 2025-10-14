# gui\dialogs\control_data_folder\pages\units.py

from __future__ import annotations
from PySide6.QtWidgets import QWidget, QFormLayout, QLabel
from .base import ControlDataPage
from ..models import ControlDataModel

class UnitsPage(QWidget, ControlDataPage):
    title = "Units"

    def __init__(self, units, parent=None):
        super().__init__(parent)
        self._length_labels = []
        self._force_labels = []

        form = QFormLayout(self)
        self.lbl_length = QLabel(units.length)
        self.lbl_force  = QLabel(units.force)
        form.addRow("Active Length Unit", self.lbl_length)
        form.addRow("Active Force Unit", self.lbl_force)

        self._length_labels.append(self.lbl_length)
        self._force_labels.append(self.lbl_force)

    # ---- ControlDataPage API ----
    def get_length_labels(self): return self._length_labels
    def get_force_labels(self):  return self._force_labels

    def set_state_from_model(self, model: ControlDataModel) -> None: pass
    def apply_to_model(self, model: ControlDataModel) -> None: pass
    def validate(self) -> tuple[bool, str]: return True, ""

    def on_units_changed(self, units, prev_len: str, new_len: str, prev_force: str, new_force: str) -> None:
        for lab in self._length_labels: lab.setText(new_len)
        for lab in self._force_labels:  lab.setText(new_force)
