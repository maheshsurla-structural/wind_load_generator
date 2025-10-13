# gui/widgets/pressure_table.py
from PySide6.QtWidgets import QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTableWidget, \
    QTableWidgetItem, QSizePolicy, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt
from core.unit_manager import get_unit_manager
from gui.unit_system import UnitAwareMixin
from wind_database import wind_db, LOAD_CASES

class PressureTable(QWidget, UnitAwareMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.units = get_unit_manager()

        self.group = QGroupBox("Wind Pressure Table")
        vbox = QVBoxLayout(self.group)

        # group selector
        row = QHBoxLayout()
        row.addWidget(QLabel("Group:"))
        self.group_combo = QComboBox()
        row.addWidget(self.group_combo)
        row.addStretch()
        vbox.addLayout(row)

        # table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Load Case", "Gust Wind Speed", "Kz", "G", "Cd", "Pz (ksf)"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        vbox.addWidget(self.table)

        # layout for this widget
        lay = QVBoxLayout(self)
        lay.addWidget(self.group)

        # populate & wire
        self.populate_groups()
        self.group_combo.currentIndexChanged.connect(self.refresh)

        # units
        self.bind_units(self.units)
        self._set_headers()

    # ---- public API ----
    def populate_groups(self):
        names = wind_db.list_structural_groups()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("— Select group —")
        if names:
            self.group_combo.addItems(names)
        self.group_combo.setCurrentIndex(0)
        self.group_combo.blockSignals(False)

    def refresh(self):
        group = (self.group_combo.currentText() or "").strip()
        if not group or group == "— Select group —":
            self.table.setRowCount(0)
            return

        df = wind_db.wind_pressures
        self.table.setRowCount(len(LOAD_CASES))

        for r, case in enumerate(LOAD_CASES):
            self.table.setItem(r, 0, QTableWidgetItem(case))
            row = df[(df["Group"] == group) & (df["Load Case"] == case)]
            if not row.empty:
                d = row.iloc[0]
                self.table.setItem(r, 1, self._num(d.get("Gust Wind Speed", "")))
                self.table.setItem(r, 2, self._num(d.get("Kz", "")))
                self.table.setItem(r, 3, self._num(d.get("G", "")))
                self.table.setItem(r, 4, self._num(d.get("Cd", "")))
                self.table.setItem(r, 5, self._num(d.get("Pz (ksf)", "")))
            else:
                for c in range(1, 6):
                    self.table.setItem(r, c, QTableWidgetItem(""))

    # ---- unit-aware ----
    def update_units(self, length_unit: str, force_unit: str) -> None:
        # optional: push unit labels somewhere if you add them
        self._set_headers()
        # If in the future your df stores base values and you want to display converted ones,
        # you could re-compute cell text here.
        self.refresh()

    # ---- helpers ----
    def _set_headers(self):
        f, L = self.units.force, self.units.length
        self.table.setHorizontalHeaderLabels(["Load Case", "Gust Wind Speed", "Kz", "G", "Cd", f"Pz ({f}/{L}²)"])

    @staticmethod
    def _num(value, nd=3):
        if value in (None, ""):
            txt = ""
        elif isinstance(value, (int, float)):
            txt = f"{value:.{nd}f}"
        else:
            txt = str(value)
        it = QTableWidgetItem(txt)
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return it
