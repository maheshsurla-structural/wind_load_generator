# gui/main_window.py
from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar, QWidget, QVBoxLayout,
    QHBoxLayout, QGroupBox, QPushButton, QComboBox, QLabel
)
from PySide6.QtGui import QAction

from unit_manager import get_unit_manager
from unit_manager.converter import convert_length

from core.app_bus import get_app_bus
from core.worker import Worker
from core.thread_pool import run_in_thread
from services.persistence import ConfigManager
from wind_database import wind_db

from gui.widgets.wind_parameters import WindParameters
from gui.widgets.pressure_table import PressureTable

from gui.dialogs.control_data.models import ControlDataModel
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
        payload = self.config.load_control_data()

        # First, restore app unit selectors from persisted units
        self._restore_units_from_config(payload)

        # Status bar + unit selectors
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._setup_unit_selectors(sb)

        # Now build a live model from disk
        self.control_model = ControlDataModel.from_dict(payload)

        # Keep model units aligned with the (now restored) UnitManager
        self.control_model.length_unit = self.units.length
        self.control_model.force_unit = self.units.force

        # populate initial pressure groups (if any)
        self.pressure.populate_groups()
        self.pressure.refresh()


    # ---------------- Event handlers ----------------

    def _on_generate_clicked(self) -> None:
        from core.analytical_model_classification import classify_elements
        from midas import create_structural_group  # integration layer

        # --- Capture everything on the main (UI) thread ---
        defaults = self.wind_parameters.values()                 # safe here (widget)
        pr   = self.control_model.geometry.pier_radius           # pier radius
        ui_len = self.units.length.upper()                       # capture UI length unit for worker
        sa   = self.control_model.naming.suffix_above            # "_SubAbove" etc.
        base = self.control_model.naming.pier_base_name          # "Pier" etc.
        loads  = self.control_model.loads                        # gust, drag
        naming = self.control_model.naming                       # names & suffixes

        # Closure passes your parameters to the new signature
        def classify_with_params():
            return classify_elements(
                pier_radius=pr,
                length_unit=ui_len,
                suffix_above=sa,
                pier_base_name=base,
            )

        self.bus.progressStarted.emit("Generating wind data...")
        worker = Worker(
            self._run_classification_task,
            classify_with_params,
            create_structural_group,
            defaults,
            naming,
            loads,
            ui_len, 
        )
        worker.signals.finished.connect(lambda _: self.bus.progressFinished.emit(True, "Wind data generated."))
        worker.signals.error.connect(lambda e: self.bus.progressFinished.emit(False, e))
        run_in_thread(worker)


    def _run_classification_task(self, run_classification, create_structural_group, defaults, naming, loads, ui_length_unit):
        """Runs off the UI thread."""
        # Run the wrapped classifier (already parameterized on the UI thread)
        result = run_classification()

        # Load coefficients from Control Data
        gust = f"{loads.gust_factor:g}"
        cd   = f"{loads.drag_coefficient:g}"

        # --- Compute real Structure Height (deck Z - ground), unit-safe ---
        deck_ref   = result.get("deck_reference_height")                  # float | None (model units)
        model_unit = (result.get("model_unit") or "FT").upper()           # e.g., 'FT', 'M', 'IN'
        ground_ui  = float(self.control_model.geometry.reference_height or 0.0)

        if deck_ref is not None:
            # Convert ground from UI units -> model units (safe)
            try:
                ground_in_model = convert_length(ground_ui, from_sym=ui_length_unit, to_sym=model_unit)
            except ValueError:
                ground_in_model = ground_ui  # fallback if units surprise us

            height = max(0.0, float(deck_ref) - ground_in_model)
            height_str = f"{height:g}"
        else:
            height_str = "0"


        # ----- Deck (optional)
        deck_elements = result.get("deck_elements", {})
        if deck_elements:
            deck_ids = list(map(int, deck_elements.keys()))
            deck_group_name = f"{naming.deck_name} Elements"
            create_structural_group(deck_ids, deck_group_name)
            wind_db.add_structural_group(deck_group_name, {
                **defaults,
                "Structure Height": height_str,
                "Gust Factor": gust,
                "Drag Coefficient": cd,
                "Member Type": "Girders",
            })

        # ----- Piers / clusters (labels already include base name & suffix_above from classifier)
        for label, element_dict in (result.get("pier_clusters", {}) or {}).items():
            ids = list(map(int, element_dict.keys()))
            create_structural_group(ids, label)
            wind_db.add_structural_group(label, {
                **defaults,
                "Structure Height": height_str,
                "Gust Factor": gust,
                "Drag Coefficient": cd,
                "Member Type": "Trusses, Columns, and Arches",
            })

        # Compute pressures (still off-thread) and notify UI
        wind_db.update_wind_pressures()
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
        dlg.set_payload(self.control_model.to_dict())     # seed current values
        dlg.controlDataChanged.connect(self._on_control_data_changed)
        dlg.exec()



    def open_wind_load_input(self) -> None:
        WindLoadInput(self).exec()

    def open_pair_wind_load_cases(self) -> None:
        naming = getattr(getattr(self, "control_model", None), "naming", None)
        naming = getattr(naming, "wind", None)
        dlg = PairWindLoadCases(self, naming=naming)
        dlg.exec()



    def _on_control_data_changed(self, model: ControlDataModel) -> None:
        self.control_model = model                        # keep live copy
        self.config.save_control_data(model.to_dict())    # persist
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

        # --- persist unit changes immediately to disk (optional but recommended) ---
        length_combo.currentTextChanged.connect(
            lambda u: (
                setattr(self.control_model, "length_unit", u),
                self.config.save_control_data(self.control_model.to_dict())
            ) if hasattr(self, "control_model") else None
        )
        force_combo.currentTextChanged.connect(
            lambda u: (
                setattr(self.control_model, "force_unit", u),
                self.config.save_control_data(self.control_model.to_dict())
            ) if hasattr(self, "control_model") else None
        )

        sb.addPermanentWidget(QLabel("Force:"))
        sb.addPermanentWidget(force_combo)
        sb.addPermanentWidget(QLabel("Length:"))
        sb.addPermanentWidget(length_combo)



    def _restore_units_from_config(self, payload: dict) -> None:
        """Apply persisted units (if present) to the UnitManager."""
        units_cfg = payload.get("units", {})
        if "length" in units_cfg:
            self.units.set_length(units_cfg["length"])
        if "force" in units_cfg:
            self.units.set_force(units_cfg["force"])
