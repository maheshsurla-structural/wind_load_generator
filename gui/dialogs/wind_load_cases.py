# gui/dialogs/pair_wind_load_cases.py
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Sequence

import pandas as pd
from PySide6.QtCore import (
    Qt,
    QAbstractTableModel,
    QModelIndex,
    Signal,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QSpinBox,
    QPushButton,
    QTableView,
    QGroupBox,
    QMessageBox,
    QHeaderView,
    QCheckBox,
)

from wind_database import wind_db, LOAD_CASES
from gui.dialogs.control_data.models import WindLoadNamingSettings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

@dataclass
class LoadCaseAssignment:
    case: str
    angle: int
    value: str


@dataclass
class PairWindLoadModel:
    ws_cases: List[LoadCaseAssignment] = field(default_factory=list)
    wl_cases: List[LoadCaseAssignment] = field(default_factory=list)

    def to_frames(self) -> Dict[str, pd.DataFrame]:
        return {
            "WS Cases": pd.DataFrame([asdict(a) for a in self.ws_cases]),
            "WL Cases": pd.DataFrame([asdict(a) for a in self.wl_cases]),
        }


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def _parse_row_label(label: str) -> tuple[str, str]:
    """
    Turn 'Strength III' -> ('strength', 'III')
         'Service I'    -> ('service', 'I')
    Fallback to ('', '') if we can't parse.
    """
    txt = (label or "").strip()
    if not txt:
        return "", ""
    parts = txt.split()
    if len(parts) < 2:
        return "", ""
    head = parts[0].lower()
    code = parts[-1].strip(",")
    if head.startswith("strength"):
        return "strength", code
    if head.startswith("service"):
        return "service", code
    return "", code


def _compose_name(
    cfg: WindLoadNamingSettings,
    *,
    base: str,
    limit_kind: str,   # 'strength' | 'service'
    case_code: str,
    angle: int | float,
) -> str:
    limit = (
        cfg.limit_state_labels.strength_label
        if limit_kind == "strength"
        else cfg.limit_state_labels.service_label
    )
    tokens = {
        "base": base,
        "limit": limit,
        "case": case_code,
        "angle_prefix": cfg.angle.prefix,
        "angle": f"{angle:g}",
    }
    return cfg.text.template.format(**tokens)


# ---------------------------------------------------------------------------
# Table model
# ---------------------------------------------------------------------------

