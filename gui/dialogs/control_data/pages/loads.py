# gui/dialogs/control_data/pages/loads.py

from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QDoubleSpinBox,
    QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy
)

from .base import ControlDataPage
from ..models import ControlDataModel, LoadSettings, SkewCoefficients


class LoadsPage(QWidget, ControlDataPage):
    title = "Loads"

    def __init__(self, parent=None):
        super().__init__(parent)

        # ---- Root layout (match Structural page) ----
        form = QFormLayout(self)
        # form.setContentsMargins(0, 0, 0, 0)
        # form.setSpacing(8)
        # Keep fields at their size hint instead of stretching vertically
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        # --- Scalars (gust/drag) ---
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

        # --- Skew coefficients group (single row like Structural page boxes) ---
        grp = QGroupBox("Skew Coefficients", self)
        gl = QVBoxLayout(grp)
        gl.setContentsMargins(9, 9, 9, 9)  # default groupbox margins

        self.tbl = QTableWidget(len(SkewCoefficients.ANGLES), 3, self)
        self.tbl.setHorizontalHeaderLabels(["Skew Angle (deg)", "Transverse", "Longitudinal"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setWordWrap(False)

        # Sizing: first column stretches; coefficients size to contents
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        # Populate rows
        for r, ang in enumerate(SkewCoefficients.ANGLES):
            it_ang = QTableWidgetItem(str(ang))
            it_ang.setFlags(it_ang.flags() & ~Qt.ItemFlag.ItemIsEditable)  # read-only angle
            self.tbl.setItem(r, 0, it_ang)
            self.tbl.setItem(r, 1, QTableWidgetItem("1.000"))
            self.tbl.setItem(r, 2, QTableWidgetItem("0.000"))

        # Fit to contents then lock vertical size so the group hugs the table
        self._fit_table_height()

        gl.addWidget(self.tbl)
        form.addRow(grp)

    # ---- ControlDataPage API ----
    def get_length_labels(self): return []
    def get_force_labels(self):  return []

    def set_state_from_model(self, model: ControlDataModel) -> None:
        l = model.loads
        self.spin_gust.setValue(l.gust_factor)
        self.spin_drag.setValue(l.drag_coefficient)

        N = len(SkewCoefficients.ANGLES)
        for r in range(N):
            self.tbl.item(r, 1).setText(f"{l.skew.transverse[r]:.3f}")
            self.tbl.item(r, 2).setText(f"{l.skew.longitudinal[r]:.3f}")

        # Recompute in case font/metrics or values changed row heights
        self._fit_table_height()

    def apply_to_model(self, model: ControlDataModel) -> None:
        N = len(SkewCoefficients.ANGLES)
        trans, longi = [], []
        for r in range(N):
            trans.append(float(self.tbl.item(r, 1).text()))
            longi.append(float(self.tbl.item(r, 2).text()))
        model.loads = LoadSettings(
            gust_factor=self.spin_gust.value(),
            drag_coefficient=self.spin_drag.value(),
            skew=SkewCoefficients(transverse=trans, longitudinal=longi),
        )

    def validate(self) -> tuple[bool, str]:
        N = len(SkewCoefficients.ANGLES)
        if self.tbl.rowCount() != N:
            return False, f"Skew table must have exactly {N} rows."
        for r in range(N):
            for c in (1, 2):
                it = self.tbl.item(r, c)
                if it is None or (it.text() or "").strip() == "":
                    return False, "Please fill all skew coefficients."
                try:
                    float(it.text())
                except ValueError:
                    return False, "Skew coefficients must be numbers."
        return True, ""

    def on_units_changed(self, units, prev_len: str, new_len: str, prev_force: str, new_force: str) -> None:
        pass  # coefficients are dimensionless

    # ---- Helpers ----
    def _fit_table_height(self) -> None:
        """Resize rows to contents and clamp table height so it doesn't expand."""
        self.tbl.resizeColumnsToContents()
        self.tbl.resizeRowsToContents()

        header_h = self.tbl.horizontalHeader().height()
        rows_h = self.tbl.verticalHeader().length()  # total height of all rows
        frame = 2 * self.tbl.frameWidth()

        # Include horizontal scrollbar height only if it will appear
        hbar_h = self.tbl.horizontalScrollBar().sizeHint().height() if self.tbl.horizontalScrollBar().isVisible() else 0

        needed = int(header_h + rows_h + frame + hbar_h + 1)  # +1 for rounding safety

        self.tbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.tbl.setMinimumHeight(needed)
        self.tbl.setMaximumHeight(needed)
