from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QComboBox, QPushButton, QTableView, QHeaderView,
    QMessageBox,
)

from wind_database import wind_db


@dataclass
class PierFrameDef:
    pier_group: str
    cap_group: Optional[str] = None
    above_group: Optional[str] = None


class PierFrameConfigDialog(QDialog):
    pierFramesChanged = Signal(list)   # list[PierFrameDef]

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.setWindowTitle("Pier Frame Configuration")
        self.resize(900, 500)

        # local copy to edit (pulled from wind_db only)
        self.frames: List[PierFrameDef] = list(
            getattr(wind_db, "pier_frames", []) or []
        )

        self._build_ui()
        self._populate_from_db()
        self._refresh_table()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        root = QVBoxLayout(self)

        gb = QGroupBox("Pier Frame Definition")
        form = QFormLayout(gb)

        # Pier group = reference axes
        self.pier_group_cb = QComboBox()
        self.cap_group_cb   = QComboBox()
        self.above_group_cb = QComboBox()

        form.addRow("Pier Group (axes):", self.pier_group_cb)
        form.addRow("Pier Cap Group:", self.cap_group_cb)
        form.addRow("Above-Deck Group:", self.above_group_cb)

        root.addWidget(gb)

        # table (3 cols now)
        self.table_model = QStandardItemModel(0, 3)
        self.table_model.setHorizontalHeaderLabels(
            ["Pier Group", "Pier Cap", "Above-Deck"]
        )
        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.clicked.connect(self._on_table_clicked)
        root.addWidget(self.table)

        # buttons
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add / Replace")
        self.btn_delete = QPushButton("Delete")
        self.btn_close = QPushButton("OK")

        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_close)
        root.addLayout(btn_row)

        self.btn_add.clicked.connect(self._on_add_or_replace)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_close.clicked.connect(self._on_ok)

    # ------------------------------------------------------------------ data

    def _populate_from_db(self):
        """
        Fill the combo boxes from wind_db.structural_groups and existing frames.
        """
        groups = getattr(wind_db, "structural_groups", {}) or {}

        pier_groups: List[str] = []
        cap_groups: List[str] = []
        above_groups: List[str] = []

        if isinstance(groups, dict):
            for name, params in groups.items():
                mt = str(params.get("Member Type", "")).strip()
                if mt == "Pier":
                    pier_groups.append(name)
                elif mt == "Pier Cap":
                    cap_groups.append(name)
                elif mt == "Substructure – Above Deck":
                    above_groups.append(name)

        # also include pier groups from existing frames (in case group was renamed / missing)
        for pf in self.frames:
            if pf.pier_group and pf.pier_group not in pier_groups:
                pier_groups.append(pf.pier_group)

        def _fill(cb: QComboBox, items):
            cb.clear()
            cb.addItems(sorted(items) or [""])

        _fill(self.pier_group_cb, pier_groups or ["Pier_1"])
        _fill(self.cap_group_cb, cap_groups or [""])
        _fill(self.above_group_cb, above_groups or [""])

    def _refresh_table(self):
        self.table_model.setRowCount(0)
        for pf in self.frames:
            row = [
                pf.pier_group,
                pf.cap_group or "",
                pf.above_group or "",
            ]
            self.table_model.appendRow([QStandardItem(x) for x in row])

    # ------------------------------------------------------------------ interaction

    def _on_table_clicked(self, idx):
        if not idx.isValid():
            return
        r = idx.row()
        pf = self.frames[r]
        self.pier_group_cb.setCurrentText(pf.pier_group)
        self.cap_group_cb.setCurrentText(pf.cap_group or "")
        self.above_group_cb.setCurrentText(pf.above_group or "")

    def _on_add_or_replace(self):
        pier_group = self.pier_group_cb.currentText().strip()
        cap = self.cap_group_cb.currentText().strip() or None
        above = self.above_group_cb.currentText().strip() or None

        if not pier_group:
            QMessageBox.warning(self, "Invalid Input", "Pier group cannot be empty.")
            return

        # Upsert by pier_group
        for i, pf in enumerate(self.frames):
            if pf.pier_group == pier_group:
                self.frames[i] = PierFrameDef(pier_group, cap, above)
                break
        else:
            self.frames.append(PierFrameDef(pier_group, cap, above))

        self._refresh_table()

    def _on_delete(self):
        idx = self.table.currentIndex()
        if not idx.isValid():
            QMessageBox.information(self, "Select Row", "Select a pier frame to delete.")
            return
        pier = self.table_model.item(idx.row(), 0).text()
        self.frames = [pf for pf in self.frames if pf.pier_group != pier]
        self._refresh_table()

    def _on_ok(self):
        # stash in wind_db for now (non-persistent until we wire ControlData)
        setattr(wind_db, "pier_frames", self.frames)
        self.pierFramesChanged.emit(self.frames)
        self.accept()
