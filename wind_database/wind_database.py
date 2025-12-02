# wind_database/wind_database.py

import math
import pandas as pd
from typing import Optional, List

LOAD_CASES = ["Strength III", "Strength V", "Service I", "Service IV"]


class WindDatabase:

    def __init__(self):
        # Structural groups and their parameters (wind speed, exposure, etc.)
        self.structural_groups = {}

        # Pier frame configuration (filled from classification / UI)
        # list[PierFrameDef] or list[dict]
        self.pier_frames: List[object] = []              # <-- NEW

        # Tabular storage for calculations and cases
        self.wind_pressures = pd.DataFrame(columns=[
            "Group", "Load Case", "Gust Wind Speed", "Kz", "G", "Cd", "Pz (ksf)"
        ])
        self.ws_cases = pd.DataFrame(columns=["Group", "Case", "Details"])
        self.wl_cases = pd.DataFrame(columns=["Group", "Case", "Details"])

    # ---------------------------
    # Structural Groups
    # ---------------------------
    def add_structural_group(self, name: str, parameters: dict):
        """Add or update a structural group with its parameters."""
        self.structural_groups[name] = parameters

    def get_structural_group(self, name: str):
        """Retrieve parameters of a specific structural group."""
        return self.structural_groups.get(name)

    def list_structural_groups(self):
        """Return all group names."""
        return list(self.structural_groups.keys())

    # ---------------------------
    # Wind Pressures
    # ---------------------------
    def update_wind_pressures(self):
        """Recalculate wind pressures for all structural groups and update DataFrame."""
        rows = []
        for group, params in self.structural_groups.items():
            wind_speed = float(params["Wind Speed"])
            exposure = params["Exposure Category"]
            height = float(params["Structure Height"])
            gust_factor = float(params["Gust Factor"])
            cd = float(params["Drag Coefficient"])

            gust_speeds = {
                "Strength III": wind_speed,
                "Strength V": 80.0,
                "Service I": 70.0,
                "Service IV": 0.75 * wind_speed
            }

            kz_values = {
                case: self.calculate_kz(exposure, height) if case in ["Strength III", "Service IV"] else 1.0
                for case in gust_speeds
            }

            g_values = {
                case: gust_factor if case in ["Strength III", "Service IV"] else 1.0
                for case in gust_speeds
            }

            for case in gust_speeds:
                pz = 2.56e-6 * (gust_speeds[case] ** 2) * kz_values[case] * g_values[case] * cd
                rows.append({
                    "Group": group,
                    "Load Case": case,
                    "Gust Wind Speed": gust_speeds[case],
                    "Kz": kz_values[case],
                    "G": g_values[case],
                    "Cd": cd,
                    "Pz (ksf)": round(pz, 5)
                })

        self.wind_pressures = pd.DataFrame(rows)

    def calculate_kz(self, exposure_category: str, height: float):
        """Calculate Kz using AASHTO LRFD formulas."""
        if height <= 0:
            raise ValueError("Structure height must be > 0")

        params = {
            "B": {"Z0": 0.9834, "C": 6.87, "D": 345.6},
            "C": {"Z0": 0.0984, "C": 7.35, "D": 478.4},
            "D": {"Z0": 0.0164, "C": 7.65, "D": 616.1}
        }

        if exposure_category not in params:
            raise ValueError(f"Invalid exposure category: {exposure_category}")

        p = params[exposure_category]
        kz = ((2.5 * math.log(height / p["Z0"]) + p["C"]) ** 2) / p["D"]
        return round(kz, 4)

    # ---------------------------
    # WS & WL Cases (No Groups)
    # ---------------------------
    def add_ws_case(self, case: str, details: dict):
        """Add a Wind on Structure (WS) case."""
        self.ws_cases = pd.concat([
            self.ws_cases,
            pd.DataFrame([{"Case": case, "Details": details}])
        ], ignore_index=True)

    def add_wl_case(self, case: str, details: dict):
        """Add a Wind on Live Load (WL) case."""
        self.wl_cases = pd.concat([
            self.wl_cases,
            pd.DataFrame([{"Case": case, "Details": details}])
        ], ignore_index=True)

    # ---------------------------
    # Accessor
    # ---------------------------
    def get_data(self):
        """Retrieve all stored data as a dict of dicts/DataFrames."""
        return {
            "Structural Groups": self.structural_groups,
            "Wind Pressures": self.wind_pressures,
            "WS Cases": self.ws_cases,
            "WL Cases": self.wl_cases
        }

    # ---------------------------
    # Pier frame lookup
    # ---------------------------
    def get_pier_reference_for_group(self, group_name: str) -> Optional[str]:
        """
        Given a structural group name (pier, pier cap, or above-deck),
        return the pier group whose local axes should be used as reference.

        Uses self.pier_frames, which is a list of PierFrameDef (or dicts
        with pier_group / cap_group / above_group).
        """
        frames = self.pier_frames or []

        for pf in frames:
            # Allow both dataclass and plain dict
            if hasattr(pf, "pier_group"):
                pier_group  = pf.pier_group
                cap_group   = pf.cap_group
                above_group = pf.above_group
            elif isinstance(pf, dict):
                pier_group  = pf.get("pier_group")
                cap_group   = pf.get("cap_group")
                above_group = pf.get("above_group")
            else:
                continue

            if not pier_group:
                continue

            if group_name == pier_group:
                return pier_group
            if cap_group and group_name == cap_group:
                return pier_group
            if above_group and group_name == above_group:
                return pier_group

        # No mapping found
        return None


wind_db = WindDatabase()
