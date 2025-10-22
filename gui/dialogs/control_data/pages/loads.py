# gui/dialogs/control_data/pages/loads.py

from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QDoubleSpinBox, QLineEdit, QLabel, QHBoxLayout,
    QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy
)
from PySide6.QtGui import QDoubleValidator

from .base import ControlDataPage
from ..models import ControlDataModel, LoadSettings, SkewCoefficients


class LoadsPage(QWidget, ControlDataPage):
    title = "Loads"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._length_labels: list[QLabel] = []

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

        # --- Crash Barrier Depth (length with unit label) ---
        self.txt_barrier = QLineEdit("0.0")
        self.txt_barrier.setValidator(QDoubleValidator(0, 1e12, 6, self))
        self.lbl_barrier_unit = QLabel("?")
        form.addRow(*self._row("Crash Barrier Depth", self.txt_barrier, self.lbl_barrier_unit))
        self._length_labels.append(self.lbl_barrier_unit)


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
    def get_length_labels(self):
        return self._length_labels
    
    def get_force_labels(self):  return []

    def set_state_from_model(self, model: ControlDataModel) -> None:
        l = model.loads
        self.spin_gust.setValue(l.gust_factor)
        self.spin_drag.setValue(l.drag_coefficient)
        self.txt_barrier.setText(f"{l.crash_barrier_depth:g}")

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
            crash_barrier_depth=float(self.txt_barrier.text() or 0.0),
            skew=SkewCoefficients(transverse=trans, longitudinal=longi),
        )


    def validate(self) -> tuple[bool, str]:
        # barrier depth must be numeric (can be zero or negative if needed)
        try:
            float(self.txt_barrier.text())
        except ValueError:
            return False, "Crash Barrier Depth must be numeric."

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
        # Convert the barrier depth when length unit changes, and update label
        if prev_len != new_len:
            self._convert_lineedit_length(self.txt_barrier, units, prev_len, new_len)
        for lab in self._length_labels:
            lab.setText(new_len)

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

    def _row(self, label_text, editor, unit_label):
        lab = QLabel(label_text)
        row = QWidget()
        h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(8)
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