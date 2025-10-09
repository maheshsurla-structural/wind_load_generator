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

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wind Load Generator AASHTO")

        # ---- central widget ----
        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)
        centralWidget_layout = QVBoxLayout(centralWidget)

        # --- group box: Wind Parameters ---
        groupBox_wind_parameters = QGroupBox("Wind Parameters")

        #Fields for wind parameters would go here
        self.wind_speed = QLineEdit("150")
        self.wind_speed.setValidator(QDoubleValidator(0.0, 400.0, 2,self))

        self.exposure = QComboBox()
        self.exposure.addItems(["B", "C", "D"])
        self.exposure.setCurrentText("C")

        # self.gust_factor = QComboBox()
        # self.gust_factor.addItems(["0.85", "1.00"])
        # self.gust_factor.setCurrentText("0.85")

        # self.drag_coeff = QLineEdit("1.3")
        # self.drag_coeff.setValidator(QDoubleValidator(0.0, 2.0, 2, self))


       # Creating wind parameters layout
        wind_paramters_layout = QFormLayout(groupBox_wind_parameters)
        wind_paramters_layout.addRow(QLabel("Wind Speed (mph):"), self.wind_speed)
        wind_paramters_layout.addRow(QLabel("Exposure Category:"), self.exposure)
        # wind_paramters_layout.addRow(QLabel("Gust Factor:"), self.gust_factor)
        # wind_paramters_layout.addRow(QLabel("Drag Coefficient:"), self.drag_coeff)

        # ---------------------------
        # Structural Group Classification & Wind Data
        # ---------------------------
        groupBox_wind_parameters_stuctural_group = QGroupBox("Structural Group Classification & Wind Data")


        self.generate_btn = QPushButton("Generate Wind Data")
        self.edit_btn = QPushButton("Edit Wind Data")

        self.edit_btn.clicked.connect(self.open_wind_load_input)  # connect click

        # Creating Structural Group Classification & Wind Data layout
        wind_paramters_stuctural_group_layout = QHBoxLayout(groupBox_wind_parameters_stuctural_group)
        wind_paramters_stuctural_group_layout.addWidget(self.generate_btn)
        self.generate_btn.clicked.connect(self.run_classification_and_store)


        # ---------------------------
        # Pressure Table
        # ---------------------------
        pressure_group = QGroupBox("Wind Pressure Table")
        pressure_layout = QVBoxLayout(pressure_group)

        # --- Group selector row ---
        group_row = QHBoxLayout()
        group_row.addWidget(QLabel("Group:"))
        self.group_combo = QComboBox()
        group_row.addWidget(self.group_combo)
        group_row.addStretch()
        pressure_layout.addLayout(group_row)

        # --- Pressure Table ---
        self.pressure_table = QTableWidget()
        self.pressure_table.setRowCount(len(LOAD_CASES))
        self.pressure_table.setColumnCount(6)
        self.pressure_table.setHorizontalHeaderLabels([
            "Load Case", "Gust Wind Speed", "Kz", "G", "Cd", "Pz (ksf)"
        ])

        # Appearance / UX
        self.pressure_table.verticalHeader().setVisible(False)
        self.pressure_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pressure_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pressure_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.pressure_table.verticalHeader().setDefaultSectionSize(28)
        self.pressure_table.setAlternatingRowColors(True)
        self.pressure_table.setWordWrap(False)
        self.pressure_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        pressure_layout.addWidget(self.pressure_table)



        # ---------------------------
        # Wind Load Cases
        # ---------------------------
        groupBox_wind_load_cases = QGroupBox("Wind Load Cases")

        self.pair_wind_load_cases_btn = QPushButton("Pair Wind Load Cases")
        self.pair_wind_load_cases_btn.clicked.connect(self.open_pair_wind_load_cases)

        wind_load_cases_layout = QHBoxLayout(groupBox_wind_load_cases)
        wind_load_cases_layout.addWidget(self.pair_wind_load_cases_btn)  



        wind_paramters_stuctural_group_layout.addWidget(self.edit_btn)

        # Add to Central Widget Layout
        centralWidget_layout.addWidget(groupBox_wind_parameters)
        centralWidget_layout.addWidget(groupBox_wind_parameters_stuctural_group)
        centralWidget_layout.addWidget(pressure_group)
        centralWidget_layout.addWidget(groupBox_wind_load_cases)




        # -------------------------------------------
        # Toolbar with Control Data Button
        # -------------------------------------------
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        toolbar.setMovable(False)

        # --- Settings button (appears on top-right) ---
        settings_action = QAction("Control Data", self)
        toolbar.addAction(settings_action)
        settings_action.triggered.connect(self.open_control_data)




        # ---------------------------
        # Status Bar with Unit Selection
        # ---------------------------
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)

        self.force_unit = QComboBox()
        self.force_unit.addItems(["KGF", "TONF", "N", "KN", "LBF", "KIPS"])
        self.force_unit.setCurrentText("KIPS")

        self.length_unit = QComboBox()
        self.length_unit.addItems(["MM", "CM", "M", "IN", "FT"])
        self.length_unit.setCurrentText("FT")

        statusbar.addPermanentWidget(self.force_unit)
        statusbar.addPermanentWidget(self.length_unit)

        self.units = UnitSystem(self.force_unit, self.length_unit)

        # Populate group combo (with placeholder), wire change to table update
        self.populate_group_combo()
        self.group_combo.currentIndexChanged.connect(self.update_pressure_table)

        # Start empty (no rows visible) until a real group is selected
        self.update_pressure_table()


    # ---------------------------
    # Helpers / Actions
    # ---------------------------

    def _num_item(self, value) -> QTableWidgetItem:
        """Create a right-aligned table item for numeric display."""
        it = QTableWidgetItem("" if value is None else str(value))
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return it

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



    def open_control_data(self):
        dlg = ControlData(self)
        dlg.exec()


    def open_wind_load_input(self):
        dlg = WindLoadInput(self)
        dlg.exec()

    def open_pair_wind_load_cases(self):
        dlg = PairWindLoadCases(self)
        dlg.exec()


