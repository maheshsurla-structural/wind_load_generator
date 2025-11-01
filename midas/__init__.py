from .midas_api import MidasAPI

# resource classes
from .resources.units import Units
from .resources.node import Node
from .resources.element import Element
from .resources.section import Section
from .resources.static_load_case import StaticLoadCase  

# helpers / other modules
from .material import get_materials
from .resources.section import get_section_properties 
from .view_select import ViewSelected
from .create_structural_group import create_structural_group

# public aliases (friendly plural-ish handles)
api = MidasAPI
units = Units
nodes = Node            
elements = Element      
sections = Section      
static_load_cases = StaticLoadCase  

__all__ = [
    # aliases
    "api",
    "units",
    "nodes",
    "elements",
    "sections",
    "static_load_cases",   

    # core classes
    "MidasAPI",
    "Units",
    "Node",
    "Element",
    "Section",
    "StaticLoadCase",       

    # helpers / utilities
    "get_materials",
    "get_section_properties",
    "ViewSelected",
    "create_structural_group",
]
