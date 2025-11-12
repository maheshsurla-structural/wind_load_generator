
# import json

# from core.wind_load.compute_section_exposures import exposures_numpy


# import midas as Midas

from PySide6.QtWidgets import QApplication
import sys
from gui import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 500)
    window.show()
    sys.exit(app.exec())

# # if __name__ == "__main__":

#     amc = AnalyticalModelClassification(pier_link_distance=10.0) 
#     print(json.dumps(amc.analyze_substructure(), indent=2))

# print(Midas.units.get_all())

# section_properties = Midas.get_section_properties()
# exposures = exposures_numpy(section_properties,as_dataframe=True)

# print(exposures)

# from midas.resources.structural_group import StructuralGroup

# Example 1: By name
# deck_elems = StructuralGroup.get_elements_by_name("Deck Elements")
# print(deck_elems)   # [101, 102, 103, ...]


# from core.wind_load.beam_load import apply_wind_load_to_midas_for_group

# # # Choose one of your actual element groups from MIDAS
# group_name = "Deck Elements"

# # Apply a uniform wind pressure (e.g. 0.8 kN/m²)
# apply_wind_load_to_midas_for_group(
#     group_name=group_name,
#     load_case_name="Wind Load Check",
#     pressure=0.8,
#     load_group_name="Wind Load Check",  # optional, can match load case name
#     udl_direction = "LY",
# )


# from midas import StaticLoadCase
# StaticLoadCase.bulk_upsert([
#     ("Wind Load X", "D", "Dead Load"),
#     ("Wind Load Y", "L", "Live Load"),
#     ("Wind Load Z", "W", "Wind on structure"),
# ])

# from midas.resources.structural_group import StructuralGroup

# element_ids = StructuralGroup.get_elements_by_name("Deck Elements")

# print(element_ids)