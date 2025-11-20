# core\analytical_model_classification\get_superstructure_section_ids_with_typeandshape.py

from midas.resources.section import Section

def get_superstructure_section_ids_with_typeandshape():
    TAPERED_SHAPES = [
        "1CEL", "2CEL", "3CEL", "NCEL", "NCE2",
        "PSCM", "PSCI", "PSCH", "PSCT", "PSCB",
        "VALU", "CMPW", "CP_B", "CP_T",
        "CSGB", "CSGI", "CSGT",
        "CPCI", "CPCT", "CP_G",
        "STLB", "STLI",
    ]

    all_sections = Section.get_all() or {}

    print("\n[get_superstructure_section_ids_with_typeandshape]")
    print(f"  Total sections in /db/SECT: {len(all_sections)}")

    # show a few samples with normalized keys so you can verify
    for sid, raw in list(all_sections.items())[:5]:
        norm = {str(k).upper(): v for k, v in raw.items()}
        sample_sectype = norm.get("SECTTYPE") or norm.get("SECTYPE")
        print(
            f"  SAMPLE SECT {sid}: "
            f"SECTYPE={sample_sectype!r}, "
            f"SHAPE={norm.get('SHAPE')!r}, "
            f"NAME={norm.get('SECT_NAME')!r}"
        )

    selected_ids: list[str] = []

    for sid, raw in all_sections.items():
        # normalize keys -> UPPER once
        data = {str(k).upper(): v for k, v in raw.items()}

        # MIDAS actually uses SECTTYPE; fall back to SECTYPE just in case
        sect_type = (
            data.get("SECTTYPE") or data.get("SECTYPE") or ""
        ).upper()
        shape_type = (data.get("SHAPE") or "").upper()
        name = (data.get("SECT_NAME") or "").upper()

        # 0) Skip anything that clearly looks like substructure
        if any(bad in name for bad in ["PIER", "CAP", "BRACING"]):
            continue

        # 1) PSC + COMPOSITE (true superstructure)
        if sect_type in {"PSC", "COMPOSITE"}:
            selected_ids.append(str(sid))

        # 2) Tapered with specific shapes
        elif sect_type == "TAPERED" and shape_type in TAPERED_SHAPES:
            selected_ids.append(str(sid))

        # 3) DBUSER sections that *look* like girders / deck
        elif sect_type == "DBUSER" and (
            "GIRDER" in name
            or "GIRDERWIZ" in name
            or shape_type in {"I", "SB"}
        ):
            selected_ids.append(str(sid))

    print(
        f"  Selected superstructure section IDs ({len(selected_ids)}): "
        f"{selected_ids}"
    )

    return selected_ids

