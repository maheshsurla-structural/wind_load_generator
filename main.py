from PySide6.QtWidgets import QApplication
import sys
from gui import MainWindow
import json

from core.wind_load.compute_section_exposures import exposures_numpy


import midas as Midas

# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     window = MainWindow()
#     window.resize(900, 500)
#     window.show()
#     sys.exit(app.exec())


# # if __name__ == "__main__":

#     amc = AnalyticalModelClassification(pier_link_distance=10.0) 
#     print(json.dumps(amc.analyze_substructure(), indent=2))

# print(Midas.units.get_all())

section_properties = Midas.get_section_properties()
exposures = exposures_numpy(section_properties,as_dataframe=True)

print(exposures)
