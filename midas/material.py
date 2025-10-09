from midas.midas_api import MidasAPI

def get_materials():
    """Fetch material properties from MIDAS Civil NX."""
    response = MidasAPI("GET", "/db/MATL")
    return response if response else []