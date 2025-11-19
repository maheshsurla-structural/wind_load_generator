# gui/main_window.py
from __future__ import annotations

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
        actions_group = QGroupBox("Structural Group Classification & Wind Data")
        actions = QHBoxLayout(actions_group)
        self.btn_generate = QPushButton("Generate Wind Data")
        self.btn_edit     = QPushButton("Edit Wind Data")
        actions.addWidget(self.btn_generate)
        actions.addWidget(self.btn_edit)
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
        )
        worker.signals.finished.connect(lambda _: self.bus.progressFinished.emit(True, "Wind data generated."))
        worker.signals.error.connect(lambda e: self.bus.progressFinished.emit(False, e))
        run_in_thread(worker)


    def _run_classification_task(self, run_classification, defaults, naming, loads, ui_length_unit):
        """Runs off the UI thread. Classifies, batches groups, one PUT to MIDAS, updates local DB."""

        print("DEBUG: entering _run_classification_task")
        try:
            result = run_classification()
        except Exception as e:
            import traceback
            print("DEBUG: classify_elements() raised:")
            traceback.print_exc()
            raise

        # Coefficients
        gust = f"{loads.gust_factor:g}"
        cd   = f"{loads.drag_coefficient:g}"

        # --- Compute real Structure Height (deck Z - ground), unit-safe ---
        deck_ref   = result.get("deck_reference_height")
        model_unit = (result.get("model_unit") or "FT").upper()
        ground_ui  = float(self.control_model.geometry.reference_height or 0.0)

        if deck_ref is not None:
            try:
                ground_in_model = convert_length(ground_ui, from_sym=ui_length_unit, to_sym=model_unit)
            except ValueError:
                ground_in_model = ground_ui
            height = max(0.0, float(deck_ref) - ground_in_model)
            height_str = f"{height:g}"
        else:
            height_str = "0"

        # ---- collect groups for ONE PUT
        batch: list[tuple[str, list[int]]] = []

        # Deck group (optional)
        deck_elements = result.get("deck_elements", {})
        if deck_elements:
            deck_ids = sorted({int(i) for i in deck_elements.keys()})
            if deck_ids:
                deck_group_name = f"{(naming.deck_name or 'Deck').strip()} Elements"
                batch.append((deck_group_name, deck_ids))
                # update local DB (app-side)
                wind_db.add_structural_group(deck_group_name, {
                    **defaults,
                    "Structure Height": height_str,
                    "Gust Factor": gust,
                    "Drag Coefficient": cd,
                    "Member Type": "Girders",
                })

        # Pier clusters
        for label, element_dict in result.get("pier_clusters", {}).items():
            ids = sorted({int(i) for i in element_dict.keys()})
            if not ids:
                continue
            batch.append((label, ids))
            # update local DB (app-side)
            wind_db.add_structural_group(label, {
                **defaults,
                "Structure Height": height_str,
                "Gust Factor": gust,
                "Drag Coefficient": cd,
                "Member Type": "Trusses, Columns, and Arches",
            })

        # ---- single PUT to MIDAS
        if batch:
            try:
                print(f"Assigning {len(batch)} structural groups in one PUT...")
                StructuralGroup.bulk_upsert(batch)
            except Exception as exc:
                raise RuntimeError(f"Failed to create/update structural groups in batch: {exc}")

        # Finish: compute pressures and notify UI
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


    def _on_assign_wind_loads_clicked(self) -> None:
        """Assign LIVE wind (WL) and STRUCTURAL wind (WS) loads to the deck group."""
        try:
            # ----------------- Resolve deck group name -----------------
            naming = getattr(self.control_model, "naming", None)
            base_deck_name = getattr(naming, "deck_name", None) or "Deck"
            deck_group_name = f"{base_deck_name.strip()} Elements"

            plans: list[pd.DataFrame] = []

            # ============================================================
            # 1) LIVE WIND (WL)
            # ============================================================
            wl = self.control_model.loads.wind_live  # WindLiveLoadCoefficients

            wl_df = getattr(wind_db, "wl_cases", None)
            if wl_df is None:
                wl_df = pd.DataFrame()

            live_components_df = build_live_wind_components_table(
                angles=wl.angles,
                transverse=wl.transverse,
                longitudinal=wl.longitudinal,
                wl_cases_df=wl_df,
            )

            if live_components_df is not None and not live_components_df.empty:
                wl_plan = build_live_wind_beam_load_plan_for_group(
                    deck_group_name, live_components_df
                )
                if wl_plan is not None and not wl_plan.empty:
                    plans.append(wl_plan)
            else:
                print(
                    f"[_on_assign_wind_loads_clicked] "
                    f"No LIVE wind components for '{deck_group_name}'."
                )

            # ============================================================
            # 2) STRUCTURAL WIND (WS)
            # ============================================================
            if wind_db.wind_pressures.empty:
                QMessageBox.warning(
                    self,
                    "Wind Pressures Missing",
                    "Wind pressures have not been generated yet.\n"
                    "Please click 'Generate Wind Data' before assigning structural wind loads.",
                )
                # We still allow WL plan (if any) to be applied below.
            else:
                skew = self.control_model.loads.skew  # SkewCoefficients
                raw_ws_df = getattr(wind_db, "ws_cases", None)
                if raw_ws_df is None:
                    raw_ws_df = pd.DataFrame()

                if {"Case", "Angle", "Value"}.issubset(set(raw_ws_df.columns)):
                    ws_df = raw_ws_df
                else:
                    ws_df = pd.DataFrame(columns=["Case", "Angle", "Value"])

                ws_components_df = build_structural_wind_components_table(
                    group_name=deck_group_name,
                    angles=skew.angles,
                    transverse=skew.transverse,
                    longitudinal=skew.longitudinal,
                    ws_cases_df=ws_df,
                    wind_pressures_df=wind_db.wind_pressures,
                )

                if ws_components_df is not None and not ws_components_df.empty:
                    ws_plan = build_structural_wind_beam_load_plan_for_group(
                        group_name=deck_group_name,
                        components_df=ws_components_df,
                        exposure_axis="y",   # local depth is Y
                    )
                    if ws_plan is not None and not ws_plan.empty:
                        plans.append(ws_plan)
                else:
                    print(
                        f"[_on_assign_wind_loads_clicked] "
                        f"No WS components for '{deck_group_name}'."
                    )

            # ============================================================
            # 3) COMBINE & APPLY
            # ============================================================
            if not plans:
                print("[_on_assign_wind_loads_clicked] No WL or WS loads to apply.")
                return

            combined_plan = pd.concat(plans, ignore_index=True)
            combined_plan.sort_values(["load_case", "element_id"], inplace=True)
            combined_plan.reset_index(drop=True, inplace=True)

            print(
                f"[_on_assign_wind_loads_clicked] "
                f"Applying combined WL+WS plan ({len(combined_plan)} rows) "
                f"to '{deck_group_name}'"
            )

            apply_beam_load_plan_to_midas(combined_plan)
            self.statusBar().showMessage("Wind loads (WL + WS) assigned.", 4000)

        except Exception as exc:
            print("Error assigning wind loads:", exc)
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while assigning wind loads:\n{exc}",
            )

