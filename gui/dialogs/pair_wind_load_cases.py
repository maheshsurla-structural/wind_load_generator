# gui/dialogs/pair_wind_load_cases.py
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import List, Dict

import pandas as pd
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, QEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QSpinBox,
    QPushButton, QTableView, QGroupBox, QMessageBox, QHeaderView
)
from PySide6.QtGui import QGuiApplication, QFont

from wind_database import wind_db, LOAD_CASES

log = logging.getLogger(__name__)


# --------------------------- Data Models ---------------------------

@dataclass
class LoadCaseAssignment:
    case: str
    angle: int
    value: str


@dataclass
class PairWindLoadModel:
    ws_cases: List[LoadCaseAssignment] = field(default_factory=list)
    wl_cases: List[LoadCaseAssignment] = field(default_factory=list)

    def to_frames(self) -> Dict[str, pd.DataFrame]:
        df_ws = pd.DataFrame([asdict(a) for a in self.ws_cases])
        df_wl = pd.DataFrame([asdict(a) for a in self.wl_cases])
        return {"WS Cases": df_ws, "WL Cases": df_wl}


# --------------------------- Table Model ---------------------------

class WindLoadTableModel(QAbstractTableModel):
    def __init__(self, load_cases: List[str], num_angles: int, title: str):
        super().__init__()
        self.load_cases = load_cases
        self.num_angles = num_angles
        self.title = title
        self._data = [["" for _ in range(num_angles)] for _ in load_cases]

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.load_cases)

    def columnCount(self, parent=QModelIndex()) -> int:
        return self.num_angles + 1  # first column is case label

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if role == Qt.DisplayRole:
            if c == 0:
                return self.load_cases[r]
            return self._data[r][c - 1]
        return None

    def setData(self, index: QModelIndex, value, role=Qt.EditRole):
        if not index.isValid() or index.column() == 0:
            return False
        r, c = index.row(), index.column() - 1
        self._data[r][c] = str(value)
        self.dataChanged.emit(index, index, [Qt.DisplayRole])
        return True

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        if index.column() == 0:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return "Load Case" if section == 0 else f"Angle {section}"
        return None

    def to_assignments(self, angles: List[int]) -> List[LoadCaseAssignment]:
        recs: List[LoadCaseAssignment] = []
        for r, case in enumerate(self.load_cases):
            for c, angle in enumerate(angles):
                if c < len(self._data[r]):
                    val = (self._data[r][c] or "").strip()
                    if val:
                        recs.append(LoadCaseAssignment(case=case, angle=angle, value=val))
        return recs


# --------------------------- Dialog ---------------------------

