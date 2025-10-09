from midas.midas_api import MidasAPI


def get_nodes():
    """Fetch node data from MIDAS Civil NX."""
    response = MidasAPI("GET", "/db/NODE")
    return response.get("NODE", {}) if response else []
