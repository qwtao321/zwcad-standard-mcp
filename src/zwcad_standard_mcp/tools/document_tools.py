from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.services import CadService

from .common import invoke


def register_document_tools(mcp: Any, service: CadService) -> None:
    @mcp.tool()
    def get_current_document() -> dict:
        """读取当前 DWG 的名称、路径、保存状态、只读状态和活动布局。"""
        return invoke(service.get_current_document)

    @mcp.tool()
    def list_documents() -> dict:
        """列出当前 ZWCAD 进程中已打开的全部图纸。"""
        return invoke(service.list_documents)

    @mcp.tool()
    def activate_document(name: str) -> dict:
        """切换到指定名称的已打开图纸。"""
        return invoke(service.activate_document, name)

    @mcp.tool()
    def save_document(file_path: str | None = None, confirm: bool = False) -> dict:
        """保存当前图纸；默认拒绝执行，必须在用户确认路径后传 confirm=true。"""
        return invoke(service.save_document, file_path, confirm)
