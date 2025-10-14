# gui/dialogs/wind_load_input.py
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QDoubleValidator, QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableView, QLineEdit, QComboBox, QGroupBox, QFormLayout,
    QMessageBox, QWidget, QHeaderView
)

from unit_manager import UnitAwareMixin, UnitSystem
from wind_database import wind_db

log = logging.getLogger(__name__)


# --------------------------- Data Models ---------------------------

@dataclass
class WindGroup:
    name: str
    wind_speed: float
    exposure_category: str
    structure_height: float
    gust_factor: float
    drag_coefficient: float
    member_type: str

    def validate(self) -> tuple[bool, str]:
        if not self.name.strip():
            return False, "Group name cannot be empty."
        if self.wind_speed <= 0:
            return False, "Wind speed must be positive."
        if self.structure_height <= 0:
            return False, "Structure height must be positive."
        if not (0.1 <= self.drag_coefficient <= 5.0):
            return False, "Drag coefficient must be between 0.1 and 5.0."
        return True, ""


@dataclass
class WindLoadInputModel:
    groups: Dict[str, WindGroup] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: asdict(v) for k, v in self.groups.items()}


# --------------------------- Dialog ---------------------------

class WindLoadInput(QDialog, UnitAwareMixin):
    dataChanged = Signal(WindLoadInputModel)

    def __init__(self, parent: Optional[QObject] = None, *, units: Optional[UnitSystem] = None):
        super().__init__(parent)
        self.setWindowTitle("Wind Load Input")
        self.resize(950, 600)
        self.units = units or getattr(parent, "units", UnitSystem())

        self.model = WindLoadInputModel()
        self._setup_ui()
        self.bind_units(self.units)
        self._populate_from_db()

    # ---------------- UI ----------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        group_box = QGroupBox("Structural Group Parameters")
        form = QFormLayout(group_box)

        self.group_name_input = QComboBox()
        self._refresh_group_names()

        self.wind_speed = QLineEdit("150")
        self.wind_speed.setValidator(QDoubleValidator(0.0, 400.0, 2, self))

        self.exposure = QComboBox()
        self.exposure.addItems(["B", "C", "D"])
        self.exposure.setCurrentText("B")

        self.ref_height = QLineEdit("40")
        self.ref_height.setValidator(QDoubleValidator(0.0, 10000.0, 2, self))

        self.gust_factor = QComboBox()
        self.gust_factor.addItems(["0.85", "1.00"])
        self.gust_factor.setCurrentText("0.85")

        self.drag_coeff = QLineEdit("1.3")
        self.drag_coeff.setValidator(QDoubleValidator(0.0, 5.0, 2, self))

        self.member_type = QComboBox()
        self.member_type.addItems(["Girders", "Trusses, Columns, and Arches"])

        form.addRow("Group Name:", self.group_name_input)
        form.addRow("Wind Speed (mph):", self.wind_speed)
        form.addRow("Exposure Category:", self.exposure)
        form.addRow("Structure Height (ft):", self.ref_height)
        form.addRow("Gust Factor (G):", self.gust_factor)
        form.addRow("Drag Coefficient (Cd):", self.drag_coeff)
        form.addRow("Member Type:", self.member_type)

        layout.addWidget(group_box)

        # Table
        self.table_model = QStandardItemModel(0, 7)
        self.table_model.setHorizontalHeaderLabels(
            ["Group", "Wind Speed", "Exposure", "Height", "G", "Cd", "Member Type"]
        )
        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.clicked.connect(self._on_table_clicked)
        layout.addWidget(self.table)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_add_replace = QPushButton("Add / Replace")
        self.btn_delete = QPushButton("Delete")
        self.btn_finalize = QPushButton("Finalize & Compute")
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_add_replace)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_finalize)
        layout.addLayout(btn_row)

        # Signals
        self.btn_refresh.clicked.connect(self._refresh_group_names)
        self.btn_add_replace.clicked.connect(self._on_add_or_replace)
        self.btn_delete.clicked.connect(self._on_delete_selected)
        self.btn_finalize.clicked.connect(self._finalize)

    # ---------------- Data/Events ----------------

    def _refresh_group_names(self):
        """Fetch group names: try Midas, fallback to wind_db."""
        try:
            from main import MidasAPI
            result = MidasAPI("GET", "/db/GRUP")
            names = [v["NAME"] for v in result.get("GRUP", {}).values() if isinstance(v, dict) and "NAME" in v]
        except Exception:
            names = list((wind_db.structural_groups or {}).keys())
        self.group_name_input.clear()
        self.group_name_input.addItems(names or ["Default Group"])
        log.info("WindLoadInput: refreshed group names (%d)", len(names))

    def _populate_from_db(self):
        self.model.groups.clear()
        for name, params in (wind_db.structural_groups or {}).items():
            g = WindGroup(
                name=name,
                wind_speed=float(params.get("Wind Speed", 0.0)),
                exposure_category=str(params.get("Exposure Category", "C")),
                structure_height=float(params.get("Structure Height", 0.0)),
                gust_factor=float(params.get("Gust Factor", 1.0)),
                drag_coefficient=float(params.get("Drag Coefficient", 1.0)),
                member_type=str(params.get("Member Type", "Girders")),
            )
            self.model.groups[name] = g
        self._refresh_table()

    def _refresh_table(self):
        self.table_model.setRowCount(0)
        for g in self.model.groups.values():
            row = [
                g.name,
                f"{g.wind_speed:.2f}",
                g.exposure_category,
                f"{g.structure_height:.2f}",
                f"{g.gust_factor:.2f}",
                f"{g.drag_coefficient:.2f}",
                g.member_type,
            ]
            self.table_model.appendRow([QStandardItem(x) for x in row])

    def _on_table_clicked(self, index):
        if not index.isValid():
            return
        name = self.table_model.item(index.row(), 0).text()
        grp = self.model.groups.get(name)
        if grp:
            self._load_into_form(grp)

    def _load_into_form(self, g: WindGroup):
        self.group_name_input.setCurrentText(g.name)
        self.wind_speed.setText(str(g.wind_speed))
        self.exposure.setCurrentText(g.exposure_category)
        self.ref_height.setText(str(g.structure_height))
        self.gust_factor.setCurrentText(str(g.gust_factor))
        self.drag_coeff.setText(str(g.drag_coefficient))
        self.member_type.setCurrentText(g.member_type)

    # ---------------- Buttons ----------------

    def _on_add_or_replace(self):
        try:
            g = WindGroup(
                name=self.group_name_input.currentText().strip(),
                wind_speed=float(self.wind_speed.text()),
                exposure_category=self.exposure.currentText(),
                structure_height=float(self.ref_height.text()),
                gust_factor=float(self.gust_factor.currentText()),
                drag_coefficient=float(self.drag_coeff.text()),
                member_type=self.member_type.currentText(),
            )
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please provide valid numeric values.")
            return

        ok, msg = g.validate()
        if not ok:
            QMessageBox.warning(self, "Validation Error", msg)
            return

        self.model.groups[g.name] = g
        self._refresh_table()
        log.info("WindLoadInput: added/updated group '%s'", g.name)

    def _on_delete_selected(self):
        idx = self.table.currentIndex()
        if not idx.isValid():
            QMessageBox.information(self, "Select Row", "Please select a group to delete.")
            return
        name = self.table_model.item(idx.row(), 0).text()
        if name in self.model.groups:
            del self.model.groups[name]
            self._refresh_table()
            log.info("WindLoadInput: deleted group '%s'", name)

    def _finalize(self):
        if not self.model.groups:
            QMessageBox.warning(self, "No Groups", "Define at least one group before computing.")
            return
        try:
            for g in self.model.groups.values():
                wind_db.add_structural_group(g.name, self._to_legacy_params(g))

            wind_db.update_wind_pressures()
            self.dataChanged.emit(self.model)
            QMessageBox.information(self, "Success", "Wind data computed successfully.")
            self.accept()
        except Exception as e:
            log.exception("WindLoadInput: finalize failed: %s", e)
            QMessageBox.critical(self, "Error", str(e))

    def _to_legacy_params(self, g: WindGroup) -> dict:
        return {
            "Wind Speed": g.wind_speed,
            "Exposure Category": g.exposure_category,
            "Structure Height": g.structure_height,
            "Gust Factor": g.gust_factor,
            "Drag Coefficient": g.drag_coefficient,
            "Member Type": g.member_type,
        }
