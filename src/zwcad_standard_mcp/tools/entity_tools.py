from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.models import EntityPropertyPatch, EntityQuerySpec, TransformRequest
from zwcad_standard_mcp.services import CadService

from .common import invoke


def register_entity_tools(mcp: Any, service: CadService) -> None:
    @mcp.tool()
    def get_selected_entities(limit: int = 200) -> dict:
        """读取用户在 ZWCAD 中预先选中的实体，返回句柄、类型、图层和摘要。"""
        return invoke(service.get_selected_entities, limit)

    @mcp.tool()
    def query_entities(query: EntityQuerySpec) -> dict:
        """按空间、实体类型、图层、文字内容或块名查询对象，适合批量检查与定位。"""
        return invoke(service.query_entities, query)

    @mcp.tool()
    def get_entity_details(handles: list[str]) -> dict:
        """按句柄批量读取实体几何、通用属性、边界框和块属性。"""
        return invoke(service.get_entity_details, handles)

    @mcp.tool()
    def update_entity_properties(
        patch: EntityPropertyPatch,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """批量修改实体图层、颜色、线型、线宽或可见性；dry_run=true 仅预览，dry_run=false 且 confirm=true 才执行。"""
        return invoke(service.update_entity_properties, patch, dry_run, confirm)

    @mcp.tool()
    def normalize_selected_entities(
        target_layer: str | None = None,
        set_color_bylayer: bool = True,
        set_linetype_bylayer: bool = True,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """将当前选择对象归一到目标图层，并可统一为 ByLayer；解决导入图纸属性混乱。dry_run=true 仅预览，dry_run=false 且 confirm=true 才执行。"""
        return invoke(
            service.normalize_selected_entities,
            target_layer,
            set_color_bylayer,
            set_linetype_bylayer,
            dry_run,
            confirm,
        )

    @mcp.tool()
    def transform_entities(request: TransformRequest, dry_run: bool = True, confirm: bool = False) -> dict:
        """批量移动、复制、旋转、缩放或镜像实体；dry_run=true 仅预览，dry_run=false 且 confirm=true 才执行。角度使用弧度。"""
        return invoke(service.transform_entities, request, dry_run, confirm)

    @mcp.tool()
    def delete_entities(
        handles: list[str],
        dry_run: bool = True,
        confirm: bool = False,
        second_confirm: bool = False,
    ) -> dict:
        """批量删除对象。必须先 dry_run 预览，再以 dry_run=false、confirm=true 且 second_confirm=true 执行（双重确认）。"""
        return invoke(service.delete_entities, handles, dry_run, confirm, second_confirm)
