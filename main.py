
# import json

# from core.wind_load.compute_section_exposures import exposures_numpy

# from core.analytical_model_classification.get_superstructure_section_ids_with_typeandshape import (
#     get_superstructure_section_ids_with_typeandshape,
# )

# if __name__ == "__main__":
#     section_ids = get_superstructure_section_ids_with_typeandshape()
#     print(section_ids)


from PySide6.QtWidgets import QApplication
import sys
from gui import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 500)
    window.show()
    sys.exit(app.exec())


# from midas.resources.section import Section

# if __name__ == "__main__":
#     print("before Section.get_all()")
#     try:
#         sections = Section.get_all()
#         print("after Section.get_all()")

#         from pprint import pprint
#         pprint(sections)

#         # Optional: write to json for VS Code
#         import json
#         with open("sections_debug.json", "w") as f:
#             json.dump(sections, f, indent=4)

#     except Exception as e:
#         print("ERROR in Section.get_all:", repr(e))


# from tests.model_classification import run_classification_diagnostics
# if __name__ == "__main__":
#     run_classification_diagnostics()


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


# main.py

# import sys
# from pathlib import Path

# ROOT = Path(__file__).resolve().parent
# if str(ROOT) not in sys.path:
#     sys.path.insert(0, str(ROOT))


# def run_unit_tests():
#     import pytest

#     print("\n=== Running substructure wind UNIT TESTS ===")
#     result = pytest.main(["-q", "tests/test_substructure_wind_components.py"])
#     if result != 0:
#         print("\n❌ Unit tests failed.")
#         sys.exit(result)
#     print("✅ Unit tests passed.")


# def run_substructure_demo():
#     """
#     Run the integration-style demo (no write to MIDAS unless you flip APPLY_TO_MIDAS).
#     """
#     from tests.run_substructure_wind_demo import run_demo

#     print("\n=== Running substructure wind DEMO ===")
#     run_demo()
#     print("=== Demo finished ===\n")


# if __name__ == "__main__":
#     RUN_TESTS = True
#     RUN_DEMO = True

#     if RUN_TESTS:
#         run_unit_tests()

#     if RUN_DEMO:
#         run_substructure_demo()

#     print("\nAll done from main.py ✅")

# from core.geometry.midas_element_local_axes import MidasElementLocalAxes

# # Build snapshot once (you can pass a custom logger if you like)
# model = MidasElementLocalAxes.from_midas(debug=True)

# axes_1 = model.compute_local_axes_for_element(1030)
# axes_2 = model.compute_local_axes_for_element(2)
# axes_3 = model.compute_local_axes_for_element(3)
# axes_4 = model.compute_local_axes_for_element(4)
# axes_5 = model.compute_local_axes_for_element(5)
# axes_6 = model.compute_local_axes_for_element(6)
# later you can do plates / solids using the same `model`


# from pretension.apply_ptns_as_nodal import apply_ptns_element_as_nodal

# results = apply_ptns_element_as_nodal(
#     elem_id=1033,
#     suffix="_nodal",
#     mode="append",
#     use_group_from_ptns=False,  # start safe
#     debug=True
# )

# print(results)

 