# tests/run_substructure_wind_demo.py

"""
Hard-coded demo for substructure wind loads.

This bypasses wind_db completely and uses the same simple data
as your unit tests, so you can verify that:

    - components are computed correctly
    - a beam-load plan is built
    - loads are actually written to MIDAS

Once this works, we can plug real wind_db tables back in.
"""

import math
import pandas as pd

from core.wind_load.substructure_wind_loads import (
    build_substructure_wind_components_table,
    build_substructure_wind_beam_load_plan_for_group,
    apply_substructure_wind_loads_to_group,
)
from core.wind_load.debug_utils import summarize_plan


TEST_STRUCT_GROUP = "Pier 1_Pier"          # real group in your model
TEST_LOAD_BOUNDARY_GROUP = "WS_ULS_III_Ang_15_Q1"
APPLY_TO_MIDAS = True                      # send loads for real


def run_demo():
    group_name = TEST_STRUCT_GROUP

    # 1) Hard-code WS cases (same as first unit test)
    ws_cases_df = pd.DataFrame(
        [
            {
                "Case": "Strength III",
                "Angle": 15.0,
                "Value": "WS_ULS_III_Ang_15_Q1",
            }
        ]
    )
    print("\n[run_demo] WS cases for demo (synthetic):")
    print(ws_cases_df)

    # 2) Hard-code wind pressure table (same as unit test)
    wind_pressures_df = pd.DataFrame(
        [
            {
                "Group": group_name,
                "Load Case": "Strength III",
                "Pz (ksf)": 1.0,
            }
        ]
    )
    print("\n[run_demo] Wind pressures for demo (synthetic):")
    print(wind_pressures_df)

    # 3) Build components from the synthetic tables
    components_df = build_substructure_wind_components_table(
        group_name=group_name,
        ws_cases_df=ws_cases_df,
        wind_pressures_df=wind_pressures_df,
    )

    print("\n[run_demo] Substructure WS components:")
    print(components_df)

    if components_df.empty:
        print("[run_demo] No components built – something is wrong with the math.")
        return

    # 4) Override load_group to your boundary group
    components_df = components_df.copy()
    components_df["load_group"] = TEST_LOAD_BOUNDARY_GROUP

    # 5) Build the beam-load plan (LY + LZ)
    plan_df = build_substructure_wind_beam_load_plan_for_group(
        group_name=group_name,
        components_df=components_df,
        extra_exposure_y_default=0.0,
        extra_exposure_y_by_id=None,
    )

    print("\n[run_demo] Beam-load plan (first 20 rows):")
    print(plan_df.head(20))

    if plan_df.empty:
        print(
            "[run_demo] Plan is empty – maybe group has no elements or exposures?"
        )
        return

    summarize_plan(
        plan_df,
        label=f"WS_SUB_DEMO_{group_name}",
        dump_csv_per_case=False,
        write_log=True,
    )

    # 6) Actually send loads to MIDAS
    if APPLY_TO_MIDAS:
        print("\n[run_demo] APPLY_TO_MIDAS = True → sending loads to MIDAS...")
        apply_substructure_wind_loads_to_group(
            group_name=group_name,
            components_df=components_df,
            extra_exposure_y_default=0.0,
            extra_exposure_y_by_id=None,
        )
    else:
        print("\n[run_demo] APPLY_TO_MIDAS = False → preview only (no loads sent).")


if __name__ == "__main__":
    run_demo()
