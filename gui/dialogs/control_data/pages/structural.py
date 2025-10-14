#gui\dialogs\control_data_folder\pages\structural.py

from __future__ import annotations
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QLabel, QGroupBox, QFormLayout, QSpinBox, QHBoxLayout
from PySide6.QtGui import QDoubleValidator
from .base import ControlDataPage
from ..models import ControlDataModel, GeometrySettings, NamingRules

class StructuralPage(QWidget, ControlDataPage):
    title = "Structural Group Classification"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._length_labels: list[QLabel] = []

        form = QFormLayout(self)

        self.txt_ground = QLineEdit("0.0")
        self.txt_ground.setValidator(QDoubleValidator(0.0, 1e9, 3, self))
        self.txt_radius = QLineEdit("10.0")
        self.txt_radius.setValidator(QDoubleValidator(0.0, 1e9, 3, self))
        self.lbl_len1, self.lbl_len2 = QLabel("?"), QLabel("?")
        form.addRow(*self._row("Ground Level", self.txt_ground, self.lbl_len1))
        form.addRow(*self._row("Pier Proximity Radius", self.txt_radius, self.lbl_len2))
        self._length_labels.extend([self.lbl_len1, self.lbl_len2])

        naming = QGroupBox("Naming Rules", self)
        nform = QFormLayout(naming)
        self.txt_deck = QLineEdit("Deck")
        self.txt_pier = QLineEdit("Pier")
        self.spin_start = QSpinBox(); self.spin_start.setRange(1, 9999)
        self.txt_above = QLineEdit("_SubAbove")
        self.txt_below = QLineEdit("_SubBelow")
        nform.addRow("Deck Name", self.txt_deck)
        nform.addRow("Pier Base Name", self.txt_pier)
        nform.addRow("Starting Index", self.spin_start)
        nform.addRow("Suffix Above", self.txt_above)
        nform.addRow("Suffix Below", self.txt_below)
        form.addRow(naming)

    # ---- ControlDataPage API ----
    def get_length_labels(self): 
        return self._length_labels
    
    def get_force_labels(self):  
        return []  

    def set_state_from_model(self, model: ControlDataModel) -> None:
        s, n = model.geometry, model.naming
        self.txt_ground.setText(f"{s.reference_height:g}")
        self.txt_radius.setText(f"{s.pier_radius:g}")
        self.txt_deck.setText(n.deck_name)
        self.txt_pier.setText(n.pier_base_name)
        self.spin_start.setValue(n.starting_index)
        self.txt_above.setText(n.suffix_above)
        self.txt_below.setText(n.suffix_below)

    def apply_to_model(self, model: ControlDataModel) -> None:
        model.geometry = GeometrySettings(
            reference_height=float(self.txt_ground.text() or 0),
            pier_radius=float(self.txt_radius.text() or 0),
        )
        model.naming = NamingRules(
            deck_name=self.txt_deck.text().strip(),
            pier_base_name=self.txt_pier.text().strip(),
            starting_index=self.spin_start.value(),
            suffix_above=self.txt_above.text().strip(),
            suffix_below=self.txt_below.text().strip(),
        )

    def validate(self) -> tuple[bool, str]:
        try:
            h = float(self.txt_ground.text()); r = float(self.txt_radius.text())
        except ValueError:
            return False, "Ground Level and Pier Radius must be numeric."
        if h < 0 or r < 0:
            return False, "Values must be non-negative."
        if not self.txt_deck.text().strip():
            return False, "Deck name cannot be empty."
        return True, ""

    def on_units_changed(self, units, prev_len: str, new_len: str, prev_force: str, new_force: str) -> None:
        # convert the two length fields if unit changed
        if prev_len != new_len:
            self._convert_lineedit_length(self.txt_ground, units, prev_len, new_len)
            self._convert_lineedit_length(self.txt_radius, units, prev_len, new_len)
        for lab in self._length_labels:
            lab.setText(new_len)

    # ---- helpers ----
    def _row(self, label_text, editor, unit_label):
        lab = QLabel(label_text)
        row = QWidget()
        h = QHBoxLayout(row); h.setContentsMargins(0,0,0,0); h.setSpacing(8)
        h.addWidget(editor, 1); h.addWidget(unit_label)
        return lab, row

    def _convert_lineedit_length(self, le: QLineEdit, units, old_u: str, new_u: str) -> None:
        t = (le.text() or "").strip()
        try:
            v_old = float(t)
        except ValueError:
            return
        v_new = units.convert_length_between(v_old, old_u, new_u)
        le.setText(f"{v_new:g}")
