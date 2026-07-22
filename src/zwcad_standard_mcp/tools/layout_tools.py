from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.models import PlotScopeRequest
from zwcad_standard_mcp.services import CadService

from .common import invoke


def register_layout_tools(mcp: Any, service: CadService) -> None:
    @mcp.tool()
    def list_layouts() -> dict:
        """列出模型空间和全部布局，并返回当前活动布局及出图配置摘要。"""
        return invoke(service.list_layouts)

    @mcp.tool()
    def activate_layout(name: str) -> dict:
        """切换到指定模型/图纸布局。"""
        return invoke(service.activate_layout, name)

    @mcp.tool()
    def get_layout_plot_settings(layout_name: str | None = None) -> dict:
        """读取指定布局的打印配置：纸张尺寸、出图范围、窗口坐标、设备、比例、方向、打印样式等；不传 layout_name 时读取当前活动布局。"""
        return invoke(service.get_layout_plot_settings, layout_name)

    @mcp.tool()
    def get_plot_capabilities() -> dict:
        """读取当前 ZWCAD 环境支持的打印设备、纸张尺寸和输出格式，用于规划出图。"""
        return invoke(service.get_plot_capabilities)

    @mcp.tool()
    def preview_plot_scope(request: PlotScopeRequest) -> dict:
        """解析并预览最终打印区域，返回包围盒、裁切风险和关联的打印设置。"""
        return invoke(service.preview_plot_scope, request)

    @mcp.tool()
    def get_current_view() -> dict:
        """读取当前 CAD 视口的中心、范围与包围盒，用于"当前显示范围"出图。"""
        return invoke(service.get_current_view)

    @mcp.tool()
    def get_drawing_extents() -> dict:
        """读取整张图纸的实际图形包围盒（所有实体最小外包矩形），用于"图形范围"出图。"""
        return invoke(service.get_drawing_extents)

    @mcp.tool()
    def plot_layouts(
        layout_names: list[str],
        output_dir: str,
        plot_configuration: str | None = None,
        extension: str = "pdf",
        scope_type: str | None = None,
        window_lower_left: list[float] | None = None,
        window_upper_right: list[float] | None = None,
        selected_handles: list[str] | None = None,
        center_plot: bool | None = None,
        fit_to_paper: bool | None = None,
        custom_scale: float | None = None,
        override_policy: str = "temporary",
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """按布局批量输出文件。支持指定打印范围（display/extents/limits/view/window/layout）、窗口坐标、居中、布满图纸和自定义比例；dry_run=true 仅预览，dry_run=false 且 confirm=true 才真正输出。"""
        return invoke(
            service.plot_layouts,
            layout_names,
            output_dir,
            plot_configuration,
            extension,
            scope_type,
            window_lower_left,
            window_upper_right,
            selected_handles,
            center_plot,
            fit_to_paper,
            custom_scale,
            override_policy,
            dry_run,
            confirm,
        )

    @mcp.tool()
    def export_drawing(
        base_file_path: str,
        extension: str = "DXF",
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """使用 ZWCAD Export 导出当前图纸全部对象；dry_run=true 仅预览，dry_run=false 且 confirm=true 才真正导出。"""
        return invoke(service.export_drawing, base_file_path, extension, dry_run, confirm)

    @mcp.tool()
    def verify_export_files(
        file_paths: list[str],
        layout_names: list[str] | None = None,
        min_size_bytes: int = 1024,
        expected_plot_range: dict[str, list[float]] | None = None,
    ) -> dict:
        """验证已导出文件是否存在、大小是否满足最小值、布局与打印范围是否合理，并校验常见格式签名。"""
        return invoke(service.verify_export_files, file_paths, layout_names, min_size_bytes, expected_plot_range)
