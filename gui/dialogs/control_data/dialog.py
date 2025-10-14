# gui\dialogs\control_data_folder\dialog.py

from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QListWidget, QStackedWidget, QSplitter,
    QHBoxLayout, QVBoxLayout, QPushButton
)
from unit_manager import UnitAwareMixin, UnitSystem
from .models import ControlDataModel
from .pages.structural import StructuralPage
from .pages.loads import LoadsPage
from .pages.units import UnitsPage

class ControlData(QDialog, UnitAwareMixin):
    """Entry point dialog that stacks page widgets and aggregates their state."""
    controlDataChanged = Signal(object)

    def __init__(self, parent=None, *, units: Optional[UnitSystem] = None):
        super().__init__(parent)
        self.setWindowTitle("Control Data")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(820, 460)

        self.units = units or getattr(parent, "units", UnitSystem())
        self.model = ControlDataModel(length_unit=self.units.length, force_unit=self.units.force)

        # --- pages (each page = single file with all its logic) ---
        self._pages = [
            StructuralPage(self),
            LoadsPage(self),
            UnitsPage(self.units, self),
        ]

        self.section_list = QListWidget()
        self.section_list.addItems([p.title for p in self._pages])
        self.section_list.setFixedWidth(220)

        self.stack = QStackedWidget()
        for p in self._pages:
            self.stack.addWidget(p)

        splitter = QSplitter()
        splitter.addWidget(self.section_list)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)

        self.btn_defaults = QPushButton("Restore Defaults")
        self.btn_apply = QPushButton("Apply")
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancel")

        btns = QHBoxLayout()
        btns.addWidget(self.btn_defaults); btns.addStretch()
        btns.addWidget(self.btn_apply); btns.addWidget(self.btn_ok); btns.addWidget(self.btn_cancel)

        root = QVBoxLayout(self)
        root.addWidget(splitter); root.addLayout(btns)

        # wire events
        self.section_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.btn_defaults.clicked.connect(self._on_defaults)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_ok.clicked.connect(lambda: (self._on_apply(), self.accept()))
        self.btn_cancel.clicked.connect(self.reject)

        # unit binding
        self._prev_len = self.units.length
        self._prev_force = self.units.force
        self.bind_units(self.units)  # will call update_units at least once

        # default to first page
        self.section_list.setCurrentRow(0)

        # initialize from current model
        self._push_model_to_pages()

    # ---------- UnitAwareMixin hook ----------
    def update_units(self, length_unit: str, force_unit: str) -> None:
        for p in self._pages:
            p.on_units_changed(self.units, self._prev_len, length_unit, self._prev_force, force_unit)
        self._prev_len = length_unit
        self._prev_force = force_unit

    # ---------- payload API ----------
    def set_payload(self, payload: dict) -> None:
        try:
            self.model = ControlDataModel.from_dict(payload)
            self._push_model_to_pages()
            # convert structural numeric fields if payload length != current
            if self.model.length_unit != self.units.length:
                # simulate a unit change to trigger per-page conversion
                for p in self._pages:
                    p.on_units_changed(self.units, self.model.length_unit, self.units.length,
                                       self.model.force_unit, self.units.force)
            # keep model units aligned to global after load
            self.model.length_unit = self.units.length
            self.model.force_unit = self.units.force
        except Exception as e:
            # keep silent UI; you can log here if desired
            # log.exception("set_payload failed: %s", e)
            pass

    # ---------- buttons ----------
    def _on_defaults(self):
        self.model = ControlDataModel(length_unit=self.units.length, force_unit=self.units.force)
        self._push_model_to_pages()

    def _on_apply(self):
        # validate each page
        for p in self._pages:
            ok, msg = p.validate()
            if not ok:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Invalid Data", msg)
                return

        # collect into model
        for p in self._pages:
            p.apply_to_model(self.model)
        self.model.length_unit = self.units.length
        self.model.force_unit = self.units.force

        self.controlDataChanged.emit(self.model)

    # ---------- helpers ----------
    def _push_model_to_pages(self):
        for p in self._pages:
            p.set_state_from_model(self.model)
