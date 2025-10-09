# control_data.py
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QListWidget, QStackedWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QDoubleSpinBox,
    QComboBox, QPushButton, QLineEdit, QGroupBox, QGridLayout, QSpinBox
)

from PySide6.QtGui import QIntValidator, QDoubleValidator, QAction

# IMPORTANT: this imports your mixin from your unit_system.py
from gui.unit_system import UnitAwareMixin


class ControlData(QDialog, UnitAwareMixin):
    """
    Stand-alone, non-modal dialog for Control Data.
    - Left: section list (fixed)
    - Right: stacked pages with form rows
    - Bottom: Restore Defaults | Apply | OK | Cancel
    - Unit labels (length/force) auto-sync via UnitAwareMixin.bind_units()
    """
    controlDataChanged = Signal(dict)

    def __init__(self, parent=None):

        super().__init__(parent)
        self.setWindowTitle("Control Data")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # single-instance friendly
        self.resize(400, 400)

        # --- Left sections ---
        self.section_list = QListWidget()
        self.section_list.addItems([
            "Structural Group Classification",
            "Loads",
            "Units"
        ])
        self.section_list.setFixedWidth(200)

        # --- Right pages ---
        self.pages = QStackedWidget()
        self.page_structural = self._page_structural_group_classification()
        self.page_loads = self._build_loads_page()
        self.page_units = self._build_units_page()

        self.pages.addWidget(self.page_structural)
        self.pages.addWidget(self.page_loads)
        self.pages.addWidget(self.page_units)

        # --- Splitter ---
        splitter = QSplitter()
        splitter.addWidget(self.section_list)
        splitter.addWidget(self.pages)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # --- Bottom buttons ---
        btn_defaults = QPushButton("Restore Defaults")
        btn_apply    = QPushButton("Apply")
        btn_ok       = QPushButton("OK")
        btn_cancel   = QPushButton("Cancel")

        btn_defaults.clicked.connect(self.restore_defaults)
        btn_apply.clicked.connect(self.apply_changes)
        btn_ok.clicked.connect(lambda: (self.apply_changes(), self.accept()))
        btn_cancel.clicked.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(btn_defaults)
        bottom.addStretch(1)
        bottom.addWidget(btn_apply)
        bottom.addWidget(btn_ok)
        bottom.addWidget(btn_cancel)

        # --- Root layout ---
        root = QVBoxLayout(self)
        root.addWidget(splitter)
        root.addLayout(bottom)

        # wiring
        self.section_list.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.section_list.setCurrentRow(0)

        # 🔗 make this dialog unit-aware (labels will sync immediately + on changes)
        self.bind_units()

    # ---------------------------------------------------------------------
    # Pages
    # ---------------------------------------------------------------------



    def _page_structural_group_classification(self) -> QWidget:
        
        """
        Structural Group Classification page
        (all geometry fields use LENGTH units).
        """

        widget = QWidget()
        widget_layout = QFormLayout(widget)
        widget_layout.setHorizontalSpacing(14)
        widget_layout.setVerticalSpacing(10)

        # Ground Level
        self.ground_level = QLineEdit()
        self.ground_level.setText("0.000")
        self.ground_level.setValidator(QDoubleValidator(0.0, 1e9, 2, self))
        self.ground_level_unit = QLabel("?")
        widget_layout.addRow(*self._row("Ground Level", self.ground_level, self.ground_level_unit))

        # Pier/Member Radius
        self.pier_proximity_radius = QLineEdit()
        self.pier_proximity_radius.setText("10.0")
        self.pier_proximity_radius.setValidator(QDoubleValidator(0.0, 1e9, 2, self))
        self.pier_proximity_radius_unit = QLabel("?")
        widget_layout.addRow(*self._row("Pier Proximity Radius", self.pier_proximity_radius, self.pier_proximity_radius_unit))

        # --- Structural Group Naming Rules ---
        outer = QGroupBox("Structural Group Naming Rules")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(8)

        # Create widgets used below (these were missing)
        self.deck_name = QLineEdit("Deck")
        self.pier_base_name = QLineEdit("Pier")
        self.starting_index = QSpinBox()
        self.starting_index.setRange(0, 10000)
        self.starting_index.setValue(1)
        self.suffix_above = QLineEdit("_SubAbove")
        self.suffix_below = QLineEdit("_SubBelow")

        # Inner box 1: Superstructure — Deck
        gb_super = QGroupBox("Superstructure — Deck")
        super_form = QFormLayout(gb_super)
        super_form.addRow("Deck Name", self.deck_name)

        # Inner box 2: Substructure — Piers
        gb_sub = QGroupBox("Substructure — Piers")
        sub_form = QFormLayout(gb_sub)
        sub_form.addRow("Base Name", self.pier_base_name)
        sub_form.addRow("Starting Index", self.starting_index)
        sub_form.addRow("Above the Deck", self.suffix_above)
        sub_form.addRow("Below the Deck", self.suffix_below)

        # Nest them into the outer box
        outer_layout.addWidget(gb_super)
        outer_layout.addWidget(gb_sub)

        # Add the outer box to the page
        widget_layout.addRow(outer)

        # Collect all LENGTH unit labels so UnitAwareMixin can update them together
        self.length_unit_labels = [
            self.ground_level_unit,
            self.pier_proximity_radius_unit,
        ]
        # No FORCE units on this page (yet)
        self.force_unit_labels = []

        return widget



    def _build_loads_page(self) -> QWidget:
        """
        Loads page
        (doesn't need unit labels here unless you show force-based values).
        """
        w = QWidget()
        form = QFormLayout(w)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.gust_factor = QDoubleSpinBox(decimals=2, minimum=0.5, maximum=3.0, singleStep=0.05)
        self.gust_factor.setValue(1.00)
        form.addRow("Gust Factor", self.gust_factor)

        self.drag_coeff = QDoubleSpinBox(decimals=2, minimum=0.1, maximum=5.0, singleStep=0.05)
        self.drag_coeff.setValue(1.20)
        form.addRow("Drag Coefficient", self.drag_coeff)

        # Example of a force-based field (optional; uncomment if you need it)
        # self.wind_pressure = QDoubleSpinBox(decimals=2, minimum=0.0, maximum=1e9)
        # self.wind_pressure.setValue(0.00)
        # self.wind_pressure_unit = QLabel("?")
        # form.addRow(*self._row("Wind Pressure", self.wind_pressure, self.wind_pressure_unit))
        #
        # If you use the above, remember to add:
        # self.force_unit_labels.append(self.wind_pressure_unit)

        return w

    def _build_units_page(self) -> QWidget:
        """
        Units info page (read-only summary reflecting current selection).
        You can expand this to allow local overrides if ever needed.
        """
        w = QWidget()
        form = QFormLayout(w)

        self.lbl_active_length = QLabel("—")
        self.lbl_active_force = QLabel("—")
        form.addRow("Active Length Unit", self.lbl_active_length)
        form.addRow("Active Force Unit", self.lbl_active_force)

        # Keep these labels synced too (optional)
        # Use mixin lists for consistency
        # NOTE: These labels show text like "m", "ft", "kN", etc.
        # They are not next to editors, but we still want live updates
        if not hasattr(self, "length_unit_labels"):
            self.length_unit_labels = []
        if not hasattr(self, "force_unit_labels"):
            self.force_unit_labels = []
        self.length_unit_labels.append(self.lbl_active_length)
        self.force_unit_labels.append(self.lbl_active_force)

        return w

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _row(self, label_text: str, editor: QWidget, unit_label: QLabel) -> tuple[QLabel, QWidget]:
        """
        Returns a (label, widget) pair suitable for QFormLayout.addRow(...)
        The widget is a small horizontal layout: editor | unit_label
        """
        lab = QLabel(label_text)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(editor, 1)
        h.addWidget(unit_label)
        return lab, row

    # ---------------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------------
    def collect_payload(self) -> dict:
        return {
            "structural": {
                "reference_height": float(self.ground_level.text()),
                "pier_radius": float(self.pier_proximity_radius.text()),
            },
            "naming": {
                "deck_name": self.deck_name.text().strip(),
                "pier_base_name": self.pier_base_name.text().strip(),
                "starting_index": int(self.starting_index.value()),
                "suffix_above": self.suffix_above.text().strip(),
                "suffix_below": self.suffix_below.text().strip(),
            },
            "loads": {
                "gust_factor": float(self.gust_factor.value()),
                "drag_coefficient": float(self.drag_coeff.value()),
            },
            "units": {
                "length": self.length_unit_labels[0].text() if self.length_unit_labels else "",
                "force": self.force_unit_labels[0].text() if self.force_unit_labels else "",
            },
        }



    def validate(self) -> tuple[bool, str]:
        try:
            gl = float(self.ground_level.text())
            pr = float(self.pier_proximity_radius.text())
        except ValueError:
            return False, "Ground Level and Pier Proximity Radius must be numbers."

        if gl < 0:
            return False, "Ground Level must be ≥ 0."
        if pr < 0:
            return False, "Pier Proximity Radius must be ≥ 0."

        if not (0.5 <= self.gust_factor.value() <= 3.0):
            return False, "Gust Factor must be between 0.5 and 3.0."

        if not self.deck_name.text().strip():
            return False, "Deck Name cannot be empty."
        if not self.pier_base_name.text().strip():
            return False, "Base Name cannot be empty."

        return True, ""


    def apply_changes(self):
        ok, msg = self.validate()
        if not ok:
            # Replace with a nicer banner/dialog as you prefer
            print("Validation error:", msg)
            return
        payload = self.collect_payload()
        # TODO: Persist to your project/session store if needed
        self.controlDataChanged.emit(payload)


    def restore_defaults(self):
        self.ground_level.setText("0.0")
        self.pier_proximity_radius.setText("10.0")
        self.gust_factor.setValue(1.00)
        self.drag_coeff.setValue(1.20)

        # naming
        self.deck_name.setText("Deck")
        self.pier_base_name.setText("Pier")
        self.starting_index.setValue(1)
        self.suffix_above.setText("_SubAbove")
        self.suffix_below.setText("_SubBelow")


    # ---------------------------------------------------------------------
    # UnitAwareMixin override (optional)
    # ---------------------------------------------------------------------
    def update_units(self, force_unit: str, length_unit: str) -> None:
        """
        Called by UnitAwareMixin when MainWindow units change.
        Default behavior (super) updates label *texts*. Keep that, then
        optionally adjust any read-only mirrors.
        """
        super().update_units(force_unit, length_unit)
        # keep summary page mirrors consistent (already handled via lists, but harmless)
        if hasattr(self, "lbl_active_length"):
            self.lbl_active_length.setText(length_unit)
        if hasattr(self, "lbl_active_force"):
            self.lbl_active_force.setText(force_unit)
