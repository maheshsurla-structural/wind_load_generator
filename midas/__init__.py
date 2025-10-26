from .midas_api import MidasAPI
from .resources.units import Units
from .resources.node import Node
from .resources.element import Element
from .material import get_materials
from .section import get_sections, get_section_properties
from .view_select import ViewSelected
from .create_structural_group import create_structural_group

# public aliases
api = MidasAPI
units = Units
nodes = Node            # <-- alias singular -> plural-style name
elements = Element      # <-- alias singular -> plural-style name

__all__ = [
    "api",
    "units",
    "nodes",
    "elements",
    "MidasAPI",
    "Units",
    "Node",
    "Element",
    "get_materials",
    "get_sections",
    "get_section_properties",
    "ViewSelected",
    "get_query_element",
    "create_structural_group",
]