class WindLoadTableModel(QAbstractTableModel):
    """
    Generic table:
    - optionally a fixed, non-editable first column with case names
    - N angle columns
    - internal data is a list[list[str]]
    """

    def __init__(
        self,
        *,
        title: str,
        load_cases: Sequence[str],
        angles: Sequence[int],
        angle_prefix: str,
        show_case_column: bool,
    ) -> None:
        
        super().__init__()
        self.title = title                # "WS" or "WL" (used for autofill logic)
        self.load_cases = list(load_cases)
        self.angles = list(angles)
        self.angle_prefix = angle_prefix
        self.show_case_column = show_case_column

        cols = len(self.angles)
        self._cells: list[list[str]] = [
            ["" for _ in range(cols)] for _ in self.load_cases
        ]

    # ----- Qt API -----

    def rowCount(self, parent=QModelIndex()) -> int:  # type: ignore[override]
        return len(self.load_cases)

    def columnCount(self, parent=QModelIndex()) -> int:  # type: ignore[override]
        return len(self.angles) + (1 if self.show_case_column else 0)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):  # type: ignore[override]
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None

        r, c = index.row(), index.column()

        if self.show_case_column and c == 0:
            return self.load_cases[r]

        data_col = c - (1 if self.show_case_column else 0)
        try:
            return self._cells[r][data_col]
        except IndexError:
            return None

    def setData(self, index: QModelIndex, value, role=Qt.EditRole):  # type: ignore[override]
        if role != Qt.EditRole or not index.isValid():
            return False

        # case column is non editable
        if self.show_case_column and index.column() == 0:
            return False

        r = index.row()
        c = index.column() - (1 if self.show_case_column else 0)
        try:
            self._cells[r][c] = str(value or "").strip()
        except IndexError:
            return False

        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def flags(self, index: QModelIndex):  # type: ignore[override]
        if not index.isValid():
            return Qt.NoItemFlags

        base_flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.show_case_column and index.column() == 0:
            return base_flags
        return base_flags | Qt.ItemIsEditable

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):  # type: ignore[override]
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None

        if self.show_case_column and section == 0:
            return "Load Case"

        offset = 1 if self.show_case_column else 0
        try:
            ang = self.angles[section - offset]
            return f"{self.angle_prefix} {ang}"
        except IndexError:
            return f"Angle {section}"

    # ----- our API -----

    def replace_angles(self, angles: Sequence[int]) -> None:
        """Resize columns when angle set changes."""
        self.beginResetModel()
        self.angles = list(angles)
        cols = len(self.angles)
        for r in range(len(self._cells)):
            row = self._cells[r]
            if len(row) < cols:
                row.extend([""] * (cols - len(row)))
            elif len(row) > cols:
                del row[cols:]
        self.endResetModel()

    def set_cell(self, row: int, angle: int, value: str) -> None:
        """Set by angle value, not by column index."""
        try:
            col_idx = self.angles.index(angle)
        except ValueError:
            return
        if self.show_case_column:
            model_col = col_idx + 1
        else:
            model_col = col_idx

        self.setData(self.index(row, model_col), value, Qt.EditRole)

    def to_assignments(self) -> List[LoadCaseAssignment]:
        out: List[LoadCaseAssignment] = []
        for r, case in enumerate(self.load_cases):
            # WL table has no case column -> use table title
            case_name = case if self.show_case_column else self.title
            for c, angle in enumerate(self.angles):
                val = (self._cells[r][c] or "").strip()
                if val:
                    out.append(
                        LoadCaseAssignment(
                            case=case_name,
                            angle=angle,
                            value=val,
                        )
                    )
        return out


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class WindLoadCases(QDialog):
    dataChanged = Signal(PairWindLoadModel)

    MAX_ANGLES = 5

    def __init__(self, parent=None, *, naming: Optional[WindLoadNamingSettings] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Wind Load Cases")
        self.resize(940, 640)

        self.naming = naming or WindLoadNamingSettings()

        # master list from DB module
        self.ws_all_cases: List[str] = LOAD_CASES[:]       # all possible rows
        self.ws_visible_cases: List[str] = LOAD_CASES[:]   # rows actually shown

        self._angle_spinners: List[QComboBox] = []
        self._num_angles: int = 3

        self.ws_model: WindLoadTableModel
        self.wl_model: WindLoadTableModel

        self._build_ui()
        self._load_from_db()
        self._autofill_all()

    # ----- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # angles bar
        root.addWidget(self._build_angles_group())

        # tables
        angles_now = self._current_angles()
        angle_prefix = self.naming.angle.prefix

        self.ws_model = WindLoadTableModel(
            title="WS",
            load_cases=self.ws_visible_cases,
            angles=angles_now,
            angle_prefix=angle_prefix,
            show_case_column=True,
        )
        self.wl_model = WindLoadTableModel(
            title="WL",
            load_cases=["WL"],
            angles=angles_now,
            angle_prefix=angle_prefix,
            show_case_column=False,
        )

        self.ws_group = self._build_ws_group(self.ws_model)
        self.wl_group = self._build_table_group("Wind on Live Load (WL)", self.wl_model)
        root.addWidget(self.ws_group)
        root.addWidget(self.wl_group)

        # buttons
        btn_row = QHBoxLayout()
        btn_apply = QPushButton("Apply")
        btn_close = QPushButton("Close")
        btn_apply.clicked.connect(self._on_apply)
        btn_close.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    def _build_angles_group(self) -> QGroupBox:
        gb = QGroupBox("Angle Configuration")
        lay = QHBoxLayout(gb)

        lay.addWidget(QLabel("Number of Angles:"))
        self.spin_num = QSpinBox()
        self.spin_num.setRange(1, self.MAX_ANGLES)
        self.spin_num.setValue(self._num_angles)
        self.spin_num.valueChanged.connect(self._on_num_angles_changed)
        lay.addWidget(self.spin_num)

        lay.addWidget(QLabel("Angles:"))
        defaults = ["0", "15", "30", "45", "60"]
        for i in range(self.MAX_ANGLES):
            cb = QComboBox()
            cb.addItems(defaults)
            cb.setCurrentIndex(i if i < len(defaults) else 0)
            cb.setEnabled(i < self._num_angles)
            cb.currentTextChanged.connect(self._on_angle_text_changed)
            self._angle_spinners.append(cb)
            lay.addWidget(cb)

        return gb

    def _build_ws_group(self, model: QAbstractTableModel) -> QGroupBox:
        gb = QGroupBox("Wind on Structure (WS)")
        vlay = QVBoxLayout(gb)

        # checkbox row
        cbrow = QHBoxLayout()
        cbrow.addWidget(QLabel("Show:"))
        self._ws_checkboxes: List[QCheckBox] = []
        for case in self.ws_all_cases:
            cb = QCheckBox(case)
            cb.setChecked(case in self.ws_visible_cases)
            cb.toggled.connect(self._on_ws_case_toggled)
            cbrow.addWidget(cb)
            self._ws_checkboxes.append(cb)
        cbrow.addStretch()
        vlay.addLayout(cbrow)

        # table
        view = self._create_table_view(model)
        vlay.addWidget(view)
        return gb

    def _build_table_group(self, title: str, model: QAbstractTableModel) -> QGroupBox:
        gb = QGroupBox(title)
        vlay = QVBoxLayout(gb)
        vlay.addWidget(self._create_table_view(model))
        return gb

    def _create_table_view(self, model: QAbstractTableModel) -> QTableView:
        view = QTableView()
        view.setModel(model)
        view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        view.verticalHeader().setVisible(False)
        view.setFont(QFont("Arial", 10))
        return view

    # ----- angle handling --------------------------------------------------

    def _current_angles(self) -> List[int]:
        n = self.spin_num.value()
        return [int(self._angle_spinners[i].currentText()) for i in range(n)]

    def _on_num_angles_changed(self, n: int) -> None:
        for i, cb in enumerate(self._angle_spinners):
            cb.setEnabled(i < n)
        self._rebuild_models()

    def _on_angle_text_changed(self, _: str) -> None:
        # any change should propagate to models
        self._rebuild_models()

    def _rebuild_models(self) -> None:
        angles_now = self._current_angles()
        angle_prefix = self.naming.angle.prefix

        # rebuild WS
        self.ws_model = WindLoadTableModel(
            title="WS",
            load_cases=self.ws_visible_cases,
            angles=angles_now,
            angle_prefix=angle_prefix,
            show_case_column=True,
        )
        self._replace_last_widget(self.ws_group, self._create_table_view(self.ws_model))

        # rebuild WL
        self.wl_model = WindLoadTableModel(
            title="WL",
            load_cases=["WL"],
            angles=angles_now,
            angle_prefix=angle_prefix,
            show_case_column=False,
        )
        self._replace_last_widget(self.wl_group, self._create_table_view(self.wl_model))

        self._autofill_all()

    @staticmethod
    def _replace_last_widget(group: QGroupBox, new_widget) -> None:
        lay = group.layout()
        old = lay.itemAt(lay.count() - 1).widget()
        lay.removeWidget(old)
        old.deleteLater()
        lay.addWidget(new_widget)

    # ----- autofill --------------------------------------------------------

    def _autofill_all(self) -> None:
        angles = self._current_angles()
        self._autofill_model(
            self.ws_model,
            base=self.naming.bases.wind_on_structure,
            angles=angles,
        )
        self._autofill_model(
            self.wl_model,
            base=self.naming.bases.wind_on_live_load,
            angles=angles,
        )

    def _autofill_model(
        self,
        model: WindLoadTableModel,
        *,
        base: str,
        angles: Sequence[int],
    ) -> None:
        cfg = self.naming
        for r, label in enumerate(model.load_cases):
            limit_kind, case_code = _parse_row_label(label)

            # WL special case: no strength/service in label
            if not limit_kind and model.title == "WL":
                limit_kind = "service"
                case_code = ""

            if not limit_kind and model.title != "WL":
                continue

            for c, ang in enumerate(angles):
                current_val = (model._cells[r][c] or "").strip()
                if current_val:
                    continue

                if model.title == "WL" and not model.show_case_column:
                    name = f"{base}_{cfg.angle.prefix}{ang:g}"
                else:
                    name = _compose_name(
                        cfg,
                        base=base,
                        limit_kind=limit_kind,
                        case_code=case_code,
                        angle=ang,
                    )
                model._cells[r][c] = name

        if model.rowCount() and model.columnCount():
            start_col = 1 if model.show_case_column else 0
            top_left = model.index(0, start_col)
            bottom_right = model.index(model.rowCount() - 1, model.columnCount() - 1)
            model.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole])

    # ----- WS checkbox handling --------------------------------------------

    def _on_ws_case_toggled(self) -> None:
        visible: List[str] = [
            cb.text() for cb in self._ws_checkboxes if cb.isChecked()
        ]

        if not visible:
            # keep at least first one
            first = self.ws_all_cases[0]
            visible = [first]
            for cb in self._ws_checkboxes:
                if cb.text() == first:
                    cb.blockSignals(True)
                    cb.setChecked(True)
                    cb.blockSignals(False)

        self.ws_visible_cases = visible
        self._rebuild_models()

    # ----- persistence ------------------------------------------------------

    def _on_apply(self) -> None:
        try:
            ws_assignments = self.ws_model.to_assignments()
            wl_assignments = self.wl_model.to_assignments()
            model = PairWindLoadModel(
                ws_cases=ws_assignments,
                wl_cases=wl_assignments,
            )

            wind_db.ws_cases = pd.DataFrame([asdict(a) for a in ws_assignments])
            wind_db.wl_cases = pd.DataFrame([asdict(a) for a in wl_assignments])
            wind_db.update_wind_pressures()

            self.dataChanged.emit(model)
            QMessageBox.information(self, "Success", "Wind load pairs updated successfully.")
            self.accept()
        except Exception as exc:
            log.exception("PairWindLoadCases: apply failed: %s", exc)
            QMessageBox.critical(self, "Error", str(exc))

    def _load_from_db(self) -> None:
        """
        Pull data from wind_db and paint it into the models.
        We let DB drive:
        - angle set
        - WS visible rows
        - cell contents
        """
        try:
            data = wind_db.get_data()
        except Exception as exc:
            log.warning("PairWindLoadCases: no prior data: %s", exc)
            return

        ws_df: pd.DataFrame = data.get("WS Cases", pd.DataFrame())
        wl_df: pd.DataFrame = data.get("WL Cases", pd.DataFrame())
        if ws_df.empty and wl_df.empty:
            return

        # angles in DB
        angles_set = set()
        for df in (ws_df, wl_df):
            if not df.empty and "Angle" in df:
                angles_set.update(int(a) for a in df["Angle"].unique())
        if angles_set:
            angles_sorted = sorted(angles_set)
            self.spin_num.setValue(len(angles_sorted))
            # this calls _rebuild_models()
            for i, ang in enumerate(angles_sorted):
                self._angle_spinners[i].blockSignals(True)
                self._angle_spinners[i].setCurrentText(str(ang))
                self._angle_spinners[i].blockSignals(False)
            self._rebuild_models()

        # --- load WS ---
        if not ws_df.empty:
            db_cases = [str(c) for c in ws_df["Case"].unique()]
            active_cases = [c for c in self.ws_all_cases if c in db_cases] or self.ws_all_cases[:]
            self.ws_visible_cases = active_cases

            # update checkboxes
            for cb in self._ws_checkboxes:
                cb.blockSignals(True)
                cb.setChecked(cb.text() in active_cases)
                cb.blockSignals(False)

            # rebuild again to reflect new visible rows
            self._rebuild_models()

            for _, row in ws_df.iterrows():
                case_name = str(row["Case"])
                angle_val = int(row["Angle"])
                value = str(row.get("Value", ""))

                try:
                    r = self.ws_model.load_cases.index(case_name)
                except ValueError:
                    continue
                self.ws_model.set_cell(r, angle_val, value)

        # --- load WL ---
        if not wl_df.empty:
            for _, row in wl_df.iterrows():
                angle_val = int(row["Angle"])
                value = str(row.get("Value", ""))
                # WL always single row, index 0
                self.wl_model.set_cell(0, angle_val, value)

        # finally fill missing
        self._autofill_all()
