from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.services import CadService

from .common import invoke


def register_system_tools(mcp: Any, service: CadService) -> None:
    @mcp.tool()
    def diagnose_cad() -> dict:
        """诊断 ZWCAD COM 连接、当前图纸和 MCP 写入策略；排查“AI 连不上 CAD”。"""
        return invoke(service.diagnose_cad)

    @mcp.tool()
    def get_cad_app_info() -> dict:
        """获取当前 ZWCAD 程序版本、安装路径和可见状态。"""
        return invoke(service.get_app_info)

    @mcp.tool()
    def audit_drawing(sample_limit: int = 30) -> dict:
        """快速盘点整张图纸：实体类型、图层分布、块引用、布局数量及少量对象样本。"""
        return invoke(service.audit_drawing, sample_limit)
