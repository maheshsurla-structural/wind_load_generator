from midas.midas_api import MidasAPI

def get_distance_unit():
    response = MidasAPI("GET", "/db/UNIT")
    return response.get("UNIT", {}).get("1", {}).get("DIST", "")