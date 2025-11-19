
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


# from core.wind_load.beam_load import (
#     build_uniform_pressure_beam_load_plan_for_group,
#     apply_beam_load_plan_to_midas,

# )
# from core.wind_load.structural_wind_loads import test_structural_wind_two_cases

# test_structural_wind_two_cases()




# from midas import StaticLoadCase
# StaticLoadCase.bulk_upsert([
#     ("Wind Load X", "D", "Dead Load"),
#     ("Wind Load Y", "L", "Live Load"),
#     ("Wind Load Z", "W", "Wind on structure"),
# ])

# from midas.resources.structural_group import StructuralGroup

# element_ids = StructuralGroup.get_elements_by_name("Deck Elements")

# print(element_ids)