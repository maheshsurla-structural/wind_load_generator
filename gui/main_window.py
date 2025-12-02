# gui/main_window.py
from __future__ import annotations
from typing import List, Optional

from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar, QWidget, QVBoxLayout,
    QHBoxLayout, QGroupBox, QPushButton, QComboBox, QLabel
)
from PySide6.QtGui import QAction

from unit_manager import get_unit_manager
from unit_manager.converter import convert_length

from core.app_bus import get_app_bus
from core.worker import Worker
from core.thread_pool import run_in_thread
from services.persistence import ConfigManager
from wind_database import wind_db

from gui.widgets.wind_parameters import WindParameters
from gui.widgets.pressure_table import PressureTable

from gui.dialogs.control_data.models import ControlDataModel
from gui.dialogs.control_data import ControlData
from gui.dialogs.pier_frame_config import PierFrameConfigDialog, PierFrameDef


from gui.dialogs.wind_load_input import WindLoadInput
from gui.dialogs.wind_load_cases import WindLoadCases

from midas.resources.structural_group import StructuralGroup

from core.wind_load.beam_load import apply_beam_load_plan_to_midas

from core.wind_load.live_wind_loads import (
    build_live_wind_components_table,
    apply_live_wind_loads_to_group,
    build_live_wind_beam_load_plan_for_group,   # NEW
)

from core.wind_load.structural_wind_loads import (
    build_structural_wind_components_table,
    apply_structural_wind_loads_to_group,
    build_structural_wind_beam_load_plan_for_group,   # NEW
)

from core.wind_load.substructure_wind_loads import (
    build_substructure_wind_components_table,
    apply_substructure_wind_loads_to_group,
)


import pandas as pd
from PySide6.QtWidgets import QMessageBox  # already imported in some files


