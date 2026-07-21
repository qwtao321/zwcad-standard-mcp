from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.models import EntityCreateSpec
from zwcad_standard_mcp.services import CadService

from .common import invoke


def register_drawing_tools(mcp: Any, service: CadService) -> None:
    @mcp.tool()
    def create_entities_batch(
        entities: list[EntityCreateSpec],
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """批量创建直线、圆、圆弧、多段线、文字、图块及常用尺寸标注。dry_run=true 仅预览，dry_run=false 且 confirm=true 才真正写入。"""
        return invoke(service.create_entities, entities, dry_run, confirm)
