# core/analytical_model_classification/get_superstructure_section_ids_with_typeandshape.py

from midas import get_section_properties

def get_superstructure_section_ids_with_typeandshape():
    TAPERED_SHAPES = ["1CEL", "2CEL", "3CEL", "NCEL", "NCE2", "PSCM", "PSCI", "PSCH", "PSCT", "PSCB", "VALU", "CMPW", "CP_B", "CP_T", "CSGB", "CSGI", "CSGT", "CPCI", "CPCT", "CP_G", "STLB", "STLI"]
    """Fetch section property IDs that define superstructure elements (PSC, TAPERED, COMPOSITE). If section type is 'TAPERED', also check the shape."""
    section_properties = get_section_properties()
    selected_supersection_ids = []
    
    for section in section_properties:
        section_id = section[1]  # Assuming Section ID is the first item
        section_type = section[2]  # Assuming Section Type is the second item
        shape_type = section[3]  # Assuming Shape Type is the third item
        
        if section_type in ["PSC", "COMPOSITE"]:
            selected_supersection_ids.append(section_id)
        elif section_type == "TAPERED" and shape_type in TAPERED_SHAPES:
            selected_supersection_ids.append(section_id)
    
    return selected_supersection_ids