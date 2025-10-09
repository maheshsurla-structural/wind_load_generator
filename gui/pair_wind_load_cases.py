from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QLabel, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QSpinBox, QPushButton, QSizePolicy, QApplication, QComboBox,
    QHeaderView, QAbstractScrollArea
)
from PySide6.QtGui import QFont, QGuiApplication
import pandas as pd
from PySide6.QtCore import Qt, QEvent

from wind_database.wind_database import wind_db, LOAD_CASES  # <-- updated import path

class PairWindLoadCases(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("Pair Wind Load Cases")
        self.setGeometry(200, 200, 900, 640)

        main_layout = QVBoxLayout()

        wind_load_group = QGroupBox("Pair Wind Loads with Limit States")
        wind_load_layout = QVBoxLayout()

        # --- Number of Angles ---
        num_angles_layout = QHBoxLayout()
        num_angles_layout.addWidget(QLabel("No. of Angles:"))
        self.num_angles_spinbox = QSpinBox()
        self.num_angles_spinbox.setRange(1, 5)
        self.num_angles_spinbox.setValue(1)
        self.num_angles_spinbox.valueChanged.connect(self.update_angle_inputs)
        num_angles_layout.addWidget(self.num_angles_spinbox)
        wind_load_layout.addLayout(num_angles_layout)

        # --- Angle selections (inline) ---
        angles_layout = QHBoxLayout()
        angles_layout.addWidget(QLabel("Angles:"))
        self.angle_dropdowns = []
        default_angles = ["0", "15", "30", "45", "60"]
        for i in range(5):
            dd = QComboBox()
            dd.addItems(default_angles)
            dd.setCurrentText(default_angles[i])
            dd.setEnabled(i == 0)
            self.angle_dropdowns.append(dd)
            angles_layout.addWidget(dd)
        wind_load_layout.addLayout(angles_layout)

        # --- WS table ---
        self.ws_table_widget, ws_table_group = self.create_wind_load_table("WS Case")
        wind_load_layout.addWidget(ws_table_group)

        # --- WL table ---
        self.wl_table_widget, wl_table_group = self.create_wind_load_table("WL Case")
        wind_load_layout.addWidget(wl_table_group)

        # --- Buttons ---
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.close_button = QPushButton("Close")
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.close_button)
        self.ok_button.clicked.connect(self.assign_ws_wl_data)
        self.close_button.clicked.connect(self.close_window)
        wind_load_layout.addLayout(button_layout)

        wind_load_group.setLayout(wind_load_layout)
        main_layout.addWidget(wind_load_group)
        self.setLayout(main_layout)

        # initial load
        self.load_existing_data()

    def create_wind_load_table(self, title):
        table_group_title = "Wind on Structure (WS)" if title == "WS Case" else "Wind on Live Load (WL)"
        table_group = QGroupBox(table_group_title)
        table_layout = QVBoxLayout()

        table = QTableWidget(4, 6)  # 4 load cases, 5 angle columns + 1 header col
        table.setHorizontalHeaderLabels(["Load Combination"] + [f"{title}" for _ in range(5)])
        table.verticalHeader().setVisible(False)

        table.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding))
        table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for i, combination in enumerate(LOAD_CASES):
            item = QTableWidgetItem(combination)
            item.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            table.setItem(i, 0, item)

            for j in range(1, 6):
                case_item = QTableWidgetItem("Case 1")
                if j == 1:
                    case_item.setFlags(
                        Qt.ItemFlag.ItemIsEditable
                        | Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                    )
                else:
                    case_item.setFlags(Qt.ItemFlag.NoItemFlags)
                table.setItem(i, j, case_item)

        table.installEventFilter(self)
        table_layout.addWidget(table)
        table_group.setLayout(table_layout)
        return table, table_group

    def update_angle_inputs(self):
        num_angles = self.num_angles_spinbox.value()

        for i, dd in enumerate(self.angle_dropdowns):
            dd.setEnabled(i == 0 or i < num_angles)

        for table in [self.ws_table_widget, self.wl_table_widget]:
            for col in range(1, 6):
                is_active = col <= num_angles
                for row in range(table.rowCount()):
                    item = table.item(row, col)
                    if item:
                        item.setFlags(
                            (Qt.ItemFlag.ItemIsEditable
                             | Qt.ItemFlag.ItemIsEnabled
                             | Qt.ItemFlag.ItemIsSelectable)
                            if is_active else Qt.ItemFlag.NoItemFlags
                        )
            table.viewport().update()

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.KeyPress:
            widget = self.focusWidget()
            if isinstance(widget, QTableWidget):
                key = event.key()
                mods = event.modifiers()
                if key == Qt.Key.Key_C and (mods & Qt.KeyboardModifier.ControlModifier):
                    self.copy_selection(widget)
                    return True
                elif key == Qt.Key.Key_V and (mods & Qt.KeyboardModifier.ControlModifier):
                    self.paste_selection(widget)
                    return True
        return super().eventFilter(source, event)

    def copy_selection(self, table):
        sr = table.selectedRanges()
        if not sr:
            return
        r = sr[0]
        out = []
        for row in range(r.topRow(), r.bottomRow() + 1):
            row_data = []
            for col in range(r.leftColumn(), r.rightColumn() + 1):
                it = table.item(row, col)
                row_data.append(it.text() if it else "")
            out.append("\t".join(row_data))
        QGuiApplication.clipboard().setText("\n".join(out))

    def paste_selection(self, table):
        txt = QGuiApplication.clipboard().text()
        sr = table.selectedRanges()
        if not sr or not txt:
            return
        r = sr[0]
        rows = txt.split("\n")
        for i, row_text in enumerate(rows):
            cols = row_text.split("\t")
            for j, text in enumerate(cols):
                rr = r.topRow() + i
                cc = r.leftColumn() + j
                if rr < table.rowCount() and cc < table.columnCount():
                    table.setItem(rr, cc, QTableWidgetItem(text))

    # ------------ Save helpers aligned with new WindDatabase ------------

    def _angles_in_use(self):
        """Return the active angle integers for current UI."""
        n = self.num_angles_spinbox.value()
        return [int(self.angle_dropdowns[i].currentText()) for i in range(n)]

    def _clear_existing_rows_for_group(self, df_name: str, group: str):
        """Directly overwrite DataFrame in wind_db to remove rows for a group."""
        if df_name == "ws":
            wind_db.ws_cases = wind_db.ws_cases[wind_db.ws_cases["Group"] != group].reset_index(drop=True)
        else:
            wind_db.wl_cases = wind_db.wl_cases[wind_db.wl_cases["Group"] != group].reset_index(drop=True)

    def save_ws_case_data(self):
        """Store WS as one row per (Load Case, Angle)."""
        angles = self._angles_in_use()

        # Clear existing WS rows
        wind_db.ws_cases = wind_db.ws_cases.iloc[0:0]  # keeps the same columns

        # Save fresh rows
        for row, load_case in enumerate(LOAD_CASES):
            for col_idx, angle in enumerate(angles, start=1):
                item = self.ws_table_widget.item(row, col_idx)
                value = item.text() if item else ""
                details = {"Angle": angle, "Value": value}
                wind_db.add_ws_case(case=load_case, details=details)

    def save_wl_case_data(self):
        """Store WL as one row per (Load Case, Angle)."""
        angles = self._angles_in_use()
        wind_db.wl_cases = pd.DataFrame(columns=["Case", "Details"])  # clear before saving

        for row, load_case in enumerate(LOAD_CASES):
            for col_idx, angle in enumerate(angles, start=1):
                item = self.wl_table_widget.item(row, col_idx)
                value = item.text() if item else ""
                details = {"Angle": angle, "Value": value}
                wind_db.add_wl_case(case=load_case, details=details)


    def assign_ws_wl_data(self):
        """Persist WS & WL to wind_db as DataFrames (overwrite for selected group)."""
        try:
            self.save_ws_case_data()
            self.save_wl_case_data()
            data = wind_db.get_data()
            print("✅ Wind Load Cases Updated Successfully:")
            print("WS Cases:\n", data["WS Cases"])
            print("WL Cases:\n", data["WL Cases"])
        except Exception as e:
            print(f"❌ Error: {e}")

    def close_window(self):
        self.close()

    # ------------ Load from DataFrames back into the UI ------------

    def load_existing_data(self):
        """Load WS/WL DataFrames (no groups) back into the tables."""
        data = wind_db.get_data()
        ws_df = data["WS Cases"]
        wl_df = data["WL Cases"]

        # Reset UI first
        self.num_angles_spinbox.setValue(1)
        for i, dd in enumerate(self.angle_dropdowns):
            dd.setCurrentIndex(i if i < dd.count() else 0)

        # Determine active angles from WS rows (prefer Strength III if available)
        angles = []
        if not ws_df.empty:
            s3 = ws_df[ws_df["Case"] == "Strength III"]
            base = s3 if not s3.empty else ws_df
            angles = sorted({
                int(d["Angle"]) for d in base["Details"]
                if isinstance(d, dict) and "Angle" in d
            })

        # Apply number of angles (cap 1..5) and set dropdowns
        if angles:
            n = min(max(len(angles), 1), 5)
            self.num_angles_spinbox.setValue(n)
            for i in range(min(n, 5)):
                target = str(angles[i])
                idx = self.angle_dropdowns[i].findText(target)
                if idx >= 0:
                    self.angle_dropdowns[i].setCurrentIndex(idx)

        # Clear table cells beyond header
        for table in (self.ws_table_widget, self.wl_table_widget):
            for r in range(table.rowCount()):
                for c in range(1, table.columnCount()):
                    table.setItem(r, c, QTableWidgetItem(""))

        # Fill WS
        if not ws_df.empty:
            for r, load_case in enumerate(LOAD_CASES):
                rows = ws_df[ws_df["Case"] == load_case]
                for c in range(1, self.num_angles_spinbox.value() + 1):
                    angle = int(self.angle_dropdowns[c - 1].currentText())
                    match = rows[rows["Details"].apply(
                        lambda d: isinstance(d, dict) and d.get("Angle") == angle
                    )]
                    if not match.empty:
                        val = match.iloc[0]["Details"].get("Value", "")
                        self.ws_table_widget.setItem(r, c, QTableWidgetItem(str(val)))

        # Fill WL
        if not wl_df.empty:
            for r, load_case in enumerate(LOAD_CASES):
                rows = wl_df[wl_df["Case"] == load_case]
                for c in range(1, self.num_angles_spinbox.value() + 1):
                    angle = int(self.angle_dropdowns[c - 1].currentText())
                    match = rows[rows["Details"].apply(
                        lambda d: isinstance(d, dict) and d.get("Angle") == angle
                    )]
                    if not match.empty:
                        val = match.iloc[0]["Details"].get("Value", "")
                        self.wl_table_widget.setItem(r, c, QTableWidgetItem(str(val)))

        # Apply enabled/disabled state after loading
        self.update_angle_inputs()

