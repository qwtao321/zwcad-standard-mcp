from __future__ import annotations

from typing import Any

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
        """读取指定布局的打印配置：纸张尺寸、出图比例、方向、打印机配置等；不传 layout_name 时读取当前活动布局。"""
        return invoke(service.get_layout_plot_settings, layout_name)

    @mcp.tool()
    def plot_layouts(
        layout_names: list[str],
        output_dir: str,
        plot_configuration: str | None = None,
        extension: str = "pdf",
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """按布局批量输出文件，解决逐布局切换、命名和打印的重复工作；dry_run=true 仅预览路径，dry_run=false 且 confirm=true 才真正输出。"""
        return invoke(
            service.plot_layouts,
            layout_names,
            output_dir,
            plot_configuration,
            extension,
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
    def verify_export_files(file_paths: list[str]) -> dict:
        """验证已导出文件是否存在、大小是否非零，并校验常见格式（PDF/DXF/DWG/STEP/STL/3MF/PNG/JPG）的文件签名。"""
        return invoke(service.verify_export_files, file_paths)
