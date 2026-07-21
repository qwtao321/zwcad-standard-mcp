from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.models import BlockAttributePatch
from zwcad_standard_mcp.services import CadService

from .common import invoke


def register_block_tools(mcp: Any, service: CadService) -> None:
    @mcp.tool()
    def list_block_definitions(detail: bool = False) -> dict:
        """列出块定义，识别标准件、图框、标题栏和外部参照。"""
        return invoke(service.list_block_definitions, detail)

    @mcp.tool()
    def list_block_references(
        scope: str = "all_layouts",
        block_name: str | None = None,
        has_attributes: bool | None = None,
        limit: int = 200,
    ) -> dict:
        """查询模型空间或布局中的实际块引用，可按块名和是否含属性过滤。"""
        return invoke(
            service.list_block_references,
            scope,
            block_name,
            has_attributes,
            limit,
        )

    @mcp.tool()
    def get_block_attributes(handles: list[str]) -> dict:
        """按块引用句柄批量读取属性 TAG 和文本，适合标准版标题栏检查。"""
        return invoke(service.get_block_attributes, handles)

    @mcp.tool()
    def update_block_attributes(
        updates: list[BlockAttributePatch],
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """按块引用句柄批量修改属性 TAG；dry_run=true 仅预览并报告不存在的 TAG，dry_run=false 且 confirm=true 才执行并回读验证。"""
        return invoke(service.update_block_attributes, updates, dry_run, confirm)

    @mcp.tool()
    def insert_blocks_batch(
        blocks: list[dict],
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """批量插入已有块定义，并可同步填写属性；dry_run=true 仅预览，dry_run=false 且 confirm=true 才执行。"""
        return invoke(service.insert_blocks, blocks, dry_run, confirm)
