# gui/widgets/wind_parameters.py
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QFormLayout,
    QLineEdit, QComboBox, QLabel, QVBoxLayout
)
from PySide6.QtGui import QDoubleValidator
from PySide6.QtCore import Qt


class WindParameters(QWidget):
    """Simple panel for wind speed and exposure category inputs."""

    def __init__(self, parent=None):

        super().__init__(parent)

        # ---- Group box ----
        self.groupBox = QGroupBox("Wind Parameters")
        form_layout = QFormLayout(self.groupBox)

        # ---- Wind speed ----
        self.wind_speed = QLineEdit("150")
        self.wind_speed.setAlignment(Qt.AlignRight)
        self.wind_speed.setValidator(QDoubleValidator(0.0, 400.0, 2, self))
        self.wind_speed.setPlaceholderText("Enter wind speed (mph)")

        # ---- Exposure category ----
        self.exposure = QComboBox()
        self.exposure.addItems(["B", "C", "D"])
        self.exposure.setCurrentText("C")

        # ---- Layout ----
        form_layout.addRow(QLabel("Wind Speed (mph):"), self.wind_speed)
        form_layout.addRow(QLabel("Exposure Category:"), self.exposure)

        layout = QVBoxLayout(self)
        layout.addWidget(self.groupBox)

    # ---- Public API ----
    def values(self) -> dict:
        """Return the form data as a dictionary."""
        try:
            ws = float((self.wind_speed.text() or "0").strip())
        except ValueError:
            ws = 0.0
        return {
            "Wind Speed": ws,
            "Exposure Category": self.exposure.currentText(),
        }
