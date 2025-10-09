# gui/wind_load_input.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QComboBox, QGroupBox, QFormLayout, QMessageBox, QAbstractItemView, QHeaderView
)

from PySide6.QtGui import QDoubleValidator

from wind_database import wind_db


class WindLoadInput(QDialog):
    
    def __init__(self, parent=None):

        super().__init__(parent)
        self.setWindowTitle("Wind Load Input")
        self.resize(900, 550)  # optional, but helpful

        wind_load_input_layout = QVBoxLayout()

        # --- Group: Wind Parameters ---
        groupBox_str_group_parameters = QGroupBox("Structural Group Parameters")

        # Group name input (so user can create multiple groups)
        self.group_name_input = QComboBox()
        self.refresh_group_names()


        self.wind_speed = QLineEdit("150")
        self.wind_speed.setValidator(QDoubleValidator(0.0, 400.0, 2, self))

        self.exposure = QComboBox()
        self.exposure.addItems(["B", "C", "D"])
        self.exposure.setCurrentText("B")

        self.ref_height = QLineEdit("40")


        self.gust_factor = QComboBox()
        self.gust_factor.addItems(["0.85", "1.00"])
        self.gust_factor.setCurrentText("0.85")

        self.drag_coeff = QLineEdit("1.3")
        self.drag_coeff.setValidator(QDoubleValidator(0.0, 2.0, 2, self))

        self.member_type = QComboBox()
        self.member_type.addItems(["Girders", "Trusses, Columns, and Arches"])

        # Creating wind load parameters layout
        str_group_parameters_layout = QFormLayout(groupBox_str_group_parameters)
        str_group_parameters_layout.addRow(QLabel("Group Name:"), self.group_name_input)
        str_group_parameters_layout.addRow(QLabel("Wind Speed (mph):"), self.wind_speed)
        str_group_parameters_layout.addRow(QLabel("Exposure Category:"), self.exposure)
        str_group_parameters_layout.addRow(QLabel("Structure Height (ft):"), self.ref_height)
        str_group_parameters_layout.addRow(QLabel("Gust Factor (G):"), self.gust_factor)
        str_group_parameters_layout.addRow(QLabel("Drag Coefficient (Cd):"), self.drag_coeff)
        str_group_parameters_layout.addRow(QLabel("Member Type:"), self.member_type)

        # --- Buttons ---
        btn_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh Structural Groups")
        self.refresh_button.clicked.connect(self.refresh_group_names)
        btn_layout.addWidget(self.refresh_button)

        self.add_or_replace_button = QPushButton("Add/Replace")
        self.add_or_replace_button.clicked.connect(self.add_or_replace_group_data)
        btn_layout.addWidget(self.add_or_replace_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_selected_group)
        btn_layout.addWidget(self.delete_button)

        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.save_and_finalize)
        btn_layout.addWidget(self.ok_button)




        # --- Table: Wind Load Input Table (NOT pressures) ---

        self.wind_load_input_table = QTableWidget(0, 7)
        self.wind_load_input_table.setHorizontalHeaderLabels(
            ["Group", "Wind Speed", "Exposure", "Height", "G", "Cd", "Member Type"]
        )
        self.wind_load_input_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.wind_load_input_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.wind_load_input_table.setSelectionMode(QAbstractItemView.SingleSelection) 
        self.wind_load_input_table.verticalHeader().setVisible(False) 


        # Stretch columns to fill the table width
        header = self.wind_load_input_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        # Row→form sync on click
        self.wind_load_input_table.cellClicked.connect(  # NEW
            lambda r, c: self.populate_inputs_from_table()
        )

        # Add all widgets to wind Load input layout
        
        wind_load_input_layout.addWidget(groupBox_str_group_parameters)
        wind_load_input_layout.addWidget(self.wind_load_input_table)
        wind_load_input_layout.addLayout(btn_layout)


        self.setLayout(wind_load_input_layout)

        self.populate_input_table()

    # ---------------------------
    # Button Functions
    # ---------------------------
    def add_or_replace_group_data(self):
        """Add or update a structural group in the database + table."""
        group_name = (self.group_name_input.currentText() or "").strip()
        if not group_name:
            QMessageBox.warning(self, "Missing Name", "Please enter/select a Group Name.")  # NEW
            return

        try:
            params = {
                "Wind Speed": float(self.wind_speed.text()),
                "Exposure Category": self.exposure.currentText(),
                "Structure Height": float(self.ref_height.text()),
                "Gust Factor": float(self.gust_factor.currentText()),
                "Drag Coefficient": float(self.drag_coeff.text()),
                "Member Type": self.member_type.currentText(),
            }
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric values.")
            return

        wind_db.add_structural_group(group_name, params)
        self.populate_input_table()




    def delete_selected_group(self):
        """Delete selected group from database + refresh table."""
        sel = self.wind_load_input_table.selectedItems()
        if not sel:
            return

        row = sel[0].row()
        item = self.wind_load_input_table.item(row, 0)
        if not item:
            return

        group_name = item.text().strip()

        # Optional confirm (uncomment if you want)
        # if QMessageBox.question(self, "Delete Group", f"Delete '{group_name}'?",
        #                         QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
        #     return

        if group_name in wind_db.structural_groups:
            del wind_db.structural_groups[group_name]

        self.populate_input_table()


    def save_and_finalize(self):
        """Finalize groups and compute pressures only once."""
        wind_db.update_wind_pressures()
        QMessageBox.information(self, "Saved", "All groups finalized and pressures computed.")
        self.close()



    # ---------------------------
    # Table Helpers
    # ---------------------------
    def populate_input_table(self):
        """Populate wind_load_input_table from structural_groups dict."""
        groups = wind_db.structural_groups
        self.wind_load_input_table.setRowCount(len(groups))

        for r, (name, params) in enumerate(groups.items()):
            self.wind_load_input_table.setItem(r, 0, QTableWidgetItem(name))
            self.wind_load_input_table.setItem(r, 1, QTableWidgetItem(str(params["Wind Speed"])))
            self.wind_load_input_table.setItem(r, 2, QTableWidgetItem(params["Exposure Category"]))
            self.wind_load_input_table.setItem(r, 3, QTableWidgetItem(str(params["Structure Height"])))
            self.wind_load_input_table.setItem(r, 4, QTableWidgetItem(str(params["Gust Factor"])))
            self.wind_load_input_table.setItem(r, 5, QTableWidgetItem(str(params["Drag Coefficient"])))
            self.wind_load_input_table.setItem(r, 6, QTableWidgetItem(params["Member Type"]))

        self.wind_load_input_table.resizeColumnsToContents()

    def populate_inputs_from_table(self):
        """When a row is selected, load its group's parameters into the form."""
        sel = self.wind_load_input_table.selectedItems()
        if not sel:
            return

        row = sel[0].row()
        item = self.wind_load_input_table.item(row, 0)
        if not item:
            return

        group_name = item.text().strip()
        params = wind_db.get_structural_group(group_name)
        if not params:
            return

        self.group_name_input.setCurrentText(group_name)
        self.wind_speed.setText(str(params["Wind Speed"]))
        self.exposure.setCurrentText(params["Exposure Category"])
        self.ref_height.setText(str(params["Structure Height"]))
        self.gust_factor.setCurrentText(str(params["Gust Factor"]))  # CHANGED (cast to str)
        self.drag_coeff.setText(str(params["Drag Coefficient"]))
        self.member_type.setCurrentText(params["Member Type"])

    def refresh_group_names(self):
        """Fetch and update group names from Midas Civil NX."""
        try:
            from main import MidasAPI
            result = MidasAPI("GET", "/db/GRUP")
            groups = result.get("GRUP", {}) if result else {}
        except Exception:
            groups = {}

        self.group_name_input.clear()
        self.group_name_input.addItems(
            [gdata["NAME"] for gdata in groups.values() if isinstance(gdata, dict) and "NAME" in gdata]
        )  # CHANGED (safer)

