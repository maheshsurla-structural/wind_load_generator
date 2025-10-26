from .midas_api import MidasAPI

# resource classes
from .resources.units import Units
from .resources.node import Node
from .resources.element import Element
from .resources.section import Section  # NEW

# helpers / other modules
from .material import get_materials
from .resources.section import get_section_properties  # moved from old_section
from .view_select import ViewSelected
from .create_structural_group import create_structural_group

# public aliases (friendly plural-ish handles)
api = MidasAPI
units = Units
nodes = Node            # alias singular class -> plural-y name
elements = Element      # alias singular class -> plural-y name
sections = Section      # NEW alias, same pattern

__all__ = [
    # aliases
    "api",
    "units",
    "nodes",
    "elements",
    "sections",

    # core classes
    "MidasAPI",
    "Units",
    "Node",
    "Element",
    "Section",

    # helpers / utilities
    "get_materials",
    "get_section_properties",
    "ViewSelected",
    "create_structural_group",
]