class PairWindLoadCases(QDialog):
    dataChanged = Signal(PairWindLoadModel)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pair Wind Load Cases")
        self.resize(940, 640)

        self.num_angles = 3
        self._build_ui()
        self._load_from_db()
        self.installEventFilter(self)

    # ---------------- UI ----------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Angle controls
        gb_angles = QGroupBox("Angle Configuration")
        lay = QHBoxLayout(gb_angles)
        lay.addWidget(QLabel("Number of Angles:"))
        self.spin_num = QSpinBox()
        self.spin_num.setRange(1, 5)
        self.spin_num.setValue(self.num_angles)
        self.spin_num.valueChanged.connect(self._on_num_angles_changed)
        lay.addWidget(self.spin_num)
        lay.addWidget(QLabel("Angles:"))

        self.combo_angles: List[QComboBox] = []
        defaults = ["0", "15", "30", "45", "60"]
        for i in range(5):
            cb = QComboBox()
            cb.addItems(defaults)
            cb.setCurrentIndex(i if i < len(defaults) else 0)
            cb.setEnabled(i < self.num_angles)
            self.combo_angles.append(cb)
            lay.addWidget(cb)

        root.addWidget(gb_angles)

        # Tables
        self.ws_model = WindLoadTableModel(LOAD_CASES, self.num_angles, "WS")
        self.wl_model = WindLoadTableModel(LOAD_CASES, self.num_angles, "WL")
        self.ws_group = self._make_table_group("Wind on Structure (WS)", self.ws_model)
        self.wl_group = self._make_table_group("Wind on Live Load (WL)", self.wl_model)
        root.addWidget(self.ws_group)
        root.addWidget(self.wl_group)

        # Buttons
        btns = QHBoxLayout()
        self.btn_apply = QPushButton("Apply")
        self.btn_close = QPushButton("Close")
        btns.addStretch()
        btns.addWidget(self.btn_apply)
        btns.addWidget(self.btn_close)
        root.addLayout(btns)

        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_close.clicked.connect(self.close)

    def _make_table_group(self, title: str, model: QAbstractTableModel) -> QGroupBox:
        gb = QGroupBox(title)
        lay = QVBoxLayout(gb)
        view = QTableView()
        view.setModel(model)
        view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        view.verticalHeader().setVisible(False)
        view.setFont(QFont("Arial", 10))
        lay.addWidget(view)
        return gb

    # ---------------- Events ----------------

    def _on_num_angles_changed(self, n: int):
        for i, cb in enumerate(self.combo_angles):
            cb.setEnabled(i < n)
        self._rebuild_models(n)

    def _rebuild_models(self, n: int):
        self.ws_model = WindLoadTableModel(LOAD_CASES, n, "WS")
        self.wl_model = WindLoadTableModel(LOAD_CASES, n, "WL")
        # replace views inside groups
        for grp, model in ((self.ws_group, self.ws_model), (self.wl_group, self.wl_model)):
            lay = grp.layout()
            old = lay.itemAt(0).widget()
            lay.removeWidget(old)
            old.deleteLater()
            v = QTableView()
            v.setModel(model)
            v.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            v.verticalHeader().setVisible(False)
            lay.addWidget(v)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key.Key_C and (mods & Qt.KeyboardModifier.ControlModifier):
                self._copy_all_to_clipboard()
                return True
            if key == Qt.Key.Key_V and (mods & Qt.KeyboardModifier.ControlModifier):
                self._paste_into_ws()
                return True
        return super().eventFilter(source, event)

    # ---------------- Clipboard ----------------

    def _copy_all_to_clipboard(self):
        lines: List[str] = []
        for table in (self.ws_model, self.wl_model):
            for r in range(table.rowCount()):
                row = [table.data(table.index(r, c), Qt.DisplayRole) or "" for c in range(1, table.columnCount())]
                lines.append("\t".join(row))
        QGuiApplication.clipboard().setText("\n".join(lines))
        log.info("PairWindLoadCases: copied selection to clipboard")

    def _paste_into_ws(self):
        txt = QGuiApplication.clipboard().text()
        if not txt.strip():
            return
        rows = txt.splitlines()
        for r, line in enumerate(rows[: self.ws_model.rowCount()]):
            vals = line.split("\t")
            for c, val in enumerate(vals[: self.ws_model.columnCount() - 1]):
                self.ws_model.setData(self.ws_model.index(r, c + 1), val)

    # ---------------- Persistence ----------------

    def _active_angles(self) -> List[int]:
        n = self.spin_num.value()
        return [int(self.combo_angles[i].currentText()) for i in range(n)]

    def _on_apply(self):
        try:
            angles = self._active_angles()
            ws = self.ws_model.to_assignments(angles)
            wl = self.wl_model.to_assignments(angles)
            model = PairWindLoadModel(ws_cases=ws, wl_cases=wl)

            wind_db.ws_cases = pd.DataFrame([asdict(a) for a in ws])
            wind_db.wl_cases = pd.DataFrame([asdict(a) for a in wl])
            wind_db.update_wind_pressures()

            self.dataChanged.emit(model)
            QMessageBox.information(self, "Success", "Wind load pairs updated successfully.")
            self.accept()
        except Exception as e:
            log.exception("PairWindLoadCases: apply failed: %s", e)
            QMessageBox.critical(self, "Error", str(e))

    def _load_from_db(self):
        try:
            data = wind_db.get_data()
            self._load_df_into_model(data.get("WS Cases", pd.DataFrame()), self.ws_model)
            self._load_df_into_model(data.get("WL Cases", pd.DataFrame()), self.wl_model)
        except Exception as e:
            log.warning("PairWindLoadCases: no prior data: %s", e)

    def _load_df_into_model(self, df: pd.DataFrame, model: WindLoadTableModel):
        if df.empty:
            return
        angles = sorted({int(a) for a in df["Angle"].unique()})
        self.spin_num.setValue(len(angles))
        self._rebuild_models(len(angles))
        # after rebuild, model reference changed:
        target = self.ws_model if model.title == "WS" else self.wl_model
        # fill
        for _, row in df.iterrows():
            try:
                r = LOAD_CASES.index(row["Case"])
                c = angles.index(int(row["Angle"]))
                target._data[r][c] = str(row.get("Value", ""))
            except Exception:
                continue
