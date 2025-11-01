# from PySide6.QtWidgets import QApplication
# import sys
# from gui import MainWindow
# import json

# from core.wind_load.compute_section_exposures import exposures_numpy


# import midas as Midas

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

# section_properties = Midas.get_section_properties()
# exposures = exposures_numpy(section_properties,as_dataframe=True)

# print(exposures)

# from midas.resources.structural_group import StructuralGroup

# Example 1: By name
# deck_elems = StructuralGroup.get_elements_by_name("Deck Elements")
# print(deck_elems)   # [101, 102, 103, ...]


from core.wind_load.beam_load import (
    _get_element_to_section_map,
    build_beam_load_plan_for_group,
    apply_wind_load_to_midas_for_group,
)
from midas import elements, get_section_properties
from midas.resources.structural_group import StructuralGroup

group_name = "Deck Elements"  # <-- use a real group in your model

print("Group elements:", StructuralGroup.get_elements_by_name(group_name))

element_ids = StructuralGroup.get_elements_by_name(group_name)
elem_to_sect = _get_element_to_section_map(element_ids)
print("Element → Section map:", elem_to_sect)

rows = get_section_properties()
print("Num section rows:", len(rows))
print("Sample first row:", rows[0] if rows else None)

from core.wind_load.compute_section_exposures import compute_section_exposures

exposures_df = compute_section_exposures(
    rows,
    extra_exposure_y_default=0.0,
    extra_exposure_y_by_id=None,
    as_dataframe=True,
)

print(exposures_df.head())
print("Columns:", list(exposures_df.columns))


from core.wind_load.beam_load import build_beam_load_plan_for_group
print("\n--- SECTION ASSIGNMENTS ---")
print("Total elements in group:", len(element_ids))
print("Total elements with a section_id:", len(elem_to_sect))
for i, eid in enumerate(element_ids[:10]):
    print(f"elem {eid} -> sect {elem_to_sect.get(eid)}")

all_elem_data = elements.get_all()
first_id = str(element_ids[0])
print("\nSample element record from /db/ELEM:")
print(first_id, all_elem_data.get(first_id))

sect_ids_from_elements = sorted(set(elem_to_sect.values()))
sect_ids_from_exposures = sorted(exposures_df.index.tolist())

print("\n--- SECTION IDS ---")
print("Section IDs from elements:", sect_ids_from_elements[:20])
print("Exposure table index IDs:", sect_ids_from_exposures[:20])

plan_df = build_beam_load_plan_for_group(
    group_name=group_name,
    load_case_name="Wind Load Check",
    pressure=0.8,
    extra_exposure_y_default=0.0,
    extra_exposure_y_by_id=None,
    exposure_axis="y",
    udl_direction="GZ",
    load_group_name="WIND",
)

print("\n=== PLAN DF ===")
print(plan_df)

print("\nRows:", len(plan_df))
if not plan_df.empty:
    print("\nColumns:", list(plan_df.columns))
    print("\nSample row 0:")
    print(plan_df.iloc[0])

    # numerical self-check
    bad_rows = plan_df[
        (plan_df["line_load"].round(6) != (plan_df["pressure"] * plan_df["exposure_depth"]).round(6))
    ]
    print("\nLine load consistency issues:", len(bad_rows))
    if not bad_rows.empty:
        print(bad_rows.head())

    # coverage check
    element_ids = StructuralGroup.get_elements_by_name(group_name)
    planned_eids = set(plan_df["element_id"].tolist())
    missed_eids = [eid for eid in element_ids if eid not in planned_eids]
    print("\nElements in group:", len(element_ids))
    print("Elements with loads planned:", len(planned_eids))
    print("Elements skipped:", len(missed_eids))
    if missed_eids:
        print("Skipped element IDs:", missed_eids[:20], "...")
else:
    print("No loads planned. Plan is empty.")

apply_wind_load_to_midas_for_group(
    group_name="Deck Elements",
    load_case_name="Wind Load Check",
    pressure=0.8,
    load_group_name="Wind Load Check",
)
