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
from ..models import ControlDataModel, LoadSettings, SkewCoefficients, WindLiveLoadCoefficients


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

        # --- Scalars (gust / drag) ---
        self.spin_gust = QDoubleSpinBox()
        self.spin_gust.setRange(0.5, 3.0)
        self.spin_gust.setSingleStep(0.05)
        self.spin_gust.setValue(1.00)

        self.spin_drag_super = QDoubleSpinBox()
        self.spin_drag_super.setRange(0.1, 5.0)
        self.spin_drag_super.setSingleStep(0.05)
        self.spin_drag_super.setValue(1.20)

        self.spin_drag_sub = QDoubleSpinBox()
        self.spin_drag_sub.setRange(0.1, 5.0)
        self.spin_drag_sub.setSingleStep(0.05)
        self.spin_drag_sub.setValue(1.20)

        form.addRow("Gust Factor", self.spin_gust)
        form.addRow("Superstructure Drag Coefficient", self.spin_drag_super)
        form.addRow("Substructure Drag Coefficient", self.spin_drag_sub)


        # --- Crash Barrier Depth (length with unit label) ---
        self.txt_barrier = QLineEdit("0.0")
        self.txt_barrier.setValidator(QDoubleValidator(0, 1e12, 6, self))
        self.lbl_barrier_unit = QLabel("?")
        form.addRow(*self._row("Crash Barrier Depth", self.txt_barrier, self.lbl_barrier_unit))
        self._length_labels.append(self.lbl_barrier_unit)


        # --- Skew coefficients group (single row like Structural page boxes) ---
        grp_skew = QGroupBox("Skew Coefficients", self)
        gl_skew = QVBoxLayout(grp_skew)
        gl_skew.setContentsMargins(9, 9, 9, 9)  # default groupbox margins

        self.tbl_skew = QTableWidget(len(SkewCoefficients.ANGLES), 3, self)
        self.tbl_skew.setHorizontalHeaderLabels(["Skew Angle (deg)", "Transverse", "Longitudinal"])
        self.tbl_skew.horizontalHeader().setStretchLastSection(True)
        self.tbl_skew.verticalHeader().setVisible(False)
        self.tbl_skew.setAlternatingRowColors(True)
        self.tbl_skew.setWordWrap(False)

        # Sizing: first column stretches; coefficients size to contents
        hh_skew = self.tbl_skew.horizontalHeader()
        hh_skew.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        hh_skew.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh_skew.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh_skew.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        # Populate rows
        for r, ang in enumerate(SkewCoefficients.ANGLES):
            it_ang = QTableWidgetItem(str(ang))
            it_ang.setFlags(it_ang.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_ang.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_skew.setItem(r, 0, it_ang)

            it_t = QTableWidgetItem("1.000")
            it_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_skew.setItem(r, 1, it_t)

            it_l = QTableWidgetItem("0.000")
            it_l.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_skew.setItem(r, 2, it_l)


        # Fit to contents then lock vertical size so the group hugs the table
        self._fit_table_height(self.tbl_skew)

        gl_skew.addWidget(self.tbl_skew)
        form.addRow(grp_skew)


        grp_live = QGroupBox("Wind Load Components on Live Load", self)
        gl_live = QVBoxLayout(grp_live)
        gl_live.setContentsMargins(9, 9, 9, 9)  # default groupbox margins
        
        self.tbl_live = QTableWidget(len(WindLiveLoadCoefficients.ANGLES), 3, self)
        self.tbl_live.setHorizontalHeaderLabels(["Skew Angle (deg)", "Transverse (klf)", "Longitudinal (klf)"])
        self.tbl_live.horizontalHeader().setStretchLastSection(True)
        self.tbl_live.verticalHeader().setVisible(False)
        self.tbl_live.setAlternatingRowColors(True)
        self.tbl_live.setWordWrap(False)


        # Sizing: first column stretches; coefficients size to contents
        hh_live = self.tbl_live.horizontalHeader()
        hh_live.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        hh_live.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh_live.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh_live.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        # Populate rows
        defaults_live = WindLiveLoadCoefficients()
        for r, ang in enumerate(WindLiveLoadCoefficients.ANGLES):
            it_ang = QTableWidgetItem(str(ang))
            it_ang.setFlags(it_ang.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_ang.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_live.setItem(r, 0, it_ang)

            it_t = QTableWidgetItem(f"{defaults_live.transverse[r]:.3f}")
            it_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_live.setItem(r, 1, it_t)

            it_l = QTableWidgetItem(f"{defaults_live.longitudinal[r]:.3f}")
            it_l.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_live.setItem(r, 2, it_l)


        self._fit_table_height(self.tbl_live)
        gl_live.addWidget(self.tbl_live)
        form.addRow(grp_live)



    # ---- ControlDataPage API ----
    def get_length_labels(self):
        return self._length_labels
    
    def get_force_labels(self):  return []

    def set_state_from_model(self, model: ControlDataModel) -> None:
        l = model.loads
        self.spin_gust.setValue(l.gust_factor)
        self.spin_drag_super.setValue(l.superstructure_drag_coefficient)
        self.spin_drag_sub.setValue(l.substructure_drag_coefficient)
        self.txt_barrier.setText(f"{l.crash_barrier_depth:g}")

        # skew
        N = len(SkewCoefficients.ANGLES)
        for r in range(N):
            self.tbl_skew.item(r, 1).setText(f"{l.skew.transverse[r]:.3f}")
            self.tbl_skew.item(r, 2).setText(f"{l.skew.longitudinal[r]:.3f}")
        self._fit_table_height(self.tbl_skew)

        # wind-on-live
        M = len(WindLiveLoadCoefficients.ANGLES)
        for r in range(M):
            self.tbl_live.item(r, 1).setText(f"{l.wind_live.transverse[r]:.3f}")
            self.tbl_live.item(r, 2).setText(f"{l.wind_live.longitudinal[r]:.3f}")
        self._fit_table_height(self.tbl_live)


    def apply_to_model(self, model: ControlDataModel) -> None:
        # skew
        N = len(SkewCoefficients.ANGLES)
        trans_skew, longi_skew = [], []
        for r in range(N):
            trans_skew.append(float(self.tbl_skew.item(r, 1).text()))
            longi_skew.append(float(self.tbl_skew.item(r, 2).text()))

        # wind-on-live
        M = len(WindLiveLoadCoefficients.ANGLES)
        trans_live, longi_live = [], []
        for r in range(M):
            trans_live.append(float(self.tbl_live.item(r, 1).text()))
            longi_live.append(float(self.tbl_live.item(r, 2).text()))

        model.loads = LoadSettings(
            gust_factor=self.spin_gust.value(),
            superstructure_drag_coefficient=self.spin_drag_super.value(),
            substructure_drag_coefficient=self.spin_drag_sub.value(),
            crash_barrier_depth=float(self.txt_barrier.text() or 0.0),
            skew=SkewCoefficients(transverse=trans_skew, longitudinal=longi_skew),
            wind_live=WindLiveLoadCoefficients(
                transverse=trans_live,
                longitudinal=longi_live,
            ),
        )




    def validate(self) -> tuple[bool, str]:
        # barrier
        try:
            float(self.txt_barrier.text())
        except ValueError:
            return False, "Crash Barrier Depth must be numeric."

        # skew
        N = len(SkewCoefficients.ANGLES)
        if self.tbl_skew.rowCount() != N:
            return False, f"Skew table must have exactly {N} rows."
        for r in range(N):
            for c in (1, 2):
                it = self.tbl_skew.item(r, c)
                if it is None or (it.text() or "").strip() == "":
                    return False, "Please fill all skew coefficients."
                try:
                    float(it.text())
                except ValueError:
                    return False, "Skew coefficients must be numbers."

        # wind-on-live
        M = len(WindLiveLoadCoefficients.ANGLES)
        if self.tbl_live.rowCount() != M:
            return False, f"Wind live table must have exactly {M} rows."
        for r in range(M):
            for c in (1, 2):
                it = self.tbl_live.item(r, c)
                if it is None or (it.text() or "").strip() == "":
                    return False, "Please fill all wind-live coefficients."
                try:
                    float(it.text())
                except ValueError:
                    return False, "Wind-live coefficients must be numbers."

        return True, ""


    def on_units_changed(self, units, prev_len: str, new_len: str, prev_force: str, new_force: str) -> None:
        # Convert the barrier depth when length unit changes, and update label
        if prev_len != new_len:
            self._convert_lineedit_length(self.txt_barrier, units, prev_len, new_len)
        for lab in self._length_labels:
            lab.setText(new_len)

    # ---- Helpers ----
    def _fit_table_height(self, tbl: QTableWidget) -> None:
        tbl.resizeColumnsToContents()
        tbl.resizeRowsToContents()

        header_h = tbl.horizontalHeader().height()
        rows_h = tbl.verticalHeader().length()
        frame = 2 * tbl.frameWidth()
        hbar_h = tbl.horizontalScrollBar().sizeHint().height() if tbl.horizontalScrollBar().isVisible() else 0

        needed = int(header_h + rows_h + frame + hbar_h + 1)

        tbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        tbl.setMinimumHeight(needed)
        tbl.setMaximumHeight(needed)


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