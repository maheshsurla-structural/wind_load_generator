# gui/main_window.py

from PySide6.QtWidgets import (QMainWindow, QToolBar, QStatusBar, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton
                               , QLineEdit, QFormLayout, QLabel, QComboBox, QTableWidget, QSizePolicy, QHeaderView, QTableWidgetItem, 
                               QAbstractItemView)

from PySide6.QtGui import QIntValidator, QDoubleValidator, QAction

from PySide6.QtCore import Qt

from gui.wind_load_input import WindLoadInput

from gui.pair_wind_load_cases import PairWindLoadCases

from wind_database import wind_db, LOAD_CASES

from gui.control_data import ControlData

from gui.unit_system import UnitSystem

# --- persistence (optional but you call _save_control_data, so include it) ---
import json, os
from pathlib import Path

class MainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wind Load Generator AASHTO")

        # ---- central widget ----
        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)
        centralWidget_layout = QVBoxLayout(centralWidget)

        # ---------------------------
        # Wind Parameters (top group)
        # ---------------------------
        groupBox_wind_parameters = QGroupBox("Wind Parameters")

        self.wind_speed = QLineEdit("150")
        self.wind_speed.setValidator(QDoubleValidator(0.0, 400.0, 2, self))

        self.exposure = QComboBox()
        self.exposure.addItems(["B", "C", "D"])
        self.exposure.setCurrentText("C")

        wind_paramters_layout = QFormLayout(groupBox_wind_parameters)
        wind_paramters_layout.addRow(QLabel("Wind Speed (mph):"), self.wind_speed)
        wind_paramters_layout.addRow(QLabel("Exposure Category:"), self.exposure)

        # ---------------------------
        # Structural Group Classification & Wind Data
        # ---------------------------
        groupBox_wind_parameters_stuctural_group = QGroupBox("Structural Group Classification & Wind Data")

        self.generate_btn = QPushButton("Generate Wind Data")
        self.edit_btn     = QPushButton("Edit Wind Data")
        self.generate_btn.clicked.connect(self.run_classification_and_store)
        self.edit_btn.clicked.connect(self.open_wind_load_input)

        wind_paramters_stuctural_group_layout = QHBoxLayout(groupBox_wind_parameters_stuctural_group)
        wind_paramters_stuctural_group_layout.addWidget(self.generate_btn)
        wind_paramters_stuctural_group_layout.addWidget(self.edit_btn)

        # ---------------------------
        # Toolbar
        # ---------------------------
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        toolbar.setMovable(False)

        settings_action = QAction("Control Data", self)
        toolbar.addAction(settings_action)
        settings_action.triggered.connect(self.open_control_data)

        # ---------------------------
        # Status Bar + Unit Selection (create UnitSystem BEFORE pressure table)
        # ---------------------------
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)

        self.force_unit = QComboBox()
        self.force_unit.addItems(["KGF", "TONF", "N", "KN", "LBF", "KIP"])
        self.force_unit.setCurrentText("KIP")

        self.length_unit = QComboBox()
        self.length_unit.addItems(["MM", "CM", "M", "IN", "FT"])
        self.length_unit.setCurrentText("FT")

        statusbar.addPermanentWidget(self.force_unit)
        statusbar.addPermanentWidget(self.length_unit)

        # Global unit context (ALL CAPS)
        self.units = UnitSystem(length_symbol=self.length_unit.currentText(),
                                force_symbol=self.force_unit.currentText())

        # ---- app-level control data (BASE units: M, N) ----
        self._control_data = {
            "structural": {"reference_height_m": 0.0, "pier_radius_m": 10.0},
            "naming": {
                "deck_name": "Deck",
                "pier_base_name": "Pier",
                "starting_index": 1,
                "suffix_above": "_SubAbove",
                "suffix_below": "_SubBelow",
            },
            "loads": {"gust_factor": 1.00, "drag_coefficient": 1.20},
            "units": {"length": self.units.length, "force": self.units.force},
        }

        # Wire combos → UnitSystem
        self.force_unit.currentTextChanged.connect(self.units.set_force)
        self.length_unit.currentTextChanged.connect(self.units.set_length)

        # Load previously saved control data, then sync unit combos (triggers UnitSystem)
        self._load_control_data()
        self.length_unit.setCurrentText(self._control_data["units"].get("length", self.units.length))
        self.force_unit.setCurrentText(self._control_data["units"].get("force", self.units.force))

        # React to unit changes (connect ONCE)
        self.units.unitsChanged.connect(self._on_units_changed)

        # ---------------------------
        # Pressure Table (build AFTER units exist)
        # ---------------------------
        pressure_group = QGroupBox("Wind Pressure Table")
        pressure_layout = QVBoxLayout(pressure_group)

        # Group selector row
        group_row = QHBoxLayout()
        group_row.addWidget(QLabel("Group:"))
        self.group_combo = QComboBox()
        group_row.addWidget(self.group_combo)
        group_row.addStretch()
        pressure_layout.addLayout(group_row)

        # Table
        self.pressure_table = QTableWidget()
        self.pressure_table.setRowCount(0)  # start empty; fill on selection
        self.pressure_table.setColumnCount(6)
        self.pressure_table.setHorizontalHeaderLabels(
            ["Load Case", "Gust Wind Speed", "Kz", "G", "Cd", "Pz (ksf)"]
        )
        self.pressure_table.verticalHeader().setVisible(False)
        self.pressure_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pressure_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pressure_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.pressure_table.verticalHeader().setDefaultSectionSize(28)
        self.pressure_table.setAlternatingRowColors(True)
        self.pressure_table.setWordWrap(False)
        self.pressure_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        pressure_layout.addWidget(self.pressure_table)

        # Populate groups & wire selection ONCE
        self.populate_group_combo()
        self.group_combo.currentIndexChanged.connect(self.update_pressure_table)

        # Set header with current units & start empty until a real group is selected
        self._set_pressure_headers()
        self.update_pressure_table()

        # ---------------------------
        # Wind Load Cases
        # ---------------------------
        groupBox_wind_load_cases = QGroupBox("Wind Load Cases")
        self.pair_wind_load_cases_btn = QPushButton("Pair Wind Load Cases")
        self.pair_wind_load_cases_btn.clicked.connect(self.open_pair_wind_load_cases)
        wind_load_cases_layout = QHBoxLayout(groupBox_wind_load_cases)
        wind_load_cases_layout.addWidget(self.pair_wind_load_cases_btn)

        # ---------------------------
        # Add to Central Widget Layout (ONCE, in order)
        # ---------------------------
        centralWidget_layout.addWidget(groupBox_wind_parameters)
        centralWidget_layout.addWidget(groupBox_wind_parameters_stuctural_group)
        centralWidget_layout.addWidget(pressure_group)
        centralWidget_layout.addWidget(groupBox_wind_load_cases)





    # ---------------------------
    # Helpers / Actions
    # ---------------------------

    def get_default_classification_inputs(self) -> dict:
        """Return Wind Speed and Exposure Category from the main window inputs."""
        text = (self.wind_speed.text() or "").strip()
        try:
            wind_speed_val = float(text)
        except ValueError:
            wind_speed_val = 0.0

        return {
            "Wind Speed": wind_speed_val,
            "Exposure Category": self.exposure.currentText()
        }


    def run_classification_and_store(self):
        """
        Classify model, create structural groups in MIDAS, and persist
        group parameters into WindDatabase, then recompute wind pressures.
        """
        try:
            # Local import avoids circulars with dialogs
            from core.analytical_model_classification import classify_elements           
            from midas import create_structural_group            

            # --- inputs from the main window ---
            defaults = self.get_default_classification_inputs()  # {"Wind Speed": float, "Exposure Category": "B/C/D"}

            # --- run your classifier (returns dict with keys used below) ---
            result = classify_elements()

            # --- Deck Elements group ---
            deck_elements = result.get("deck_elements", {})
            if deck_elements:
                deck_ids = list(map(int, deck_elements.keys()))
                create_structural_group(deck_ids, "Deck Elements")

                wind_db.add_structural_group("Deck Elements", {
                    **defaults,
                    "Structure Height": "40",          # TODO: replace placeholders as needed
                    "Gust Factor": "0.85",
                    "Drag Coefficient": "1.3",
                    "Member Type": "Girders"
                })

            # --- Pier Cluster groups ---
            pier_clusters = result.get("pier_clusters", {})
            for group_label, element_dict in pier_clusters.items():
                element_ids = list(map(int, element_dict.keys()))
                create_structural_group(element_ids, group_label)

                wind_db.add_structural_group(group_label, {
                    **defaults,
                    "Structure Height": "40",
                    "Gust Factor": "0.85",
                    "Drag Coefficient": "1.3",
                    "Member Type": "Trusses, Columns, and Arches"
                })

            # --- recompute pressures table for all groups ---
            wind_db.update_wind_pressures()
            self.populate_group_combo()
            self.update_pressure_table()


            # Optional: if you later add WS/WL creation, call wind_db.add_ws_case / add_wl_case here

            # UX feedback
            if self.statusBar():
                self.statusBar().showMessage("✅ Wind data generated: groups saved and pressures updated.", 5000)

        except Exception as exc:
            # Minimal error toast
            if self.statusBar():
                self.statusBar().showMessage(f"❌ Failed to generate wind data: {exc}", 8000)
            # Also helpful for dev console
            print("run_classification_and_store error:", exc)



    def populate_group_combo(self):
        """Fill the Group dropdown from the Wind Database with a placeholder first."""
        names = wind_db.list_structural_groups()

        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("— Select group —")  # placeholder
        if names:
            self.group_combo.addItems(names)
        self.group_combo.setCurrentIndex(0)  # keep placeholder selected by default
        self.group_combo.blockSignals(False)
        

    def update_pressure_table(self):
        """
        Update pressure table for the selected group using wind_db.wind_pressures.
        Table remains empty until a real group is selected.
        """
        group = (self.group_combo.currentText() or "").strip()

        # If no real group selected, show nothing
        if not group or group == "— Select group —":
            self.pressure_table.setRowCount(0)
            return

        df = wind_db.wind_pressures  # expects columns: Group, Load Case, Gust Wind Speed, Kz, G, Cd, Pz (ksf)

        # Show rows only after a valid group is selected
        self.pressure_table.setRowCount(len(LOAD_CASES))

        for r, case in enumerate(LOAD_CASES):
            # Column 0: Load Case (always set after group chosen)
            self.pressure_table.setItem(r, 0, QTableWidgetItem(case))

            # Filter the dataframe for this group + case
            row = df[(df["Group"] == group) & (df["Load Case"] == case)]

            if not row.empty:
                d = row.iloc[0]
                self.pressure_table.setItem(r, 1, self._num_item(d.get("Gust Wind Speed", "")))
                self.pressure_table.setItem(r, 2, self._num_item(d.get("Kz", "")))
                self.pressure_table.setItem(r, 3, self._num_item(d.get("G", "")))
                self.pressure_table.setItem(r, 4, self._num_item(d.get("Cd", "")))
                self.pressure_table.setItem(r, 5, self._num_item(d.get("Pz (ksf)", "")))
            else:
                # Clear data columns if nothing for this case
                for c in range(1, 6):
                    self.pressure_table.setItem(r, c, QTableWidgetItem(""))


    def _on_units_changed(self, length_sym: str, force_sym: str):
        # If you have unit-bearing columns/fields, update their text & headers here.
        self._refresh_all_views()

    def _refresh_all_views(self):
        # Example: refresh text fields and tables
        # self._refresh_parameters_panel()
        # self._refresh_pressure_table()
        pass


    def open_control_data(self):
        dlg = ControlData(self, units=self.units)

        # Prefill: convert BASE → UI units for the dialog
        dlg.set_payload(self._payload_for_dialog())

        # Save back on Apply/OK
        dlg.controlDataChanged.connect(self._on_control_data_changed)

        dlg.exec()


    def open_wind_load_input(self):
        dlg = WindLoadInput(self)
        dlg.exec()

    def open_pair_wind_load_cases(self):
        dlg = PairWindLoadCases(self)
        dlg.exec()




    def _config_path(self) -> Path:
        cfg_dir = Path(os.path.expanduser("~")) / ".wind_load_generator"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir / "control_data.json"

    def _save_control_data(self) -> None:
        try:
            self._config_path().write_text(json.dumps(self._control_data, indent=2))
        except Exception as e:
            print("Failed to save control_data.json:", e)

    def _load_control_data(self) -> None:
        p = self._config_path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
            # be defensive: only update known keys
            s = data.get("structural", {})
            n = data.get("naming", {})
            l = data.get("loads", {})
            self._control_data["structural"]["reference_height_m"] = float(s.get("reference_height_m", 0.0))
            self._control_data["structural"]["pier_radius_m"]      = float(s.get("pier_radius_m", 10.0))
            self._control_data["naming"].update(n)
            self._control_data["loads"].update(l)
            self._control_data["units"].update(data.get("units", {}))
        except Exception as e:
            print("Failed to load control_data.json:", e)



    def _on_control_data_changed(self, payload: dict):
        """
        Receive dialog data (in CURRENT UI units), convert to BASE, persist,
        and refresh anything that depends on control data.
        """
        u = self.units

        # Convert UI → BASE (meters)
        try:
            ref_h_ui = float(payload["structural"]["reference_height"])
            pier_r_ui = float(payload["structural"]["pier_radius"])
        except Exception:
            ref_h_ui = 0.0
            pier_r_ui = 10.0

        ref_h_m  = u.to_base_length(ref_h_ui)
        pier_r_m = u.to_base_length(pier_r_ui)

        # Persist to app-level store (BASE units)
        self._control_data = {
            "structural": {
                "reference_height_m": ref_h_m,
                "pier_radius_m": pier_r_m,
            },
            "naming": {
                "deck_name": payload["naming"]["deck_name"].strip(),
                "pier_base_name": payload["naming"]["pier_base_name"].strip(),
                "starting_index": int(payload["naming"]["starting_index"]),
                "suffix_above": payload["naming"]["suffix_above"].strip(),
                "suffix_below": payload["naming"]["suffix_below"].strip(),
            },
            "loads": {
                "gust_factor": float(payload["loads"]["gust_factor"]),
                "drag_coefficient": float(payload["loads"]["drag_coefficient"]),
            },
            "units": {
                "length": u.length,
                "force":  u.force,
            },
        }

        # OPTIONAL: push to your domain layer if you expose an API:
        # wind_db.set_control_data(self._control_data)

        # If pressures depend on these values, recompute:
        # wind_db.update_wind_pressures()

        # refresh any views that should reflect this immediately
        self.update_pressure_table()

        # UX toast
        if self.statusBar():
            self.statusBar().showMessage("Control data saved.", 3000)

        # OPTIONAL: save to disk so it survives restarts
        self._save_control_data()

    def _payload_for_dialog(self) -> dict:
        """Return a payload in the CURRENT UI units for ControlData dialog."""
        u = self.units
        cd = self._control_data

        ref_h_ui = u.from_base_length(cd["structural"]["reference_height_m"])
        pier_r_ui = u.from_base_length(cd["structural"]["pier_radius_m"])

        return {
            "structural": {
                "reference_height": ref_h_ui,
                "pier_radius": pier_r_ui,
            },
            "naming": dict(cd["naming"]),
            "loads": dict(cd["loads"]),
            "units": {"length": u.length, "force": u.force},
        }


    # ---------- helpers & handlers (put these as methods of MainWindow) ----------

    def _set_pressure_headers(self):
        """
        Update the last column header to match current units.
        Pz is pressure ~ force / length^2. We show it textually (no conversion here),
        since the DataFrame already stores computed values.
        """
        f, L = self.units.force, self.units.length   # ALL CAPS
        headers = ["Load Case", "Gust Wind Speed", "Kz", "G", "Cd", f"Pz ({f}/{L}²)"]
        self.pressure_table.setHorizontalHeaderLabels(headers)

    def _num_item(self, value, nd=3) -> QTableWidgetItem:
        """
        Create a right-aligned numeric cell. Strings pass through unchanged.
        """
        if value in (None, ""):
            txt = ""
        elif isinstance(value, (int, float)):
            txt = f"{value:.{nd}f}"
        else:
            txt = str(value)
        it = QTableWidgetItem(txt)
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return it

    def populate_group_combo(self):
        """
        Fill the Group dropdown from the Wind Database with a placeholder first.
        """
        names = wind_db.list_structural_groups()

        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("— Select group —")  # placeholder
        if names:
            self.group_combo.addItems(names)
        self.group_combo.setCurrentIndex(0)  # keep placeholder selected by default
        self.group_combo.blockSignals(False)

    def update_pressure_table(self):
        """
        Update pressure table for the selected group using wind_db.wind_pressures.
        Table remains empty until a real group is selected.
        Expects df columns: Group, Load Case, Gust Wind Speed, Kz, G, Cd, Pz (ksf)
        """
        group = (self.group_combo.currentText() or "").strip()

        # If no real group selected, show nothing
        if not group or group == "— Select group —":
            self.pressure_table.setRowCount(0)
            return

        df = wind_db.wind_pressures

        # Show rows only after a valid group is selected
        self.pressure_table.setRowCount(len(LOAD_CASES))

        for r, case in enumerate(LOAD_CASES):
            # Column 0: Load Case (always set after group chosen)
            self.pressure_table.setItem(r, 0, QTableWidgetItem(case))

            # Filter the dataframe for this group + case
            row = df[(df["Group"] == group) & (df["Load Case"] == case)]

            if not row.empty:
                d = row.iloc[0]
                self.pressure_table.setItem(r, 1, self._num_item(d.get("Gust Wind Speed", "")))
                self.pressure_table.setItem(r, 2, self._num_item(d.get("Kz", "")))
                self.pressure_table.setItem(r, 3, self._num_item(d.get("G", "")))
                self.pressure_table.setItem(r, 4, self._num_item(d.get("Cd", "")))
                # The dataframe column name may stay "Pz (ksf)" internally; we only change the header label
                self.pressure_table.setItem(r, 5, self._num_item(d.get("Pz (ksf)", "")))
            else:
                # Clear data columns if nothing for this case
                for c in range(1, 6):
                    self.pressure_table.setItem(r, c, QTableWidgetItem(""))

    def _on_units_changed(self, length_sym: str, force_sym: str):
        """
        If units change, refresh headers and (optionally) re-render values if you
        later decide to store base values and display converted ones.
        For now, only the header changes since df values are already computed.
        """
        self._set_pressure_headers()
        # if gust speed or Pz are recomputed in wind_db based on units,
        # you can also call wind_db.update_wind_pressures() here.
        self.update_pressure_table()
