from __future__ import annotations

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
