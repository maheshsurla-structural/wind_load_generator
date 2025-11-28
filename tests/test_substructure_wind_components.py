# tests/test_substructure_wind_components.py

import math
import pandas as pd
import pytest

from core.wind_load.substructure_wind_loads import (
    build_substructure_wind_components_table,
)


def test_substructure_components_angle_and_quadrant_q1():
    """
    Simple sanity check for θ = 15°, Q1.
    Q1: (Y+, Z+) so we expect cos/sin components both positive.
    """
    group_name = "Pier 1_Pier"

    # Fake WS cases: 1 row, Q1
    ws_cases_df = pd.DataFrame(
        [
            {
                "Case": "Strength III",
                "Angle": 15.0,          # degrees from local +Y toward +Z
                "Value": "WS_ULS_III_Ang_15_Q1",  # final LC name
            }
        ]
    )

    # Fake pressure table
    wind_pressures_df = pd.DataFrame(
        [
            {
                "Group": group_name,
                "Load Case": "Strength III",
                "Pz (ksf)": 1.0,  # magnitude
            }
        ]
    )

    components = build_substructure_wind_components_table(
        group_name=group_name,
        ws_cases_df=ws_cases_df,
        wind_pressures_df=wind_pressures_df,
    )

    assert len(components) == 1
    row = components.iloc[0]

    # Expected base components
    P = 1.0
    theta = math.radians(15.0)
    expected_y = P * math.cos(theta)
    expected_z = P * math.sin(theta)

    assert row["load_case"] == "WS_ULS_III_Ang_15_Q1"
    assert row["P"] == pytest.approx(P)
    assert row["p_local_y"] == pytest.approx(expected_y, rel=1e-6)
    assert row["p_local_z"] == pytest.approx(expected_z, rel=1e-6)


def test_substructure_components_quadrant_flips_q2():
    """
    Check that Q2 flips the Z component only, consistent with _apply_quadrant_signs:

        Q2: (T+, L-) → (Y+, Z-)
    """
    import pytest

    group_name = "Pier_1"

    ws_cases_df = pd.DataFrame(
        [
            {
                "Case": "Strength III",
                "Angle": 30.0,
                "Value": "WS_ULS_III_Ang_30_Q2",  # note Q2
            }
        ]
    )

    wind_pressures_df = pd.DataFrame(
        [
            {
                "Group": group_name,
                "Load Case": "Strength III",
                "Pz (ksf)": 2.0,
            }
        ]
    )

    components = build_substructure_wind_components_table(
        group_name=group_name,
        ws_cases_df=ws_cases_df,
        wind_pressures_df=wind_pressures_df,
    )

    assert len(components) == 1
    row = components.iloc[0]

    P = 2.0
    theta = math.radians(30.0)
    base_y = P * math.cos(theta)
    base_z = P * math.sin(theta)

    # Q2: Y+ (same), Z- (sign flipped)
    expected_y = base_y
    expected_z = -base_z

    assert row["p_local_y"] == pytest.approx(expected_y, rel=1e-6)
    assert row["p_local_z"] == pytest.approx(expected_z, rel=1e-6)
