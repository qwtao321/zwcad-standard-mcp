from __future__ import annotations

import itertools
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zwcad_standard_mcp.adapters.base import CadAdapter
from zwcad_standard_mcp.config import Settings
from zwcad_standard_mcp.errors import (
    BatchLimitError,
    ReadOnlyDocumentError,
    ValidationError,
    WriteDisabledError,
)
from zwcad_standard_mcp.models import (
    BlockAttributePatch,
    EntityCreateSpec,
    EntityPropertyPatch,
    EntityQuerySpec,
    LayerSpec,
    TransformRequest,
)
from zwcad_standard_mcp.permissions.policy import PermissionLevel
from zwcad_standard_mcp.permissions_bridge import require_permission


# In-memory batch job registry. Jobs are transient; they live only as long as the
# MCP server process. For long-running folder workflows the skill calls
# create_batch_job with files and polls get_batch_job_status.
_BATCH_JOBS: dict[str, dict[str, Any]] = {}
_BATCH_JOB_LOCK = threading.Lock()
_BATCH_JOB_SEQ = itertools.count(1)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_job_id() -> str:
    return f"JOB{next(_BATCH_JOB_SEQ):03d}"


def _update_job(job_id: str, **kwargs: Any) -> None:
    with _BATCH_JOB_LOCK:
        job = _BATCH_JOBS.get(job_id)
        if job is None:
            return
        job.update(kwargs)
        job["updated_at"] = _utc_now()


def _execute_batch_job(
    job_id: str,
    settings: Any,
    files: list[str],
    operation: str,
    output_dir: str | None,
    config: dict[str, Any] | None,
) -> None:
    """Background worker: open each file, run the operation, close it.

    Uses a fresh COM adapter instance because COM apartment affinity prevents
    reusing the adapter that was created in the MCP server thread. This worker
    calls adapter methods directly: the user already confirmed the batch when
    calling create_batch_job with confirm=true, so we avoid nested permission
    gates and blocking UI prompts inside the background thread.
    """
    from zwcad_standard_mcp.adapters.com import ComCadAdapter

    adapter = ComCadAdapter(
        prog_id=settings.prog_id if hasattr(settings, "prog_id") else "ZWCAD.Application",
        auto_start=getattr(settings, "auto_start_cad", False),
    )
    cfg = config or {}
    out_dir = output_dir or ""
    results: list[dict[str, Any]] = []

    _update_job(job_id, status="running", started_at=_utc_now())

    failed_count = 0
    for index, file_path in enumerate(files, start=1):
        file_result: dict[str, Any] = {
            "index": index,
            "file_path": file_path,
            "success": False,
            "outputs": [],
            "error": None,
        }
        doc_name: str | None = None
        try:
            open_data = adapter.open_document(file_path, read_only=True)
            doc_name = open_data["name"]

            if operation == "plot_pdf":
                layouts = adapter.list_layouts()
                layout_names = [lo["name"] for lo in layouts if not lo.get("model_space")]
                if not layout_names:
                    raise ValidationError("No paper layouts found; nothing to plot.")
                plot_cfg = cfg.get("plot_configuration")
                ext = cfg.get("extension", "pdf")
                plot_results = adapter.plot_layouts(
                    layout_names=layout_names,
                    output_dir=out_dir,
                    plot_configuration=plot_cfg,
                    extension=ext,
                )
                file_result["outputs"] = plot_results
                if any(not r.get("success") for r in plot_results):
                    raise ValidationError("one or more layouts failed to plot")

            file_result["success"] = True
        except Exception as exc:
            file_result["error"] = str(exc)
            failed_count += 1
        finally:
            if doc_name:
                try:
                    adapter.close_document(doc_name, save_changes=False)
                except Exception as close_exc:
                    if file_result["error"] is None:
                        file_result["error"] = f"close failed: {close_exc}"
                        failed_count += 1
            _update_job(job_id, finished=index, failed=failed_count)
            results.append(file_result)

    status = "completed" if failed_count == 0 else "completed_with_errors"
    _update_job(job_id, status=status, finished=len(files), failed=failed_count, results=results, completed_at=_utc_now())


