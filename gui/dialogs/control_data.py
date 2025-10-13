# gui/dialogs/control_data.py
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton,
    QListWidget, QStackedWidget, QSplitter, QWidget, QMessageBox
)
from PySide6.QtGui import QDoubleValidator

from gui.unit_system import UnitAwareMixin, UnitSystem

log = logging.getLogger(__name__)


# --------------------------- Data Models ---------------------------

@dataclass
class StructuralSettings:
    reference_height: float = 0.0
    pier_radius: float = 10.0


@dataclass
class NamingSettings:
    deck_name: str = "Deck"
    pier_base_name: str = "Pier"
    starting_index: int = 1
    suffix_above: str = "_SubAbove"
    suffix_below: str = "_SubBelow"


@dataclass
class LoadSettings:
    gust_factor: float = 1.00
    drag_coefficient: float = 1.20


@dataclass
class ControlDataModel:
    
    structural: StructuralSettings = field(default_factory=StructuralSettings)
    naming: NamingSettings = field(default_factory=NamingSettings)
    loads: LoadSettings = field(default_factory=LoadSettings)
    length_unit: str = "FT"
    force_unit: str = "KIPS"

    def to_dict(self) -> dict:
        return {
            "structural": asdict(self.structural),
            "naming": asdict(self.naming),
            "loads": asdict(self.loads),
            "units": {"length": self.length_unit, "force": self.force_unit},
        }

    @staticmethod
    def from_dict(data: dict) -> "ControlDataModel":
        lu = data.get("units", {}).get("length", "FT")
        fu = data.get("units", {}).get("force", "KIPS")
        fu = fu.upper()
        if fu == "KIP":
            fu = "KIPS"
        return ControlDataModel(
            structural=StructuralSettings(**data.get("structural", {})),
            naming=NamingSettings(**data.get("naming", {})),
            loads=LoadSettings(**data.get("loads", {})),
            length_unit=lu,
            force_unit=fu,
        )


# --------------------------- Dialog ---------------------------

