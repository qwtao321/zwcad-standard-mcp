from __future__ import annotations

import copy
import itertools
from pathlib import Path
from typing import Any

from zwcad_standard_mcp.errors import EntityNotFoundError, ValidationError
from zwcad_standard_mcp.models import (
    EntityCreateSpec,
    EntityQuerySpec,
    LayerSpec,
    PlotScopeRequest,
)


from .base import CadAdapter


class FakeCadAdapter(CadAdapter):
    """Deterministic in-memory adapter for tests and MCP schema inspection."""

    def __init__(self) -> None:
        self._handles = itertools.count(100)
        self.document = {
            "name": "sample.dwg",
            "full_name": "C:/drawings/sample.dwg",
            "path": "C:/drawings",
            "saved": True,
            "readonly": False,
            "active_layout": "Model",
        }
        self._documents = [self.document]
        self.layers = {
            "0": {"name": "0", "color": 7, "linetype": "Continuous", "on": True, "locked": False, "frozen": False},
            "OUTLINE": {"name": "OUTLINE", "color": 7, "linetype": "Continuous", "on": True, "locked": False, "frozen": False},
            "DIM": {"name": "DIM", "color": 2, "linetype": "Continuous", "on": True, "locked": False, "frozen": False},
        }
        self.layouts = [
            {"name": "Model", "tab_order": 0, "model_space": True, "active": True},
            {"name": "Layout1", "tab_order": 1, "model_space": False, "active": False},
        ]
        self.entities: dict[str, dict[str, Any]] = {
            "10": {"handle": "10", "object_name": "AcDbLine", "entity_type": "line", "layer": "0", "StartPoint": [0, 0, 0], "EndPoint": [100, 0, 0], "layout": "Model"},
            "11": {"handle": "11", "object_name": "AcDbCircle", "entity_type": "circle", "layer": "OUTLINE", "Center": [50, 50, 0], "Radius": 10, "layout": "Model"},
            "12": {
                "handle": "12",
                "object_name": "AcDbBlockReference",
                "entity_type": "block_reference",
                "layer": "0",
                "layout": "Layout1",
                "block_name": "A3_TITLE_BLOCK",
                "has_attributes": True,
                "insertion_point": [0, 0, 0],
                "attributes": [
                    {"tag": "DESIGNER", "text": "Alice", "handle": "A1", "constant": False},
                    {"tag": "DATE", "text": "", "handle": "A2", "constant": False},
                ],
            },
        }
        self.selected_handles = ["10", "11"]
        self.block_definitions = [
            {"name": "A3_TITLE_BLOCK", "entity_count": 12, "is_layout": False, "is_xref": False},
        ]
        self.undo_depth = 0

    def _entity(self, handle: str) -> dict[str, Any]:
        try:
            return self.entities[handle]
        except KeyError as exc:
            raise EntityNotFoundError(f"Entity handle not found: {handle}") from exc

    def diagnose(self) -> dict:
        return {
            "success": True,
            "connected": True,
            "checks": [
                {"name": "com_connection", "ok": True, "prog_id": "FAKE"},
                {"name": "active_document", "ok": True, "document": self.get_current_document()},
            ],
        }

    def get_app_info(self) -> dict:
        return {"prog_id": "FAKE", "version": "2026", "path": "C:/Program Files/ZWCAD/zwcad.exe", "visible": True, "caption": "ZWCAD"}

    def get_current_document(self) -> dict:
        return copy.deepcopy(self.document)

    def list_documents(self) -> list[dict]:
        return [copy.deepcopy(doc) for doc in self._documents]

    def scan_cad_folder(self, path: str, recursive: bool = False) -> dict:
        root = Path(path)
        files = [
            {"name": "A001.dwg", "path": str(root / "A001.dwg")},
            {"name": "A002.dwg", "path": str(root / "A002.dwg")},
        ]
        return {
            "folder": str(root),
            "recursive": recursive,
            "count": len(files),
            "files": files,
        }

    def open_document(self, path: str, read_only: bool = False) -> dict:
        target = Path(path)
        new_doc = {
            "name": target.name,
            "full_name": str(target),
            "path": str(target.parent),
            "saved": True,
            "readonly": read_only,
            "active_layout": "Model",
        }
        self._documents.append(new_doc)
        return copy.deepcopy(new_doc)

    def close_document(self, name: str, save_changes: bool = False) -> dict:
        for index, doc in enumerate(self._documents):
            if doc["name"] == name:
                self._documents.pop(index)
                if self._documents:
                    self.document = self._documents[-1]
                return {"closed": True, "name": name, "save_changes": save_changes}
        raise ValidationError(f"Document not found: {name}")

    def activate_document(self, name: str) -> dict:
        for doc in self._documents:
            if doc["name"] == name:
                self.document = doc
                return self.get_current_document()
        raise ValidationError(f"Document not found: {name}")

    def save_document(self, file_path: str | None = None) -> dict:
        if file_path:
            self.document["full_name"] = file_path
            self.document["name"] = Path(file_path).name
        self.document["saved"] = True
        return {"saved": True, "file_path": self.document["full_name"]}

    def list_layers(self, detail: bool = True) -> list[dict]:
        results = []
        for item in self.layers.values():
            data = copy.deepcopy(item)
            if not detail:
                data = {"name": data["name"], "color": data["color"]}
            results.append(data)
        return results

    def ensure_layers(self, layers: list[LayerSpec]) -> list[dict]:
        results = []
        for spec in layers:
            existing = next((name for name in self.layers if name.lower() == spec.name.lower()), None)
            created = existing is None
            key = spec.name if created else existing
            if created:
                self.layers[key] = {"name": spec.name, "color": 7, "linetype": "Continuous", "on": True, "locked": False, "frozen": False}
            updated = []
            for field in ("color", "linetype", "on", "locked", "frozen"):
                value = getattr(spec, field)
                if value is not None:
                    self.layers[key][field] = value
                    updated.append(field)
            results.append({"name": spec.name, "success": True, "created": created, "updated_properties": updated})
        return results

    def audit_drawing(self, sample_limit: int) -> dict:
        type_counts: dict[str, int] = {}
        layer_counts: dict[str, int] = {}
        block_counts: dict[str, int] = {}
        for entity in self.entities.values():
            type_counts[entity["entity_type"]] = type_counts.get(entity["entity_type"], 0) + 1
            layer_counts[entity["layer"]] = layer_counts.get(entity["layer"], 0) + 1
            if entity["entity_type"] == "block_reference":
                block_counts[entity["block_name"]] = block_counts.get(entity["block_name"], 0) + 1
        return {
            "document": self.get_current_document(),
            "entity_total": len(self.entities),
            "entity_types": type_counts,
            "entities_by_layer": layer_counts,
            "block_references": block_counts,
            "layer_count": len(self.layers),
            "layout_count": len(self.layouts),
            "sample_entities": list(copy.deepcopy(self.entities.values()))[:sample_limit],
        }

    def get_selected_entities(self, limit: int) -> list[dict]:
        results = []
        for handle in self.selected_handles[:limit]:
            entity = copy.deepcopy(self._entity(handle))
            entity["space"] = entity.get("layout", "Model")
            entity["bounding_box"] = self._fake_bounds(entity)
            results.append(entity)
        return results

    def _fake_bounds(self, entity: dict) -> dict:
        et = entity.get("entity_type", "")
        if et == "line":
            sp = entity.get("StartPoint", [0, 0, 0])
            ep = entity.get("EndPoint", [0, 0, 0])
            return {"min": [min(sp[0], ep[0]), min(sp[1], ep[1]), 0.0], "max": [max(sp[0], ep[0]), max(sp[1], ep[1]), 0.0]}
        if et == "circle":
            c = entity.get("Center", [0, 0, 0])
            r = entity.get("Radius", 0)
            return {"min": [c[0] - r, c[1] - r, 0.0], "max": [c[0] + r, c[1] + r, 0.0]}
        return {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 0.0]}

    def query_entities(self, query: EntityQuerySpec) -> list[dict]:
        results = []
        for entity in self.entities.values():
            if query.scope == "model" and entity.get("layout") != "Model":
                continue
            if query.scope == "paper" and entity.get("layout") == "Model":
                continue
            if query.entity_type and entity["entity_type"].lower() != query.entity_type.lower():
                continue
            if query.layer and entity["layer"].lower() != query.layer.lower():
                continue
            if query.block_name and entity.get("block_name", "").lower() != query.block_name.lower():
                continue
            if query.text_contains and query.text_contains.lower() not in entity.get("text", "").lower():
                continue
            results.append(copy.deepcopy(entity))
            if len(results) >= query.limit:
                break
        return results

    def get_entity_details(self, handles: list[str]) -> list[dict]:
        results = []
        for handle in handles:
            try:
                results.append({"success": True, **copy.deepcopy(self._entity(handle))})
            except Exception as exc:
                results.append({"success": False, "handle": handle, "error": str(exc)})
        return results

    def update_entity_properties(self, handles: list[str], properties: dict[str, Any]) -> list[dict]:
        results = []
        for handle in handles:
            try:
                entity = self._entity(handle)
                before = copy.deepcopy(entity)
                for key, value in properties.items():
                    if value is not None:
                        entity[key] = value
                results.append({"success": True, "handle": handle, "before": before, "after": copy.deepcopy(entity), "changed": [k for k, v in properties.items() if v is not None]})
            except Exception as exc:
                results.append({"success": False, "handle": handle, "error": str(exc)})
        return results

    def transform_entities(self, action: str, handles: list[str], params: dict[str, Any]) -> list[dict]:
        results = []
        for handle in handles:
            try:
                entity = self._entity(handle)
                item = {"success": True, "handle": handle, "action": action}
                if action in {"copy", "mirror"}:
                    new_handle = str(next(self._handles))
                    self.entities[new_handle] = copy.deepcopy(entity)
                    self.entities[new_handle]["handle"] = new_handle
                    item["new_handle"] = new_handle
                    if action == "mirror" and not params.get("keep_original", True):
                        del self.entities[handle]
                results.append(item)
            except Exception as exc:
                results.append({"success": False, "handle": handle, "action": action, "error": str(exc)})
        return results

    def delete_entities(self, handles: list[str]) -> list[dict]:
        results = []
        for handle in handles:
            try:
                deleted = self.entities.pop(handle)
                results.append({"success": True, "handle": handle, "deleted": deleted})
            except KeyError:
                results.append({"success": False, "handle": handle, "error": "not found"})
        return results

    def create_entities(self, entities: list[EntityCreateSpec]) -> list[dict]:
        results = []
        for index, spec in enumerate(entities):
            handle = str(next(self._handles))
            self.entities[handle] = {
                "handle": handle,
                "object_name": f"Fake{spec.entity_type}",
                "entity_type": spec.entity_type,
                "layer": spec.layer,
                "layout": "Model",
                **copy.deepcopy(spec.params),
            }
            results.append({"success": True, "index": index, "entity_type": spec.entity_type, "handle": handle, "layer": spec.layer})
        return results

    def list_layouts(self) -> list[dict]:
        return copy.deepcopy(self.layouts)

    def get_layout_plot_settings(self, layout_name: str | None) -> dict:
        name = layout_name or self.document.get("active_layout", "Model")
        for layout in self.layouts:
            if layout["name"] == name:
                return {
                    "name": layout["name"],
                    "config_name": "DWG To PDF.pc3",
                    "canonical_media_name": "A3",
                    "plot_device": "DWG To PDF.pc3",
                    "plot_type": "layout" if not layout.get("model_space") else "display",
                    "paper_units": "millimeters",
                    "plot_scale": [1, 1],
                    "std_scale_name": "1:1",
                    "std_scale": 1.0,
                    "plot_rotation": "0_degrees",
                    "plot_origin": [0, 0],
                    "center_plot": True,
                    "plot_hidden": False,
                    "plot_with_lineweights": True,
                    "plot_with_plot_styles": False,
                    "scale_lineweights": False,
                    "use_standard_scale": True,
                    "plot_style_sheet": "",
                    "style_sheet": "",
                    "window_lower_left": [0.0, 0.0, 0.0],
                    "window_upper_right": [10.0, 10.0, 0.0],
                }
        raise ValidationError(f"Layout not found: {layout_name}")

    def get_plot_capabilities(self) -> dict:
        return {
            "devices": ["DWG To PDF.pc3", "ZWCAD PDF.pc3"],
            "default_device": "DWG To PDF.pc3",
            "paper_sizes": ["A0", "A1", "A2", "A3", "A4"],
            "supported_extensions": ["pdf", "dwf", "dwfx", "dxf", "png", "jpg", "jpeg"],
            "note": "Fake adapter returns a fixed capability list.",
        }

    def preview_plot_scope(self, request: PlotScopeRequest) -> dict:
        scope_type = request.scope_type or "layout"
        if scope_type == "window":
            mn = request.window_lower_left or [0.0, 0.0, 0.0]
            mx = request.window_upper_right or [10.0, 10.0, 0.0]
            bounds = {"min": mn, "max": mx}
        elif scope_type == "extents":
            bounds = self.get_drawing_extents()
        elif scope_type == "display":
            bounds = self.get_current_view().get("bounds", {"min": [0, 0, 0], "max": [10, 10, 0]})
        else:
            bounds = {"min": [0.0, 0.0, 0.0], "max": [420.0, 297.0, 0.0]}
        return {
            "layout": request.layout_name or self.document.get("active_layout", "Model"),
            "scope_type": scope_type,
            "bounds": bounds,
            "drawing_extents": self.get_drawing_extents(),
            "clipping_risk": False,
            "layout_settings": self.get_layout_plot_settings(request.layout_name),
        }

    def get_current_view(self) -> dict:
        return {"type": "viewport", "center": [50.0, 50.0, 0.0], "height": 100.0, "width": 100.0, "bounds": {"min": [0, 0, 0], "max": [100, 100, 0]}, "twist_angle": 0.0}

    def get_drawing_extents(self) -> dict:
        bounds = [self._fake_bounds(e) for e in self.entities.values()]
        if not bounds:
            return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}
        min_vals = [min(b["min"][i] for b in bounds) for i in range(3)]
        max_vals = [max(b["max"][i] for b in bounds) for i in range(3)]
        return {"min": min_vals, "max": max_vals}

    def activate_layout(self, name: str) -> dict:
        if name not in {item["name"] for item in self.layouts}:
            raise ValidationError(f"Layout not found: {name}")
        for item in self.layouts:
            item["active"] = item["name"] == name
        self.document["active_layout"] = name
        return {"active_layout": name}

    def plot_layouts(
        self,
        layout_names: list[str],
        output_dir: str,
        plot_configuration: str | None,
        extension: str,
        scope_type: str | None = None,
        window_lower_left: list[float] | None = None,
        window_upper_right: list[float] | None = None,
        selected_handles: list[str] | None = None,
        center_plot: bool | None = None,
        fit_to_paper: bool | None = None,
        custom_scale: float | None = None,
        override_policy: str = "temporary",
    ) -> list[dict]:
        return [
            {
                "success": True,
                "layout": name,
                "file_path": str(Path(output_dir) / f"sample-{name}.{extension}"),
                "plot_configuration": plot_configuration or "DWG To PDF.pc3",
                "scope_applied": scope_type is not None,
            }
            for name in layout_names
        ]

    def export_drawing(self, base_file_path: str, extension: str) -> dict:
        return {"success": True, "base_file_path": base_file_path, "extension": extension.upper()}

    def verify_export_files(
        self,
        file_paths: list[str],
        layout_names: list[str] | None = None,
        min_size_bytes: int = 1024,
        expected_plot_range: dict[str, list[float]] | None = None,
    ) -> dict:
        results = []
        for raw_path in file_paths:
            path = Path(raw_path)
            item = {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "extension": path.suffix.lower(),
                "layout_check": None,
                "size_check": None,
                "range_check": None,
                "signature_ok": False,
                "detected_format": None,
            }
            if item["exists"]:
                item["signature_ok"] = True
                item["detected_format"] = path.suffix.upper().lstrip(".") or "unknown"
                item["size_check"] = item["size_bytes"] >= min_size_bytes
                if layout_names is not None:
                    item["layout_check"] = any(layout in path.stem for layout in layout_names)
                if expected_plot_range is not None:
                    area = 0.0
                    mn = expected_plot_range.get("min", [0, 0, 0])
                    mx = expected_plot_range.get("max", [0, 0, 0])
                    if len(mn) >= 2 and len(mx) >= 2:
                        area = max(0.0, (mx[0] - mn[0]) * (mx[1] - mn[1]))
                    item["range_check"] = area > 0.0
            else:
                item["error"] = "file not found"
                item["size_check"] = False
                if layout_names is not None:
                    item["layout_check"] = False
                item["range_check"] = False
            results.append(item)
        existing = [r for r in results if r["exists"]]
        verified = [r for r in results if r.get("signature_ok") and r.get("size_check") and r.get("layout_check") is not False and r.get("range_check") is not False]
        return {
            "total": len(results),
            "existing": len(existing),
            "verified": len(verified),
            "missing": [r["path"] for r in results if not r["exists"]],
            "failed": [r["path"] for r in results if r["exists"] and r not in verified],
            "results": results,
        }

    def list_block_definitions(self, detail: bool) -> list[dict]:
        return copy.deepcopy(self.block_definitions)

    def list_block_references(self, scope: str, block_name: str | None, has_attributes: bool | None, limit: int) -> list[dict]:
        query = EntityQuerySpec(scope=scope, entity_type="block_reference", block_name=block_name, limit=limit)
        results = self.query_entities(query)
        if has_attributes is not None:
            results = [item for item in results if bool(item.get("has_attributes")) == has_attributes]
        return results

    def get_block_attributes(self, handles: list[str]) -> list[dict]:
        results = []
        for handle in handles:
            try:
                entity = self._entity(handle)
                if entity["entity_type"] != "block_reference":
                    raise ValidationError("not a block reference")
                results.append({"success": True, "handle": handle, "block_name": entity["block_name"], "attributes": copy.deepcopy(entity.get("attributes", []))})
            except Exception as exc:
                results.append({"success": False, "handle": handle, "error": str(exc)})
        return results

    def update_block_attributes(self, updates: list[dict[str, Any]]) -> list[dict]:
        results = []
        for update in updates:
            handle = str(update["handle"])
            try:
                entity = self._entity(handle)
                requested = {str(k).upper(): str(v) for k, v in update["attributes"].items()}
                changed = []
                unmatched = set(requested)
                for attr in entity.get("attributes", []):
                    tag = attr["tag"].upper()
                    if tag in requested:
                        old = attr["text"]
                        attr["text"] = requested[tag]
                        changed.append({"tag": tag, "old_value": old, "new_value": requested[tag]})
                        unmatched.discard(tag)
                results.append({"success": True, "handle": handle, "block_name": entity["block_name"], "changed": changed, "unmatched_tags": sorted(unmatched), "verified_attributes": copy.deepcopy(entity.get("attributes", []))})
            except Exception as exc:
                results.append({"success": False, "handle": handle, "error": str(exc)})
        return results

    def insert_blocks(self, blocks: list[dict[str, Any]]) -> list[dict]:
        results = []
        for index, item in enumerate(blocks):
            handle = str(next(self._handles))
            attributes = [{"tag": tag, "text": str(value), "handle": "", "constant": False} for tag, value in item.get("attributes", {}).items()]
            self.entities[handle] = {
                "handle": handle,
                "object_name": "AcDbBlockReference",
                "entity_type": "block_reference",
                "layer": item.get("layer", "0"),
                "layout": "Model",
                "block_name": item["name"],
                "has_attributes": bool(attributes),
                "attributes": attributes,
                "insertion_point": item["insertion_point"],
            }
            results.append({"success": True, "index": index, "handle": handle, "block_name": item["name"]})
        return results

    def begin_undo(self) -> None:
        self.undo_depth += 1

    def end_undo(self) -> None:
        self.undo_depth = max(0, self.undo_depth - 1)
