# gui/dialogs/control_data/pages/wind_naming.py

from __future__ import annotations
from dataclasses import replace
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QGroupBox, QHBoxLayout, QVBoxLayout, QLineEdit,
    QLabel, QPlainTextEdit, QDoubleSpinBox
)

from .base import ControlDataPage
from ..models import (
    ControlDataModel,
    WindLoadNamingSettings, BasePrefixes, LimitStateLabels, CaseSets,
    AngleFormat, TextFormat
)

class WindNamingPage(QWidget, ControlDataPage):
    title = "Wind Load Naming"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # --- Bases ---
        grp_bases = QGroupBox("Base Prefixes")
        form_bases = QFormLayout(grp_bases)
        self.txt_ws = QLineEdit("WS")
        self.txt_wl = QLineEdit("WL")
        form_bases.addRow("Wind on Structure:", self.txt_ws)
        form_bases.addRow("Wind on Live Load:", self.txt_wl)

        # --- Limit State Labels ---
        grp_limits = QGroupBox("Limit State Labels")
        form_limits = QFormLayout(grp_limits)
        self.txt_strength_lbl = QLineEdit("ULS")
        self.txt_service_lbl = QLineEdit("SLS")
        form_limits.addRow("Strength label:", self.txt_strength_lbl)
        form_limits.addRow("Service label:", self.txt_service_lbl)

        # --- Case Sets ---
        grp_cases = QGroupBox("Case Codes (comma-separated)")
        form_cases = QFormLayout(grp_cases)
        self.txt_strength_cases = QLineEdit("III,V")
        self.txt_service_cases = QLineEdit("I,IV")
        form_cases.addRow("Strength cases:", self.txt_strength_cases)
        form_cases.addRow("Service cases:", self.txt_service_cases)

        # --- Angle Format (simplified) ---
        grp_angle = QGroupBox("Angle Format")
        form_angle = QFormLayout(grp_angle)
        self.txt_angle_prefix = QLineEdit("Ang")
        form_angle.addRow("Prefix:", self.txt_angle_prefix)

        # --- Text Format (simplified) ---
        grp_text = QGroupBox("Text / Template")
        form_text = QFormLayout(grp_text)
        self.txt_template = QPlainTextEdit("{base}_{limit}_{case}_{angle_prefix}_{angle}")
        self.txt_template.setFixedHeight(60)
        hint = QLabel("Tokens: {base}, {limit}, {case}, {angle_prefix}, {angle}")
        hint.setWordWrap(True)
        form_text.addRow("Template:", self.txt_template)
        form_text.addRow(hint)

        # --- Live Preview ---
        grp_preview = QGroupBox("Preview")
        v_preview = QVBoxLayout(grp_preview)
        row = QHBoxLayout()
        self.spin_preview_angle = QDoubleSpinBox()
        self.spin_preview_angle.setRange(-9999.0, 9999.0)
        self.spin_preview_angle.setDecimals(3)  # UI convenience only
        self.spin_preview_angle.setValue(30.0)
        row.addWidget(QLabel("Angle:")); row.addWidget(self.spin_preview_angle)
        self.lbl_preview_ws = QLabel("WS_ULS_III_Ang_30")
        self.lbl_preview_wl = QLabel("WL_SLS_IV_Ang_30")
        self.lbl_preview_ws.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_preview_wl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v_preview.addLayout(row)
        v_preview.addWidget(QLabel("WS example:")); v_preview.addWidget(self.lbl_preview_ws)
        v_preview.addWidget(QLabel("WL example:")); v_preview.addWidget(self.lbl_preview_wl)

        # Layout
        root = QVBoxLayout(self)
        for g in (grp_bases, grp_limits, grp_cases, grp_angle, grp_text, grp_preview):
            root.addWidget(g)
        root.addStretch()

        # Wire updates -> preview
        for w in [
            self.txt_ws, self.txt_wl, self.txt_strength_lbl, self.txt_service_lbl,
            self.txt_strength_cases, self.txt_service_cases, self.txt_angle_prefix,
            self.txt_template, self.spin_preview_angle
        ]:
            for sig in ("textChanged", "valueChanged"):
                if hasattr(w, sig):
                    getattr(w, sig).connect(self._refresh_preview)

    # ---- ControlDataPage API ----
    def get_length_labels(self): return []
    def get_force_labels(self):  return []

    def set_state_from_model(self, model: ControlDataModel) -> None:
        s = model.naming.wind

        self.txt_ws.setText(s.bases.wind_on_structure)
        self.txt_wl.setText(s.bases.wind_on_live_load)

        self.txt_strength_lbl.setText(s.limit_state_labels.strength_label)
        self.txt_service_lbl.setText(s.limit_state_labels.service_label)

        self.txt_strength_cases.setText(",".join(s.cases.strength_cases))
        self.txt_service_cases.setText(",".join(s.cases.service_cases))

        self.txt_angle_prefix.setText(s.angle.prefix)
        self.txt_template.setPlainText(s.text.template)

        self._refresh_preview()

    def apply_to_model(self, model: ControlDataModel) -> None:
        s = model.naming.wind

        def _split_codes(txt: str) -> list[str]:
            return [t.strip() for t in txt.split(",") if t.strip()]

        model.naming.wind = WindLoadNamingSettings(
            bases=replace(s.bases,
                wind_on_structure=self.txt_ws.text().strip() or "WS",
                wind_on_live_load=self.txt_wl.text().strip() or "WL",
            ),
            limit_state_labels=replace(s.limit_state_labels,
                strength_label=self.txt_strength_lbl.text().strip() or "ULS",
                service_label=self.txt_service_lbl.text().strip() or "SLS",
            ),
            cases=replace(s.cases,
                strength_cases=_split_codes(self.txt_strength_cases.text()) or ["III", "V"],
                service_cases=_split_codes(self.txt_service_cases.text()) or ["I", "IV"],
            ),
            angle=replace(s.angle,
                prefix=self.txt_angle_prefix.text().strip() or "Ang",
            ),
            text=replace(s.text,
                template=self.txt_template.toPlainText().strip() or "{base}_{limit}_{case}_{angle_prefix}_{angle}",
            ),
        )

    def validate(self) -> tuple[bool, str]:
        # very light checks
        if not (self.txt_ws.text().strip() and self.txt_wl.text().strip()):
            return False, "Base prefixes (WS/WL) cannot be empty."
        if not self.txt_strength_lbl.text().strip() or not self.txt_service_lbl.text().strip():
            return False, "Limit state labels cannot be empty."
        return True, ""

    def on_units_changed(self, units, prev_len: str, new_len: str, prev_force: str, new_force: str) -> None:
        pass  # Not unit-sensitive

    # ---- preview helpers ----
    @staticmethod
    def _safe_split(txt: str, default: list[str]) -> list[str]:
        vals = [t.strip() for t in txt.split(",") if t.strip()]
        return vals or default

    @classmethod
    def _make(cls, cfg: WindLoadNamingSettings, *, base: str, limit: str, case: str, angle: float) -> str:
        tokens = {
            "base": base,
            "limit": limit,
            "case": case,
            "angle_prefix": cfg.angle.prefix,
            # simplified angle formatting; if they want "deg" etc., they add it to prefix or template
            "angle": f"{angle:g}",
        }
        return cfg.text.template.format(**tokens)

    def _refresh_preview(self) -> None:
        tmp = WindLoadNamingSettings(
            bases=BasePrefixes(
                wind_on_structure=self.txt_ws.text().strip() or "WS",
                wind_on_live_load=self.txt_wl.text().strip() or "WL",
            ),
            limit_state_labels=LimitStateLabels(
                strength_label=self.txt_strength_lbl.text().strip() or "ULS",
                service_label=self.txt_service_lbl.text().strip() or "SLS",
            ),
            cases=CaseSets(
                strength_cases=self._safe_split(self.txt_strength_cases.text(), ["III", "V"]),
                service_cases=self._safe_split(self.txt_service_cases.text(), ["I", "IV"]),
            ),
            angle=AngleFormat(
                prefix=self.txt_angle_prefix.text().strip() or "Ang",
            ),
            text=TextFormat(
                template=self.txt_template.toPlainText().strip() or "{base}_{limit}_{case}_{angle_prefix}_{angle}",
            ),
        )
        ang = float(self.spin_preview_angle.value())
        ws = self._make(tmp, base=tmp.bases.wind_on_structure,
                        limit=tmp.limit_state_labels.strength_label,
                        case=(tmp.cases.strength_cases[0] if tmp.cases.strength_cases else "III"),
                        angle=ang)
        wl = self._make(tmp, base=tmp.bases.wind_on_live_load,
                        limit=tmp.limit_state_labels.service_label,
                        case=(tmp.cases.service_cases[0] if tmp.cases.service_cases else "I"),
                        angle=ang)
        self.lbl_preview_ws.setText(ws)
        self.lbl_preview_wl.setText(wl)
