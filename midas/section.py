from midas.midas_api import MidasAPI

def get_sections():
    """Fetch section properties from MIDAS Civil NX."""
    response = MidasAPI("GET", "/db/SECT")
    return response if response else []

def get_section_properties():
    """Fetch section properties from MIDAS Civil NX."""
    request_body = {
        "Argument": {
            "TABLE_NAME": "SectionProperties",
            "TABLE_TYPE": "SECTIONALL",
        }
    }
    response = MidasAPI("POST", "/post/TABLE", request_body)
    if response and "SectionProperties" in response:
        return response["SectionProperties"].get("DATA", [])  # ✅ Returning a list
    return []