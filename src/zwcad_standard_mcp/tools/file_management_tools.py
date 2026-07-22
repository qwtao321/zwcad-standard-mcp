from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.services import CadService

from .common import invoke


def register_file_management_tools(mcp: Any, service: CadService) -> None:
    @mcp.tool()
    def scan_cad_folder(path: str, recursive: bool = False) -> dict:
        """扫描本地文件夹中的 CAD 文件（.dwg/.dxf/.dwt），返回文件列表。"""
        return invoke(service.scan_cad_folder, path, recursive)

    @mcp.tool()
    def open_document(
        path: str,
        read_only: bool = False,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """在 ZWCAD 中打开指定路径的 DWG/DXF 文件；dry_run=true 仅预览，dry_run=false 且 confirm=true 才真正打开。"""
        return invoke(service.open_document, path, read_only, dry_run, confirm)

    @mcp.tool()
    def close_document(
        name: str,
        save_changes: bool = False,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """关闭指定名称的已打开图纸；默认不保存，关闭前需 confirm=true。"""
        return invoke(service.close_document, name, save_changes, dry_run, confirm)

    @mcp.tool()
    def create_batch_job(
        total: int,
        files: list[str] | None = None,
        operation: str = "plot_pdf",
        output_dir: str | None = None,
        config: dict[str, Any] | None = None,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        """创建一个批量任务并返回任务 ID。若传入 files，则在后台自动执行该批量任务（默认 operation=plot_pdf）。真实执行需 confirm=true。"""
        return invoke(service.create_batch_job, total, files, operation, output_dir, config, dry_run, confirm)

    @mcp.tool()
    def get_batch_job_status(job_id: str) -> dict:
        """查询批量任务的当前进度（total/finished/failed/status）。"""
        return invoke(service.get_batch_job_status, job_id)
