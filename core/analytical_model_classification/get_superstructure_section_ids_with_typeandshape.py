# core/analytical_model_classification/get_superstructure_section_ids_with_typeandshape.py

from __future__ import annotations
from typing import List, Dict, Any

from midas.resources.section import Section


def get_superstructure_section_ids_with_typeandshape() -> List[str]:
    """
    Return a list of section IDs that clearly belong to the superstructure.
    Classification is based solely on reliable MIDAS metadata:
        - SECTTYPE
        - SHAPE  (for tapered sections)

    No user-defined naming patterns are used (intentionally).
    """

    # Allowed shape types for TAPERED sections that represent girders/deck profiles.
    TAPERED_SHAPES = {
        "1CEL", "2CEL", "3CEL", "NCEL", "NCE2",
        "PSCM", "PSCI", "PSCH", "PSCT", "PSCB",
        "VALU", "CMPW", "CP_B", "CP_T",
        "CSGB", "CSGI", "CSGT",
        "CPCI", "CPCT", "CP_G",
        "STLB", "STLI",
    }

    # ------------------------------------------------------------------
    # Load all sections from MIDAS
    # ------------------------------------------------------------------
    all_sections: Dict[str, Dict[str, Any]] = Section.get_all() or {}

    # print("\n[get_superstructure_section_ids_with_typeandshape]") 
    # print(f"  Total sections in /db/SECT: {len(all_sections)}")

    # Preview first few entries for debugging
    for sid, data in list(all_sections.items())[:5]:
        print(
            f"  SAMPLE {sid}: "
            f"SECTTYPE={data.get('SECTTYPE')!r}, "
            f"SHAPE={data.get('SHAPE')!r}, "
            f"SECT_NAME={data.get('SECT_NAME')!r}"
        )

    selected_ids: List[str] = []

    # ------------------------------------------------------------------
    # Classify superstructure sections
    # ------------------------------------------------------------------
    for key, value in all_sections.items():
        sect_type = (value.get("SECTTYPE") or "").upper()
        shape_type = (value.get("SHAPE") or "").upper()

        # Rule 1: PSC or COMPOSITE → always superstructure
        if sect_type in {"PSC", "COMPOSITE"}:
            selected_ids.append(str(key))
            continue

        # Rule 2: TAPERED with an allowed shape
        if sect_type == "TAPERED" and shape_type in TAPERED_SHAPES:
            selected_ids.append(str(key))
            continue

        # No other section types are considered superstructure

    print(
        f"  Selected superstructure section IDs ({len(selected_ids)}): "
        f"{selected_ids}"
    )

    return selected_ids
