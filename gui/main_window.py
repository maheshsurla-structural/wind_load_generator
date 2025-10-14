# gui/main_window.py
from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar, QWidget, QVBoxLayout,
    QHBoxLayout, QGroupBox, QPushButton, QComboBox, QLabel
)
from PySide6.QtGui import QAction

from unit_manager import get_unit_manager
from core.app_bus import get_app_bus
from core.worker import Worker
from core.thread_pool import run_in_thread
from services.persistence import ConfigManager
from wind_database import wind_db

from gui.widgets.wind_parameters import WindParameters
from gui.widgets.pressure_table import PressureTable

from gui.dialogs.control_data import ControlData

from gui.dialogs.wind_load_input import WindLoadInput
from gui.dialogs.pair_wind_load_cases import PairWindLoadCases


class MainWindow(QMainWindow):

    def __init__(self) -> None:

        super().__init__()
        
        self.setWindowTitle("Wind Load Generator AASHTO")

        # ---- Core systems ----
        self.units = get_unit_manager()
        self.bus = get_app_bus()
        self.config = ConfigManager()

        # ---- Central UI ----
        central_widget = QWidget()
        main_layout  = QVBoxLayout(central_widget)
        self.setCentralWidget(central_widget)

        # Wind parameters (imported from widgets/wind_parameters.py)
        self.wind_parameters = WindParameters(self)
        main_layout .addWidget(self.wind_parameters)

        # Structural actions
        actions_group = QGroupBox("Structural Group Classification & Wind Data")
        actions = QHBoxLayout(actions_group)
        self.btn_generate = QPushButton("Generate Wind Data")
        self.btn_edit     = QPushButton("Edit Wind Data")
        actions.addWidget(self.btn_generate)
        actions.addWidget(self.btn_edit)
        main_layout .addWidget(actions_group)

        # Pressure table (imported from widgets/pressure_table.py)
        self.pressure = PressureTable(self)
        main_layout .addWidget(self.pressure)

        # Wind load cases
        wlc_group = QGroupBox("Wind Load Cases")
        wlc_lay = QHBoxLayout(wlc_group)
        self.btn_pair = QPushButton("Pair Wind Load Cases")
        wlc_lay.addWidget(self.btn_pair)
        main_layout .addWidget(wlc_group)

        # Toolbar
        tb = QToolBar(movable=False)
        self.addToolBar(tb)
        act_control = QAction("Control Data", self)
        tb.addAction(act_control)

        # Status bar + unit selectors
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._setup_unit_selectors(sb)

        # ---- Connections ----
        act_control.triggered.connect(self.open_control_data)
        self.btn_edit.clicked.connect(self.open_wind_load_input)
        self.btn_pair.clicked.connect(self.open_pair_wind_load_cases)
        self.btn_generate.clicked.connect(self._on_generate_clicked)

        # Global events
        self.bus.progressStarted.connect(self._on_progress_started)
        self.bus.progressFinished.connect(self._on_progress_finished)
        self.bus.windGroupsUpdated.connect(self._on_wind_groups_updated)

        # ---- Restore persisted state ----
        self.control_data = self.config.load_control_data()
        self._restore_units_from_config()
        # populate initial pressure groups (if any)
        self.pressure.populate_groups()
        self.pressure.refresh()

    # ---------------- Event handlers ----------------

    def _on_generate_clicked(self) -> None:
        """Kick off classification + wind DB updates in background."""
        from core.analytical_model_classification import classify_elements
        from midas import create_structural_group  # your integration layer

        self.bus.progressStarted.emit("Generating wind data...")
        worker = Worker(self._run_classification_task, classify_elements, create_structural_group)
        worker.signals.finished.connect(lambda _: self.bus.progressFinished.emit(True, "Wind data generated."))
        worker.signals.error.connect(lambda e: self.bus.progressFinished.emit(False, e))
        run_in_thread(worker)

    def _run_classification_task(self, classify_elements, create_structural_group):
        """Runs off the UI thread."""
        defaults = self.wind_parameters.values()
        result = classify_elements()

        # Deck (optional; if present)
        deck_elements = result.get("deck_elements", {})
        if deck_elements:
            deck_ids = list(map(int, deck_elements.keys()))
            create_structural_group(deck_ids, "Deck Elements")
            wind_db.add_structural_group("Deck Elements", {
                **defaults, "Structure Height": "40", "Gust Factor": "0.85",
                "Drag Coefficient": "1.3", "Member Type": "Girders"
            })

        # Piers / clusters
        for label, element_dict in (result.get("pier_clusters", {}) or {}).items():
            ids = list(map(int, element_dict.keys()))
            create_structural_group(ids, label)
            wind_db.add_structural_group(label, {
                **defaults, "Structure Height": "40", "Gust Factor": "0.85",
                "Drag Coefficient": "1.3", "Member Type": "Trusses, Columns, and Arches"
            })

        # Compute pressures (still off-thread)
        wind_db.update_wind_pressures()
        # Notify UI to refresh
        self.bus.windGroupsUpdated.emit(wind_db.get_data())

    def _on_wind_groups_updated(self, _payload) -> None:
        """Refresh widgets that rely on wind_db data."""
        self.pressure.populate_groups()
        self.pressure.refresh()

    def _on_progress_started(self, msg: str) -> None:
        self.statusBar().showMessage(msg)

    def _on_progress_finished(self, ok: bool, msg: str) -> None:
        icon = "✅" if ok else "❌"
        self.statusBar().showMessage(f"{icon} {msg}", 4000)

    # ---------------- Dialogs ----------------

    def open_control_data(self) -> None:
        dlg = ControlData(self, units=self.units)
        dlg.set_payload(self.control_data)              # <- preload saved values
        dlg.controlDataChanged.connect(self._on_control_data_changed)
        dlg.exec()


    def open_wind_load_input(self) -> None:
        WindLoadInput(self).exec()

    def open_pair_wind_load_cases(self) -> None:
        PairWindLoadCases(self).exec()

    def _on_control_data_changed(self, model) -> None:
        print("controlDataChanged received")  # Debug confirmation
        self.control_data = model.to_dict()
        self.config.save_control_data(self.control_data)
        self.statusBar().showMessage("Control data saved.", 3000)


    # ---------------- Helpers ----------------

    def _setup_unit_selectors(self, sb: QStatusBar) -> None:
        """Hook unit selectors to the global UnitManager."""
        force_combo = QComboBox()
        force_combo.addItems(["KGF", "TONF", "N", "KN", "LBF", "KIPS"])
        length_combo = QComboBox()
        length_combo.addItems(["MM", "CM", "M", "IN", "FT"])

        length_combo.setCurrentText(self.units.length)
        force_combo.setCurrentText(self.units.force)
        length_combo.currentTextChanged.connect(self.units.set_length)
        force_combo.currentTextChanged.connect(self.units.set_force)

        sb.addPermanentWidget(QLabel("Force:"))
        sb.addPermanentWidget(force_combo)
        sb.addPermanentWidget(QLabel("Length:"))
        sb.addPermanentWidget(length_combo)

    def _restore_units_from_config(self) -> None:
        """Apply persisted units (if present) to the UnitManager."""
        units_cfg = self.control_data.get("units", {})
        if "length" in units_cfg:
            self.units.set_length(units_cfg["length"])
        if "force" in units_cfg:
            self.units.set_force(units_cfg["force"])
