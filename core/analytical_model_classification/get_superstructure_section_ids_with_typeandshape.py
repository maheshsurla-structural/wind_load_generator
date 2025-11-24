from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List, Iterable

from midas.resources.section import Section


@dataclass
class SuperstructureSectionClassifier:
    """
    Classifies MIDAS section IDs that clearly belong to the superstructure.
    """

    # Optional caller-provided sections (lazy-loaded if None)
    sections: Optional[Dict[str, Dict[str, Any]]] = None

    # Debugging settings
    debug: bool = False
    preview_limit: int = 5
    printer: Callable[[str], None] = print

    # --- Class constants ---
    SUPER_SECTTYPES: set = field(default_factory=lambda: {"PSC", "COMPOSITE"})
    TAPERED_SHAPES: set = field(
        default_factory=lambda: {
            "1CEL", "2CEL", "3CEL", "NCEL", "NCE2",
            "PSCM", "PSCI", "PSCH", "PSCT", "PSCB",
            "VALU", "CMPW", "CP_B", "CP_T",
            "CSGB", "CSGI", "CSGT",
            "CPCI", "CPCT", "CP_G",
            "STLB", "STLI",
        }
    )

    # ---------------------------------------------------------
    # Post-init validation
    # ---------------------------------------------------------
    def __post_init__(self) -> None:
        # Guard against someone passing the Section *class* by mistake
        if self.sections is Section:
            raise TypeError(
                "You passed the Section class instead of section data. "
                "Did you mean Section.get_all()?"
            )

        if self.sections is not None:
            if not isinstance(self.sections, dict):
                raise TypeError(
                    "sections must be a dict mapping section IDs to metadata "
                    f"(e.g. the result of Section.get_all()), got {type(self.sections).__name__}"
                )

            for key, val in self.sections.items():
                if not isinstance(key, (str, int)):
                    raise TypeError(
                        f"Section ID keys must be str or int, got {key!r} "
                        f"of type {type(key).__name__}"
                    )
                if not isinstance(val, dict):
                    raise TypeError(
                        f"Section entry for key {key!r} must be a dict of metadata, "
                        f"got {type(val).__name__}"
                    )

    # ---------------------------------------------------------
    # Helper: Debug-safe logging
    # ---------------------------------------------------------
    def _log(self, msg: str) -> None:
        if self.debug:
            self.printer(msg)

    # ---------------------------------------------------------
    # Lazy loading of sections
    # ---------------------------------------------------------
    def _load_sections(self) -> Dict[str, Dict[str, Any]]:
        if self.sections is None:
            self._log("[Classifier] Loading sections from MIDAS (Section.get_all())")
            self.sections = Section.get_all() or {}
            self._log(f"  Loaded {len(self.sections)} sections")
        return self.sections

    # ---------------------------------------------------------
    # Optional preview of first few entries
    # ---------------------------------------------------------
    def _debug_preview(self, sections: Dict[str, Dict[str, Any]]) -> None:
        if not self.debug:
            return

        self._log("[Classifier] Section preview:")
        for sid, data in list(sections.items())[: self.preview_limit]:
            self._log(
                f"  SAMPLE {sid}: "
                f"SECTTYPE={data.get('SECTTYPE')!r}, "
                f"SHAPE={data.get('SHAPE')!r}, "
                f"SECT_NAME={data.get('SECT_NAME')!r}"
            )

    # ---------------------------------------------------------
    # Core classification logic
    # ---------------------------------------------------------
    def iter_superstructure_section_ids(self) -> Iterable[str]:
        sections = self._load_sections()
        self._debug_preview(sections)

        for key, value in sections.items():
            sect_type = (value.get("SECTTYPE") or "").upper()
            shape_type = (value.get("SHAPE") or "").upper()

            if sect_type in self.SUPER_SECTTYPES:
                yield str(key)
                continue

            if sect_type == "TAPERED" and shape_type in self.TAPERED_SHAPES:
                yield str(key)
                continue

    def get_superstructure_section_ids(self) -> List[str]:
        ids = list(self.iter_superstructure_section_ids())
        # If you’re worried about huge logs, just log the count:
        self._log(f"[Classifier] Found {len(ids)} superstructure sections")
        # Or keep the full list if you really want:
        # self._log(f"[Classifier] Found {len(ids)} superstructure sections → {ids}")
        return ids


# ---------------------------------------------------------
# Optional backward-compatible function wrapper
# ---------------------------------------------------------
def get_superstructure_section_ids_with_typeandshape(
    sections: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    debug: bool = False,
    preview_limit: int = 5,
    printer: Callable[[str], None] = print,
) -> List[str]:
    classifier = SuperstructureSectionClassifier(
        sections=sections,
        debug=debug,
        preview_limit=preview_limit,
        printer=printer,
    )
    return classifier.get_superstructure_section_ids()
