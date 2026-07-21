from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.models import LayerSpec
from zwcad_standard_mcp.services import CadService

from .common import invoke


def register_layer_tools(mcp: Any, service: CadService) -> None:
    @mcp.tool()
    def list_layers(detail: bool = True) -> dict:
        """列出图层；用于排查外部图纸图层混乱、颜色线型不统一等问题。"""
        return invoke(service.list_layers, detail)

    @mcp.tool()
    def ensure_layers(layers: list[LayerSpec], dry_run: bool = True, confirm: bool = False) -> dict:
        """批量创建或更新图层。dry_run=true 仅预览，dry_run=false 且 confirm=true 才执行。"""
        return invoke(service.ensure_layers, layers, dry_run, confirm)