class MainWindow(QMainWindow):

    def __init__(self) -> None:

        super().__init__()
        
        self.setWindowTitle("Wind Load Generator AASHTO")

        # ---- Core systems ----
        self.units = get_unit_manager()
        self.bus = get_app_bus()
        self.config = ConfigManager()

        # ---- Central UI ----
        central_widget = QWidget()
        main_layout  = QVBoxLayout(central_widget)
        self.setCentralWidget(central_widget)

        # Wind parameters (imported from widgets/wind_parameters.py)
        self.wind_parameters = WindParameters(self)
        main_layout .addWidget(self.wind_parameters)

        # Structural actions
        actions_group = QGroupBox("Structural Group Classification And Wind Data")
        actions = QHBoxLayout(actions_group)

        self.btn_generate = QPushButton("Generate Wind Data")
        self.btn_edit     = QPushButton("Edit Wind Data")
        self.btn_pier_frames = QPushButton("Pier Frames...")

        actions.addWidget(self.btn_generate)
        actions.addWidget(self.btn_edit)
        actions.addWidget(self.btn_pier_frames)               
        main_layout .addWidget(actions_group)

        # Pressure table (imported from widgets/pressure_table.py)
        self.pressure = PressureTable(self)
        main_layout .addWidget(self.pressure)

        # Wind load cases
        wlc_group = QGroupBox("Wind Load Cases")
        wlc_lay = QHBoxLayout(wlc_group)

        self.btn_pair = QPushButton("Pair Wind Load Cases")
        wlc_lay.addWidget(self.btn_pair)

        self.btn_assign_wind_loads = QPushButton("Assign Wind Loads")
        wlc_lay.addWidget(self.btn_assign_wind_loads)

        main_layout .addWidget(wlc_group)

        # Toolbar
        tb = QToolBar(movable=False)
        self.addToolBar(tb)
        act_control = QAction("Control Data", self)
        tb.addAction(act_control)


        # ---- Connections ----
        act_control.triggered.connect(self.open_control_data)
        self.btn_edit.clicked.connect(self.open_wind_load_input)
        self.btn_pier_frames.clicked.connect(self.open_pier_frames)
        self.btn_pair.clicked.connect(self.open_pair_wind_load_cases)
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        self.btn_assign_wind_loads.clicked.connect(self._on_assign_wind_loads_clicked)

        # Global events
        self.bus.progressStarted.connect(self._on_progress_started)
        self.bus.progressFinished.connect(self._on_progress_finished)
        self.bus.windGroupsUpdated.connect(self._on_wind_groups_updated)

        # ---- Restore persisted state ----
        payload = self.config.load_control_data()

        # First, restore app unit selectors from persisted units
        self._restore_units_from_config(payload)

        # Status bar + unit selectors
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._setup_unit_selectors(sb)

        # Now build a live model from disk
        self.control_model = ControlDataModel.from_dict(payload)

        # Keep model units aligned with the (now restored) UnitManager
        self.control_model.length_unit = self.units.length
        self.control_model.force_unit = self.units.force

        # populate initial pressure groups (if any)
        self.pressure.populate_groups()
        self.pressure.refresh()


    # ---------------- Event handlers ----------------

    def _on_generate_clicked(self) -> None:
        from core.analytical_model_classification import classify_elements

        # --- Capture everything on the main (UI) thread ---
        defaults = self.wind_parameters.values()
        pr       = self.control_model.geometry.pier_radius
        ui_len   = self.units.length.upper()
        sa       = self.control_model.naming.suffix_above
        base     = self.control_model.naming.pier_base_name
        loads    = self.control_model.loads
        naming   = self.control_model.naming

        def classify_with_params():
            return classify_elements(
                pier_radius=pr,
                length_unit=ui_len,
                suffix_above=sa,
                pier_base_name=base,
            )

        self.bus.progressStarted.emit("Generating wind data...")
        worker = Worker(
            self._run_classification_task,
            classify_with_params,
            defaults,
            naming,
            loads,
            ui_len,
            sa,
        )
        worker.signals.finished.connect(lambda _: self.bus.progressFinished.emit(True, "Wind data generated."))
        worker.signals.error.connect(lambda e: self.bus.progressFinished.emit(False, e))
        run_in_thread(worker)


    def _run_classification_task(
        self,
        run_classification,
        defaults,
        naming,
        loads,
        ui_length_unit,
        suffix_above,
    ):
        """
        Runs off the UI thread. Classifies, batches groups, one PUT to MIDAS,
        updates local DB and auto-builds pier frame configuration.
        """

        print("DEBUG: entering _run_classification_task")
        try:
            result = run_classification()
        except Exception as e:
            import traceback
            print("DEBUG: classify_elements() raised:")
            traceback.print_exc()
            raise

        # Coefficients from Control Data
        gust     = f"{loads.gust_factor:g}"
        cd_super = f"{loads.superstructure_drag_coefficient:g}"
        cd_sub   = f"{loads.substructure_drag_coefficient:g}"

        # --- Compute real Structure Height (deck Z - ground), unit-safe ---
        deck_ref   = result.get("deck_reference_height")
        model_unit = (result.get("model_unit") or "FT").upper()
        ground_ui  = float(self.control_model.geometry.reference_height or 0.0)

        if deck_ref is not None:
            try:
                ground_in_model = convert_length(
                    ground_ui,
                    from_sym=ui_length_unit,
                    to_sym=model_unit,
                )
            except ValueError:
                ground_in_model = ground_ui
            height = max(0.0, float(deck_ref) - ground_in_model)
            height_str = f"{height:g}"
        else:
            height_str = "0"

        # ---- collect groups for ONE PUT
        batch: list[tuple[str, list[int]]] = []

        # ================================================================
        # 1) Deck group (optional)
        # ================================================================
        deck_elements = result.get("deck_elements", {}) or {}
        if deck_elements:
            deck_ids = sorted({int(i) for i in deck_elements.keys()})
            if deck_ids:
                deck_group_name = f"{(naming.deck_name or 'Deck').strip()} Elements"
                batch.append((deck_group_name, deck_ids))

                # update local DB (app-side)
                wind_db.add_structural_group(
                    deck_group_name,
                    {
                        **defaults,
                        "Structure Height": height_str,
                        "Gust Factor": gust,
                        "Drag Coefficient": cd_super,   # superstructure Cd
                        "Member Type": "Deck",
                    },
                )

        # ================================================================
        # 2) Pier-related clusters (Pier / PierCap / Above-Deck)
        #    NOTE: classification into those buckets was already done
        #          geometrically in process_pier_clusters.
        # ================================================================
        pier_clusters = result.get("pier_clusters", {}) or {}

        for label, element_dict in pier_clusters.items():
            ids = sorted({int(i) for i in element_dict.keys()})
            if not ids:
                continue

            batch.append((label, ids))

            # Member Type only affects how we treat the group later.
            if label.endswith("_PierCap"):
                member_type = "Pier Cap"
            elif suffix_above and label.endswith(suffix_above):
                member_type = "Substructure – Above Deck"
            else:
                member_type = "Pier"

            wind_db.add_structural_group(
                label,
                {
                    **defaults,
                    "Structure Height": height_str,
                    "Gust Factor": gust,
                    # Every non-deck group uses the substructure Cd
                    "Drag Coefficient": cd_sub,
                    "Member Type": member_type,
                },
            )

        # ================================================================
        # 3) Single PUT to MIDAS for all structural groups
        # ================================================================
        if batch:
            try:
                print(f"Assigning {len(batch)} structural groups in one PUT...")
                StructuralGroup.bulk_upsert(batch)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to create/update structural groups in batch: {exc}"
                )

        # ================================================================
        # 4) Build PierFrameDef list from structured pier_frames
        #    result['pier_frames'] is expected to be a list of dicts:
        #      { 'pier_group': str, 'cap_group': str|None, 'above_group': str|None }
        # ================================================================
        raw_frames = result.get("pier_frames") or []

        auto_frames: List[PierFrameDef] = []
        for frame in raw_frames:
            pier_group = frame.get("pier_group")
            if not pier_group:
                # We need a pier group to define axes; skip otherwise
                continue

            auto_frames.append(
                PierFrameDef(
                    pier_group=pier_group,
                    cap_group=frame.get("cap_group") or None,
                    above_group=frame.get("above_group") or None,
                )
            )

        # Merge with any existing manual frames (auto overrides same pier)
        existing_frames = list(getattr(wind_db, "pier_frames", []) or [])
        by_pier = {pf.pier_group: pf for pf in existing_frames}
        for pf in auto_frames:
            by_pier[pf.pier_group] = pf

        wind_db.pier_frames = list(by_pier.values())

        # ================================================================
        # 5) Finish: compute pressures and notify UI
        # ================================================================
        wind_db.update_wind_pressures()
        self.bus.windGroupsUpdated.emit(wind_db.get_data())





    def _on_wind_groups_updated(self, _payload) -> None:
        """Refresh widgets that rely on wind_db data."""
        self.pressure.populate_groups()
        self.pressure.refresh()

    def _on_progress_started(self, msg: str) -> None:
        self.statusBar().showMessage(msg)

    def _on_progress_finished(self, ok: bool, msg: str) -> None:
        icon = "✅" if ok else "❌"
        self.statusBar().showMessage(f"{icon} {msg}", 4000)

    # ---------------- Dialogs ----------------

    def open_control_data(self) -> None:
        dlg = ControlData(self, units=self.units)
        dlg.set_payload(self.control_model.to_dict())     # seed current values
        dlg.controlDataChanged.connect(self._on_control_data_changed)
        dlg.exec()



    def open_wind_load_input(self) -> None:
        WindLoadInput(self).exec()

    def open_pair_wind_load_cases(self) -> None:
        naming = getattr(getattr(self, "control_model", None), "naming", None)
        naming = getattr(naming, "wind", None)
        dlg = WindLoadCases(self, naming=naming)
        dlg.exec()

    def open_pier_frames(self) -> None:
        """Open the Pier Frame configuration dialog."""
        dlg = PierFrameConfigDialog(self)   # no control_model passed
        dlg.exec()


    def _on_control_data_changed(self, model: ControlDataModel) -> None:
        self.control_model = model                        # keep live copy
        self.config.save_control_data(model.to_dict())    # persist
        self.statusBar().showMessage("Control data saved.", 3000)


    # ---------------- Helpers ----------------

    def _setup_unit_selectors(self, sb: QStatusBar) -> None:
        """Hook unit selectors to the global UnitManager."""
        force_combo = QComboBox()
        force_combo.addItems(["KGF", "TONF", "N", "KN", "LBF", "KIPS"])
        length_combo = QComboBox()
        length_combo.addItems(["MM", "CM", "M", "IN", "FT"])

        length_combo.setCurrentText(self.units.length)
        force_combo.setCurrentText(self.units.force)
        length_combo.currentTextChanged.connect(self.units.set_length)
        force_combo.currentTextChanged.connect(self.units.set_force)

        # --- persist unit changes immediately to disk (optional but recommended) ---
        length_combo.currentTextChanged.connect(
            lambda u: (
                setattr(self.control_model, "length_unit", u),
                self.config.save_control_data(self.control_model.to_dict())
            ) if hasattr(self, "control_model") else None
        )
        force_combo.currentTextChanged.connect(
            lambda u: (
                setattr(self.control_model, "force_unit", u),
                self.config.save_control_data(self.control_model.to_dict())
            ) if hasattr(self, "control_model") else None
        )

        sb.addPermanentWidget(QLabel("Force:"))
        sb.addPermanentWidget(force_combo)
        sb.addPermanentWidget(QLabel("Length:"))
        sb.addPermanentWidget(length_combo)



    def _restore_units_from_config(self, payload: dict) -> None:
        """Apply persisted units (if present) to the UnitManager."""
        units_cfg = payload.get("units", {})
        if "length" in units_cfg:
            self.units.set_length(units_cfg["length"])
        if "force" in units_cfg:
            self.units.set_force(units_cfg["force"])


    # def _on_assign_wind_loads_clicked(self) -> None:
    #     """
    #     Assign LIVE wind (WL) and STRUCTURAL wind (WS) loads to the deck group.

    #     WL and WS are each delegated to their own helpers:
    #         - apply_live_wind_loads_to_group(...)
    #         - apply_structural_wind_loads_to_group(...)

    #     Those helpers are responsible for:
    #         - building the beam-load plan
    #         - running debug summaries / CSV dumps
    #         - sending the loads to MIDAS via apply_beam_load_plan_to_midas()
    #     """
    #     try:
    #         # ----------------- Resolve deck group name -----------------
    #         naming = getattr(self.control_model, "naming", None)
    #         base_deck_name = getattr(naming, "deck_name", None) or "Deck"
    #         deck_group_name = f"{base_deck_name.strip()} Elements"

    #         # Quick sanity check: does the group exist and have elements?
    #         try:
    #             from midas.resources.structural_group import StructuralGroup
    #             deck_elements = StructuralGroup.get_elements_by_name(deck_group_name)
    #             if not deck_elements:
    #                 QMessageBox.warning(
    #                     self,
    #                     "Deck Group Not Found",
    #                     f"The structural group '{deck_group_name}' has no elements.\n"
    #                     "Please generate wind data first, then try again.",
    #                 )
    #                 return
    #         except Exception:
    #             # If the API call itself fails, we still try to proceed and let
    #             # downstream code report a more detailed error.
    #             deck_elements = []

    #         wl_applied = False
    #         ws_applied = False

    #         # ============================================================
    #         # 1) LIVE WIND (WL)
    #         # ============================================================
    #         wl = self.control_model.loads.wind_live  # WindLiveLoadCoefficients

    #         wl_df = getattr(wind_db, "wl_cases", None)
    #         if wl_df is None:
    #             wl_df = pd.DataFrame()

    #         live_components_df = build_live_wind_components_table(
    #             angles=wl.angles,
    #             transverse=wl.transverse,
    #             longitudinal=wl.longitudinal,
    #             wl_cases_df=wl_df,
    #         )

    #         if live_components_df is not None and not live_components_df.empty:
    #             apply_live_wind_loads_to_group(deck_group_name, live_components_df)
    #             wl_applied = True
    #         else:
    #             print(
    #                 f"[_on_assign_wind_loads_clicked] "
    #                 f"No LIVE wind components for '{deck_group_name}'."
    #             )

    #         # ============================================================
    #         # 2) STRUCTURAL WIND (WS)
    #         # ============================================================
    #         if wind_db.wind_pressures.empty:
    #             # We do NOT bail out entirely: WL may already have been applied.
    #             QMessageBox.warning(
    #                 self,
    #                 "Wind Pressures Missing",
    #                 "Wind pressures have not been generated yet.\n"
    #                 "Click 'Generate Wind Data' before assigning structural wind loads.",
    #             )
    #         else:
    #             skew = self.control_model.loads.skew  # SkewCoefficients
    #             raw_ws_df = getattr(wind_db, "ws_cases", None)
    #             if raw_ws_df is None:
    #                 raw_ws_df = pd.DataFrame()

    #             if {"Case", "Angle", "Value"}.issubset(set(raw_ws_df.columns)):
    #                 ws_df = raw_ws_df
    #             else:
    #                 ws_df = pd.DataFrame(columns=["Case", "Angle", "Value"])

    #             ws_components_df = build_structural_wind_components_table(
    #                 group_name=deck_group_name,
    #                 angles=skew.angles,
    #                 transverse=skew.transverse,
    #                 longitudinal=skew.longitudinal,
    #                 ws_cases_df=ws_df,
    #                 wind_pressures_df=wind_db.wind_pressures,
    #             )

    #             if ws_components_df is not None and not ws_components_df.empty:
    #                 apply_structural_wind_loads_to_group(
    #                     group_name=deck_group_name,
    #                     components_df=ws_components_df,
    #                     exposure_axis="y",   # local depth is Y
    #                 )
    #                 ws_applied = True
    #             else:
    #                 print(
    #                     f"[_on_assign_wind_loads_clicked] "
    #                     f"No STRUCTURAL wind components for '{deck_group_name}'."
    #                 )

    #         # ============================================================
    #         # 3) Final status message
    #         # ============================================================
    #         if wl_applied and ws_applied:
    #             msg = "Live wind (WL) and structural wind (WS) loads assigned."
    #         elif wl_applied:
    #             msg = "Live wind (WL) loads assigned. WS was skipped."
    #         elif ws_applied:
    #             msg = "Structural wind (WS) loads assigned. WL was skipped."
    #         else:
    #             msg = "No wind loads were assigned (no WL/WS components)."

    #         print(f"[_on_assign_wind_loads_clicked] {msg}")
    #         self.statusBar().showMessage(msg, 4000)

    #     except Exception as exc:
    #         print("Error assigning wind loads:", exc)
    #         QMessageBox.critical(
    #             self,
    #             "Error",
    #             f"An error occurred while assigning wind loads:\n{exc}",
    #         )


    def _on_assign_wind_loads_clicked(self) -> None:
        """
        Assign LIVE wind (WL) and STRUCTURAL wind (WS) loads.

        New rules (member-type based):

            - For every structural group with Member Type = 'Deck':
                  → apply LIVE wind (WL)  + WS using deck formulas

            - For every structural group with Member Type = 'Pier':
                  → apply WS using substructure (pier) formulas (no WL)
        """
        try:
            # ============================================================
            # 0) Get structural groups from DB (for Member Type)
            # ============================================================
            try:
                groups_raw = getattr(wind_db, "structural_groups", None)
            except Exception:
                groups_raw = None

            # wind_db.structural_groups is a dict: {group_name: params_dict}
            if not groups_raw:
                QMessageBox.warning(
                    self,
                    "No Structural Groups",
                    "No structural groups found in the wind database.\n"
                    "Generate or edit wind data, then try again.",
                )
                return

            if isinstance(groups_raw, dict):
                # Convert dict → DataFrame with 'Group' column
                rows = []
                for name, params in groups_raw.items():
                    params = params or {}
                    row = {"Group": name}
                    row.update(params)
                    rows.append(row)
                groups_df = pd.DataFrame(rows)
            else:
                # If at some point you change it to already be a DataFrame
                groups_df = groups_raw

            if groups_df is None or groups_df.empty:
                QMessageBox.warning(
                    self,
                    "No Structural Groups",
                    "No structural groups found in the wind database.\n"
                    "Generate or edit wind data, then try again.",
                )
                return

            if "Group" not in groups_df.columns:
                QMessageBox.critical(
                    self,
                    "Invalid Structural Groups Table",
                    "The structural_groups table must contain a 'Group' column.",
                )
                return

            # If Member Type is missing for some rows, treat as Deck by default
            if "Member Type" not in groups_df.columns:
                groups_df["Member Type"] = "Deck"

            # Separate groups by member type
            deck_groups = (
                groups_df.loc[groups_df["Member Type"] == "Deck", "Group"]
                .dropna()
                .unique()
            )
            pier_groups = (
                groups_df.loc[groups_df["Member Type"] == "Pier", "Group"]
                .dropna()
                .unique()
            )

            wl_applied_any = False
            ws_deck_any    = False
            ws_pier_any    = False

            # ============================================================
            # 1) Get global WL / WS definitions (same for all groups)
            # ============================================================
            wl = self.control_model.loads.wind_live   # WL coefficients
            skew = self.control_model.loads.skew      # WS skew coefficients

            # WL cases table
            wl_df = getattr(wind_db, "wl_cases", None)
            if wl_df is None:
                wl_df = pd.DataFrame()

            # WS cases table
            raw_ws_df = getattr(wind_db, "ws_cases", None)
            if raw_ws_df is None:
                raw_ws_df = pd.DataFrame()

            if {"Case", "Angle", "Value"}.issubset(set(raw_ws_df.columns)):
                ws_df = raw_ws_df
            else:
                ws_df = pd.DataFrame(columns=["Case", "Angle", "Value"])

            # Need pressures for all WS operations
            if wind_db.wind_pressures.empty:
                QMessageBox.warning(
                    self,
                    "Wind Pressures Missing",
                    "Wind pressures have not been generated yet.\n"
                    "Click 'Generate Wind Data' before assigning structural wind loads.",
                )
                # We still allow WL-on-deck to proceed.
                allow_ws = False
            else:
                allow_ws = True

            # ============================================================
            # 2) For each DECK group: WL + WS (deck)
            # ============================================================
            for group_name in deck_groups:
                group_name = str(group_name).strip()
                if not group_name:
                    continue

                # Sanity check: does group have any elements in MIDAS?
                try:
                    from midas.resources.structural_group import StructuralGroup
                    elem_ids = StructuralGroup.get_elements_by_name(group_name)
                except Exception:
                    elem_ids = []

                if not elem_ids:
                    print(
                        f"[_on_assign_wind_loads_clicked] "
                        f"Deck group '{group_name}' has no elements in MIDAS; skipping."
                    )
                    continue

                # ---------- 2a) LIVE WIND (WL) on this deck group ----------
                live_components_df = build_live_wind_components_table(
                    angles=wl.angles,
                    transverse=wl.transverse,
                    longitudinal=wl.longitudinal,
                    wl_cases_df=wl_df,
                )

                if live_components_df is not None and not live_components_df.empty:
                    apply_live_wind_loads_to_group(group_name, live_components_df)
                    wl_applied_any = True
                    print(f"[WL] Applied live wind to deck group '{group_name}'.")
                else:
                    print(
                        f"[_on_assign_wind_loads_clicked] "
                        f"No LIVE wind components for deck group '{group_name}'."
                    )

                # ---------- 2b) STRUCTURAL WIND (WS) – deck formulas ------
                if allow_ws:
                    ws_components_deck = build_structural_wind_components_table(
                        group_name=group_name,
                        angles=skew.angles,
                        transverse=skew.transverse,
                        longitudinal=skew.longitudinal,
                        ws_cases_df=ws_df,
                        wind_pressures_df=wind_db.wind_pressures,
                    )

                    if ws_components_deck is not None and not ws_components_deck.empty:
                        apply_structural_wind_loads_to_group(
                            group_name=group_name,
                            components_df=ws_components_deck,
                            exposure_axis="y",   # depth = local Y
                        )
                        ws_deck_any = True
                        print(f"[WS_DECK] Applied structural wind to deck group '{group_name}'.")
                    else:
                        print(
                            f"[_on_assign_wind_loads_clicked] "
                            f"No STRUCTURAL wind components for deck group '{group_name}'."
                        )

            # ============================================================
            # 3) For each PIER group: WS using substructure formulas
            # ============================================================
            if allow_ws:
                for group_name in pier_groups:
                    group_name = str(group_name).strip()
                    if not group_name:
                        continue

                    sub_components_df = build_substructure_wind_components_table(
                        group_name=group_name,
                        ws_cases_df=ws_df,
                        wind_pressures_df=wind_db.wind_pressures,
                    )

                    if sub_components_df is None or sub_components_df.empty:
                        print(
                            f"[WS_PIER] No components for pier group '{group_name}'."
                        )
                        continue

                    apply_substructure_wind_loads_to_group(
                        group_name=group_name,
                        components_df=sub_components_df,
                        extra_exposure_y_default=0.0,
                        extra_exposure_y_by_id=None,
                    )
                    ws_pier_any = True
                    print(f"[WS_PIER] Applied structural wind to pier group '{group_name}'.")

            # ============================================================
            # 4) Final status message
            # ============================================================
            if wl_applied_any and (ws_deck_any or ws_pier_any):
                msg = "WL applied to deck groups; WS applied to deck and/or pier groups."
            elif wl_applied_any:
                msg = "Live wind (WL) loads assigned to deck groups. WS was skipped."
            elif ws_deck_any or ws_pier_any:
                msg = "Structural wind (WS) loads assigned to deck and/or pier groups."
            else:
                msg = "No wind loads were assigned (no WL/WS components)."

            print(f"[_on_assign_wind_loads_clicked] {msg}")
            self.statusBar().showMessage(msg, 4000)

        except Exception as exc:
            print("Error assigning wind loads:", exc)
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while assigning wind loads:\n{exc}",
            )

