from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.services import CadService

from .block_tools import register_block_tools
from .document_tools import register_document_tools
from .drawing_tools import register_drawing_tools
from .entity_tools import register_entity_tools
from .layer_tools import register_layer_tools
from .layout_tools import register_layout_tools
from .system_tools import register_system_tools


def register_all_tools(mcp: Any, service: CadService) -> None:
    register_system_tools(mcp, service)
    register_document_tools(mcp, service)
    register_layer_tools(mcp, service)
    register_entity_tools(mcp, service)
    register_drawing_tools(mcp, service)
    register_layout_tools(mcp, service)
    register_block_tools(mcp, service)
