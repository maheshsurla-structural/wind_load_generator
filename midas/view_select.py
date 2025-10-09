from midas.midas_api import MidasAPI


class ViewSelected:
    """Class to handle selection of nodes and elements for wind load application."""
    
    @staticmethod
    def view_selected_nodes():
        """Fetch selected nodes from MIDAS Civil NX."""
        selected = MidasAPI("GET", "/view/SELECT")
        return selected.get("SELECT", {}).get("NODE_LIST", [])
    
    @staticmethod
    def view_selected_elements():
        """Fetch selected elements from MIDAS Civil NX."""
        selected = MidasAPI("GET", "/view/SELECT")
        return selected.get("SELECT", {}).get("ELEM_LIST", [])

    

# if __name__ == "__main__":
#     nodes = ViewSelect.view_selected_nodes()
#     elements = ViewSelect.view_selected_elements()
#     print("Selected nodes:", nodes)
#     print("Selected elements:", elements)