class ControlData(QDialog, UnitAwareMixin):

    """Control Data dialog with dataclass model and unit-aware value conversion."""
    controlDataChanged = Signal(object)

    def __init__(self, parent: Optional[QObject] = None, *, units: Optional[UnitSystem] = None):
        super().__init__(parent)
        self.setWindowTitle("Control Data")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(820, 460)

        self.units = units or getattr(parent, "units", UnitSystem())
        self.model = ControlDataModel(length_unit=self.units.length, force_unit=self.units.force)

        # remember the previous length unit to convert values on change
        self._prev_len_unit = self.units.length

        self._setup_ui()
        self.bind_units(self.units)   # will call update_units(...) once

        # default to first page
        self.section_list.setCurrentRow(0)

    # ---------------- UI ----------------

    def _setup_ui(self) -> None:
        self.section_list = QListWidget()
        self.section_list.addItems(["Structural", "Loads", "Units"])
        self.section_list.setFixedWidth(220)

        self.length_unit_labels: list[QLabel] = []
        self.force_unit_labels: list[QLabel] = []


        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_structural_page())
        self.pages.addWidget(self._build_loads_page())
        self.pages.addWidget(self._build_units_page())

        splitter = QSplitter()
        splitter.addWidget(self.section_list)
        splitter.addWidget(self.pages)
        splitter.setStretchFactor(1, 1)

        self.btn_defaults = QPushButton("Restore Defaults")
        self.btn_apply = QPushButton("Apply")
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancel")

        btns = QHBoxLayout()
        btns.addWidget(self.btn_defaults)
        btns.addStretch()
        btns.addWidget(self.btn_apply)
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)

        root = QVBoxLayout(self)
        root.addWidget(splitter)
        root.addLayout(btns)

        self.section_list.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.btn_defaults.clicked.connect(self.restore_defaults)
        self.btn_apply.clicked.connect(self.apply_changes)
        self.btn_ok.clicked.connect(lambda: (self.apply_changes(), self.accept()))
        self.btn_cancel.clicked.connect(self.reject)



    def _build_structural_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.txt_ground = QLineEdit("0.0")
        self.txt_ground.setValidator(QDoubleValidator(0.0, 1e9, 3, self))
        self.txt_radius = QLineEdit("10.0")
        self.txt_radius.setValidator(QDoubleValidator(0.0, 1e9, 3, self))
        self.lbl_len1, self.lbl_len2 = QLabel("?"), QLabel("?")

        # NOTE: unpack the (label, widget) tuple for addRow
        form.addRow(*self._row("Ground Level", self.txt_ground, self.lbl_len1))
        form.addRow(*self._row("Pier Proximity Radius", self.txt_radius, self.lbl_len2))

        naming = QGroupBox("Naming Rules")
        nform = QFormLayout(naming)
        self.txt_deck = QLineEdit("Deck")
        self.txt_pier = QLineEdit("Pier")
        self.spin_start = QSpinBox()
        self.spin_start.setRange(1, 9999)
        self.txt_above = QLineEdit("_SubAbove")
        self.txt_below = QLineEdit("_SubBelow")
        nform.addRow("Deck Name", self.txt_deck)
        nform.addRow("Pier Base Name", self.txt_pier)
        nform.addRow("Starting Index", self.spin_start)
        nform.addRow("Suffix Above", self.txt_above)
        nform.addRow("Suffix Below", self.txt_below)
        form.addRow(naming)

        # labels for UnitAwareMixin default behavior
        self.length_unit_labels.extend([self.lbl_len1, self.lbl_len2])
        return page

    def _build_loads_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.spin_gust = QDoubleSpinBox()
        self.spin_gust.setRange(0.5, 3.0)
        self.spin_gust.setSingleStep(0.05)
        self.spin_gust.setValue(1.00)

        self.spin_drag = QDoubleSpinBox()
        self.spin_drag.setRange(0.1, 5.0)
        self.spin_drag.setSingleStep(0.05)
        self.spin_drag.setValue(1.20)

        form.addRow("Gust Factor", self.spin_gust)
        form.addRow("Drag Coefficient", self.spin_drag)
        return page

    def _build_units_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.lbl_length = QLabel(self.units.length)
        self.lbl_force = QLabel(self.units.force)
        form.addRow("Active Length Unit", self.lbl_length)
        form.addRow("Active Force Unit", self.lbl_force)

        # keep synced with mixin
        self.length_unit_labels.append(self.lbl_length)
        self.force_unit_labels.append(self.lbl_force)
        return page

    # ---------------- Unit handling ----------------

    def update_units(self, length_unit: str, force_unit: str) -> None:
        print("[ControlData] update_units", length_unit, force_unit)
        # Convert existing numeric values if length unit changed
        prev = getattr(self, "_prev_len_unit", length_unit)
        if prev != length_unit:
            self._convert_lineedit_length(self.txt_ground, prev, length_unit)
            self._convert_lineedit_length(self.txt_radius, prev, length_unit)
        self._prev_len_unit = length_unit

        # --- explicitly update all unit labels (don’t rely on the mixin) ---
        for lab in getattr(self, "length_unit_labels", []):
            lab.setText(length_unit)
        for lab in getattr(self, "force_unit_labels", []):
            lab.setText(force_unit)

        # Call parent in case it does anything else useful
        try:
            super().update_units(length_unit, force_unit)
        except AttributeError:
            # If UnitAwareMixin has no update_units, ignore.
            pass



    def _convert_lineedit_length(self, le: QLineEdit, old_u: str, new_u: str) -> None:
        txt = (le.text() or "").strip()
        try:
            v_old = float(txt)
        except ValueError:
            return
        v_new = self.units.convert_length_between(v_old, old_u, new_u)
        le.setText(f"{v_new:g}")

    # ---------------- Logic ----------------

    def restore_defaults(self) -> None:
        self.model = ControlDataModel(length_unit=self.units.length, force_unit=self.units.force)
        self._set_model_to_ui()
        self._prev_len_unit = self.units.length   # keep baseline in sync
        log.info("ControlData: restored defaults")


    def validate(self) -> Tuple[bool, str]:
        try:
            h = float(self.txt_ground.text())
            r = float(self.txt_radius.text())
        except ValueError:
            return False, "Ground Level and Pier Radius must be numeric."
        if h < 0 or r < 0:
            return False, "Values must be non-negative."
        if not self.txt_deck.text().strip():
            return False, "Deck name cannot be empty."
        return True, ""

    def apply_changes(self) -> None:
        ok, msg = self.validate()
        if not ok:
            QMessageBox.warning(self, "Invalid Data", msg)
            return

        self.model.structural = StructuralSettings(
            reference_height=float(self.txt_ground.text()),
            pier_radius=float(self.txt_radius.text()),
        )
        self.model.naming = NamingSettings(
            deck_name=self.txt_deck.text().strip(),
            pier_base_name=self.txt_pier.text().strip(),
            starting_index=self.spin_start.value(),
            suffix_above=self.txt_above.text().strip(),
            suffix_below=self.txt_below.text().strip(),
        )
        self.model.loads = LoadSettings(
            gust_factor=self.spin_gust.value(),
            drag_coefficient=self.spin_drag.value(),
        )
        self.model.length_unit = self.units.length
        self.model.force_unit = self.units.force

        self.controlDataChanged.emit(self.model)
        log.info("ControlData: applied %s", self.model)

    # ---------------- Backward-compatible API ----------------

    def set_payload(self, payload: dict) -> None:
        try:
            self.model = ControlDataModel.from_dict(payload)
            self._set_model_to_ui()

            # What units are the payload numbers in?
            payload_len = self.model.length_unit
            payload_force = self.model.force_unit

            # What units are active globally (or fall back to payload units)?
            current_len = self.units.length if self.units else payload_len
            current_force = self.units.force if self.units else payload_force

            # If payload length unit differs from current, convert the numeric fields now
            if payload_len != current_len:
                self._convert_lineedit_length(self.txt_ground, payload_len, current_len)
                self._convert_lineedit_length(self.txt_radius, payload_len, current_len)

            # Show the current units on the labels
            self.update_units(current_len, current_force)

            # Make future changes compare against the *current* unit
            self._prev_len_unit = current_len

        except Exception as e:
            log.exception("ControlData.set_payload failed: %s", e)



    # ---------------- Helpers ----------------

    def _row(self, label_text: str, editor: QWidget, unit_label: QLabel) -> tuple[QLabel, QWidget]:
        lab = QLabel(label_text)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(editor, 1)
        h.addWidget(unit_label)
        return lab, row

    def _set_model_to_ui(self) -> None:
        s, n, l = self.model.structural, self.model.naming, self.model.loads
        self.txt_ground.setText(f"{s.reference_height:g}")
        self.txt_radius.setText(f"{s.pier_radius:g}")
        self.txt_deck.setText(n.deck_name)
        self.txt_pier.setText(n.pier_base_name)
        self.spin_start.setValue(n.starting_index)
        self.txt_above.setText(n.suffix_above)
        self.txt_below.setText(n.suffix_below)
        self.spin_gust.setValue(l.gust_factor)
        self.spin_drag.setValue(l.drag_coefficient)
        # labels are updated via update_units through bind_units
