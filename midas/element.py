from midas.midas_api import MidasAPI

def get_elements():
    """Fetch element data from MIDAS Civil NX."""
    response = MidasAPI("GET", "/db/ELEM")
    return response.get("ELEM", {}) if response else {}