class CadService:
    """User-scenario-oriented operations with safe defaults and structured previews."""

    def __init__(self, adapter: CadAdapter, settings: Settings) -> None:
        self.adapter = adapter
        self.settings = settings

    def _limit(self, items: list[Any], label: str) -> None:
        if len(items) > self.settings.max_batch_size:
            raise BatchLimitError(
                f"{label} contains {len(items)} items; maximum is {self.settings.max_batch_size}."
            )

    def _ensure_write(self) -> None:
        # Per-call confirmation is enforced by require_permission() before this
        # method runs. Here we only guard against read-only documents.
        document = self.adapter.get_current_document()
        if document.get("readonly"):
            raise ReadOnlyDocumentError("The active drawing is read-only.")

    @staticmethod
    def _summary(results: list[dict]) -> dict:
        success_count = sum(1 for item in results if item.get("success"))
        return {
            "total": len(results),
            "success_count": success_count,
            "failure_count": len(results) - success_count,
            "results": results,
        }

    def diagnose_cad(self) -> dict:
        result = self.adapter.diagnose()
        result["server_policy"] = {
            "permission_model": "per-call confirm (v2)",
            "write_requires_confirm": True,
            "delete_requires_second_confirm": True,
            "save_requires_path_and_confirm": True,
            "adapter": self.settings.adapter,
            "max_batch_size": self.settings.max_batch_size,
            "max_query_results": self.settings.max_query_results,
        }
        return result

    def get_app_info(self) -> dict:
        return {"success": True, "data": self.adapter.get_app_info()}

    def get_current_document(self) -> dict:
        return {"success": True, "data": self.adapter.get_current_document()}

    def list_documents(self) -> dict:
        documents = self.adapter.list_documents()
        return {"success": True, "count": len(documents), "data": documents}

    def activate_document(self, name: str) -> dict:
        return {"success": True, "data": self.adapter.activate_document(name)}

    def scan_cad_folder(self, path: str, recursive: bool = False) -> dict:
        return {"success": True, "data": self.adapter.scan_cad_folder(path, recursive)}

    def open_document(
        self,
        path: str,
        read_only: bool = False,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        target = Path(path).expanduser()
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "path": str(target),
                "read_only": read_only,
            }
        # Opening is a read-only filesystem/CAD operation; no permission gate.
        return {"success": True, "dry_run": False, "data": self.adapter.open_document(path, read_only)}

    def close_document(
        self,
        name: str,
        save_changes: bool = False,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "name": name,
                "save_changes": save_changes,
            }
        # Closing may discard unsaved changes, so treat as MODIFY.
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        return {"success": True, "dry_run": False, "data": self.adapter.close_document(name, save_changes)}

    def create_batch_job(
        self,
        total: int,
        files: list[str] | None = None,
        operation: str = "plot_pdf",
        output_dir: str | None = None,
        config: dict[str, Any] | None = None,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        if total <= 0:
            raise ValidationError("total must be greater than 0.")
        if files is not None and len(files) != total:
            total = len(files)

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "total": total,
                "files": files or [],
                "operation": operation,
                "output_dir": output_dir,
            }

        # A batch job that actually executes operations is a mutating workflow.
        if files:
            rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
            if rejection:
                return rejection

        job_id = _new_job_id()
        job = {
            "job_id": job_id,
            "status": "pending",
            "total": total,
            "finished": 0,
            "failed": 0,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "files": files or [],
            "operation": operation,
            "output_dir": output_dir,
            "config": config or {},
            "results": [],
        }
        with _BATCH_JOB_LOCK:
            _BATCH_JOBS[job_id] = job

        if files:
            thread = threading.Thread(
                target=_execute_batch_job,
                args=(job_id, self.settings, files, operation, output_dir, config),
                daemon=True,
            )
            thread.start()

        return {"success": True, "dry_run": False, "job_id": job_id, "status": job["status"], "total": total}

    def get_batch_job_status(self, job_id: str) -> dict:
        with _BATCH_JOB_LOCK:
            job = _BATCH_JOBS.get(job_id)
        if job is None:
            raise ValidationError(f"Batch job not found: {job_id}")
        return {
            "success": True,
            "data": {
                "job_id": job["job_id"],
                "status": job["status"],
                "total": job["total"],
                "finished": job["finished"],
                "failed": job["failed"],
                "progress_percent": round((job["finished"] / job["total"]) * 100, 1) if job["total"] else 0,
                "created_at": job["created_at"],
                "updated_at": job["updated_at"],
                "operation": job["operation"],
                "output_dir": job["output_dir"],
            },
        }

    def save_document(self, file_path: str | None, confirm: bool) -> dict:
        rejection = require_permission(PermissionLevel.SAVE, confirm=confirm, file_path=file_path)
        if rejection:
            return rejection
        self._ensure_write()
        if not confirm:
            raise ValidationError("Saving requires confirm=true after the user has reviewed the target path.")
        if file_path:
            target = Path(file_path).expanduser()
            if target.exists() and not target.is_file():
                raise ValidationError(f"Save target is not a file: {target}")
        result = self.adapter.save_document(file_path)
        return {"success": True, "data": result}

    def audit_drawing(self, sample_limit: int = 30) -> dict:
        safe_limit = min(max(0, sample_limit), 100)
        return {"success": True, "data": self.adapter.audit_drawing(safe_limit)}

    def list_layers(self, detail: bool = True) -> dict:
        layers = self.adapter.list_layers(detail)
        return {"success": True, "count": len(layers), "data": layers}

    def ensure_layers(self, layers: list[LayerSpec], dry_run: bool = True, confirm: bool = False) -> dict:
        self._limit(layers, "layers")
        existing = {item["name"].lower(): item for item in self.adapter.list_layers(detail=True)}
        plan = []
        for spec in layers:
            current = existing.get(spec.name.lower())
            desired = spec.model_dump(exclude_none=True)
            if current is None:
                plan.append({"name": spec.name, "operation": "create", "desired": desired})
                continue
            changes = {
                key: value
                for key, value in desired.items()
                if key != "name" and current.get(key) != value
            }
            plan.append(
                {
                    "name": spec.name,
                    "operation": "update" if changes else "unchanged",
                    "changes": changes,
                    "current": current,
                }
            )
        if dry_run:
            return {"success": True, "dry_run": True, "planned": plan}
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        self._ensure_write()
        return {"success": True, "dry_run": False, **self._summary(self.adapter.ensure_layers(layers))}

    def get_selected_entities(self, limit: int = 200) -> dict:
        safe_limit = min(max(1, limit), self.settings.max_query_results)
        entities = self.adapter.get_selected_entities(safe_limit)
        return {
            "success": True,
            "count": len(entities),
            "truncated": len(entities) >= safe_limit,
            "data": entities,
        }

    def query_entities(self, query: EntityQuerySpec) -> dict:
        query.limit = min(query.limit, self.settings.max_query_results)
        entities = self.adapter.query_entities(query)
        return {
            "success": True,
            "count": len(entities),
            "truncated": len(entities) >= query.limit,
            "data": entities,
        }

    def get_entity_details(self, handles: list[str]) -> dict:
        self._limit(handles, "handles")
        return {"success": True, **self._summary(self.adapter.get_entity_details(handles))}

    def update_entity_properties(self, patch: EntityPropertyPatch, dry_run: bool = True, confirm: bool = False) -> dict:
        self._limit(patch.handles, "handles")
        properties = patch.model_dump(exclude={"handles"}, exclude_none=True)
        current = self.adapter.get_entity_details(patch.handles)
        plan = []
        for item in current:
            if not item.get("success"):
                plan.append(item)
                continue
            changes = {}
            for key, value in properties.items():
                current_key = {
                    "layer": "layer",
                    "color": "Color",
                    "linetype": "Linetype",
                    "linetype_scale": "LinetypeScale",
                    "lineweight": "Lineweight",
                    "visible": "visible",
                }[key]
                if item.get(current_key) != value:
                    changes[key] = {"from": item.get(current_key), "to": value}
            plan.append({"success": True, "handle": item["handle"], "changes": changes})
        if dry_run:
            return {"success": True, "dry_run": True, "planned": plan}
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        self._ensure_write()
        results = self.adapter.update_entity_properties(patch.handles, properties)
        return {"success": True, "dry_run": False, **self._summary(results)}

    def normalize_selected_entities(
        self,
        target_layer: str | None,
        set_color_bylayer: bool,
        set_linetype_bylayer: bool,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        selected = self.adapter.get_selected_entities(self.settings.max_batch_size)
        if not selected:
            raise ValidationError("No preselected entities were found in ZWCAD.")
        handles = [item["handle"] for item in selected if item.get("handle")]
        properties: dict[str, Any] = {}
        if target_layer:
            properties["layer"] = target_layer
        if set_color_bylayer:
            properties["color"] = 256
        if set_linetype_bylayer:
            properties["linetype"] = "ByLayer"
        if not properties:
            raise ValidationError("No normalization properties were requested.")
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "selected_count": len(handles),
                "target_properties": properties,
                "entities": selected,
            }
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        self._ensure_write()
        if target_layer:
            existing = {item["name"].lower() for item in self.adapter.list_layers(detail=False)}
            if target_layer.lower() not in existing:
                self.adapter.ensure_layers([LayerSpec(name=target_layer)])
        results = self.adapter.update_entity_properties(handles, properties)
        return {"success": True, "dry_run": False, **self._summary(results)}

    def transform_entities(self, request: TransformRequest, dry_run: bool = True, confirm: bool = False) -> dict:
        self._limit(request.handles, "handles")
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "action": request.action,
                "params": request.params,
                "entities": self.adapter.get_entity_details(request.handles),
            }
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        self._ensure_write()
        results = self.adapter.transform_entities(request.action, request.handles, request.params)
        return {"success": True, "dry_run": False, **self._summary(results)}

    def delete_entities(self, handles: list[str], dry_run: bool = True, confirm: bool = False, second_confirm: bool = False) -> dict:
        self._limit(handles, "handles")
        current = self.adapter.get_entity_details(handles)
        if dry_run:
            return {"success": True, "dry_run": True, "entities_to_delete": current}
        rejection = require_permission(PermissionLevel.DELETE, confirm=confirm, second_confirm=second_confirm)
        if rejection:
            return rejection
        self._ensure_write()
        if not confirm:
            raise ValidationError("Deleting entities requires confirm=true after previewing the handles.")
        results = self.adapter.delete_entities(handles)
        return {"success": True, "dry_run": False, **self._summary(results)}

    def create_entities(self, entities: list[EntityCreateSpec], dry_run: bool = True, confirm: bool = False) -> dict:
        self._limit(entities, "entities")
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "entity_count": len(entities),
                "planned": [item.model_dump() for item in entities],
            }
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        self._ensure_write()
        results = self.adapter.create_entities(entities)
        return {"success": True, "dry_run": False, **self._summary(results)}

    def list_layouts(self) -> dict:
        layouts = self.adapter.list_layouts()
        return {"success": True, "count": len(layouts), "data": layouts}

    def get_layout_plot_settings(self, layout_name: str | None = None) -> dict:
        return {"success": True, "data": self.adapter.get_layout_plot_settings(layout_name)}

    def activate_layout(self, name: str) -> dict:
        return {"success": True, "data": self.adapter.activate_layout(name)}

    def plot_layouts(
        self,
        layout_names: list[str],
        output_dir: str,
        plot_configuration: str | None,
        extension: str,
        dry_run: bool = True,
        confirm: bool = False,
    ) -> dict:
        self._limit(layout_names, "layout_names")
        available = {item["name"] for item in self.adapter.list_layouts()}
        missing = [name for name in layout_names if name not in available]
        if missing:
            raise ValidationError(f"Unknown layouts: {', '.join(missing)}")
        if dry_run:
            document = self.adapter.get_current_document()
            stem = Path(document.get("name") or "drawing").stem
            planned = [
                {
                    "layout": name,
                    "file_path": str(Path(output_dir) / f"{stem}-{name}.{extension.lstrip('.')}")
                }
                for name in layout_names
            ]
            return {"success": True, "dry_run": True, "planned": planned}
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        self._ensure_write()
        results = self.adapter.plot_layouts(
            layout_names, output_dir, plot_configuration, extension.lstrip(".")
        )
        return {"success": True, "dry_run": False, **self._summary(results)}

    def export_drawing(self, base_file_path: str, extension: str, dry_run: bool = True, confirm: bool = False) -> dict:
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "base_file_path": base_file_path,
                "extension": extension.upper(),
            }
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        self._ensure_write()
        return {"success": True, "dry_run": False, "data": self.adapter.export_drawing(base_file_path, extension)}

    def verify_export_files(self, file_paths: list[str]) -> dict:
        if not file_paths:
            raise ValidationError("file_paths cannot be empty.")
        return {"success": True, "data": self.adapter.verify_export_files(file_paths)}

    def list_block_definitions(self, detail: bool = False) -> dict:
        blocks = self.adapter.list_block_definitions(detail)
        return {"success": True, "count": len(blocks), "data": blocks}

    def list_block_references(
        self,
        scope: str,
        block_name: str | None,
        has_attributes: bool | None,
        limit: int,
    ) -> dict:
        safe_limit = min(max(1, limit), self.settings.max_query_results)
        refs = self.adapter.list_block_references(
            scope, block_name, has_attributes, safe_limit
        )
        return {
            "success": True,
            "count": len(refs),
            "truncated": len(refs) >= safe_limit,
            "data": refs,
        }

    def get_block_attributes(self, handles: list[str]) -> dict:
        self._limit(handles, "handles")
        return {"success": True, **self._summary(self.adapter.get_block_attributes(handles))}

    def update_block_attributes(
        self, updates: list[BlockAttributePatch], dry_run: bool = True, confirm: bool = False
    ) -> dict:
        self._limit(updates, "updates")
        current = {
            item.get("handle"): item
            for item in self.adapter.get_block_attributes([item.handle for item in updates])
        }
        plan = []
        for update in updates:
            current_item = current.get(update.handle, {})
            attrs = {
                attr["tag"].upper(): attr.get("text", "")
                for attr in current_item.get("attributes", [])
            }
            requested = {tag.upper(): value for tag, value in update.attributes.items()}
            changes = [
                {"tag": tag, "from": attrs.get(tag), "to": value}
                for tag, value in requested.items()
                if attrs.get(tag) != value
            ]
            unmatched = sorted(tag for tag in requested if tag not in attrs)
            plan.append(
                {
                    "handle": update.handle,
                    "block_name": current_item.get("block_name"),
                    "changes": changes,
                    "unmatched_tags": unmatched,
                    "read_error": current_item.get("error"),
                }
            )
        if dry_run:
            return {"success": True, "dry_run": True, "planned": plan}
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        self._ensure_write()
        results = self.adapter.update_block_attributes(
            [item.model_dump() for item in updates]
        )
        return {"success": True, "dry_run": False, **self._summary(results)}

    def insert_blocks(self, blocks: list[dict[str, Any]], dry_run: bool = True, confirm: bool = False) -> dict:
        self._limit(blocks, "blocks")
        for index, item in enumerate(blocks):
            for field in ("name", "insertion_point"):
                if field not in item:
                    raise ValidationError(f"blocks[{index}] is missing '{field}'.")
        if dry_run:
            return {"success": True, "dry_run": True, "planned": blocks}
        rejection = require_permission(PermissionLevel.MODIFY, confirm=confirm)
        if rejection:
            return rejection
        self._ensure_write()
        results = self.adapter.insert_blocks(blocks)
        return {"success": True, "dry_run": False, **self._summary(results)}
