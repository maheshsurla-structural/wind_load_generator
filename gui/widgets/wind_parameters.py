# gui/widgets/wind_parameters.py
from PySide6.QtWidgets import QWidget, QGroupBox, QFormLayout, QLineEdit, QComboBox, QLabel, QVBoxLayout
from PySide6.QtGui import QDoubleValidator
from core.unit_manager import get_unit_manager
from gui.unit_system import UnitAwareMixin

class WindParametersPanel(QWidget, UnitAwareMixin):
    """Wind Speed and Exposure inputs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.units = get_unit_manager()

        self.group = QGroupBox("Wind Parameters")
        form = QFormLayout(self.group)

        self.wind_speed = QLineEdit("150")
        self.wind_speed.setValidator(QDoubleValidator(0.0, 400.0, 2, self))
        self.exposure = QComboBox()
        self.exposure.addItems(["B", "C", "D"])
        self.exposure.setCurrentText("C")

        form.addRow(QLabel("Wind Speed (mph):"), self.wind_speed)
        form.addRow(QLabel("Exposure Category:"), self.exposure)

        lay = QVBoxLayout(self)
        lay.addWidget(self.group)

        # Optional: bind units to labels if you add unit labels
        self.length_unit_labels = []  # e.g., [self.speed_unit_label]
        self.force_unit_labels = []
        self.bind_units(self.units)

    def values(self) -> dict:
        try:
            ws = float((self.wind_speed.text() or "0").strip())
        except ValueError:
            ws = 0.0
        return {"Wind Speed": ws, "Exposure Category": self.exposure.currentText()}
