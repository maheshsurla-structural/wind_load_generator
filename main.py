from PySide6.QtWidgets import QApplication
import sys
from gui import MainWindow
import json

from midas.midas_api import MidasAPI
from midas.units import get_distance_unit

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 500)
    window.show()
    sys.exit(app.exec())


# # if __name__ == "__main__":

#     amc = AnalyticalModelClassification(pier_link_distance=10.0)
#     print(json.dumps(amc.analyze_substructure(), indent=2))

# units = get_distance_unit()
# print(units)