from __future__ import annotations

import contextlib
import math
import os
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator

from zwcad_standard_mcp.errors import (
    CadConnectionError,
    EntityNotFoundError,
    NoActiveDocumentError,
    UnsupportedOperationError,
    ValidationError,
)
from zwcad_standard_mcp.models import EntityCreateSpec, EntityQuerySpec, LayerSpec

from .base import CadAdapter


_OBJECT_ALIASES = {
    "line": {"acdbline", "line"},
    "circle": {"acdbcircle", "circle"},
    "arc": {"acdbarc", "arc"},
    "lwpolyline": {"acdpolyline", "acdblwpolyline", "lwpolyline", "polyline"},
    "polyline": {"acdb2dpolyline", "acdb3dpolyline", "polyline"},
    "text": {"acdbtext", "text"},
    "mtext": {"acdbmtext", "mtext"},
    "block_reference": {"acdbblockreference", "blockreference", "insert"},
    "dimension": {
        "acdbaligneddimension",
        "acdbrotateddimension",
        "acdbdiametricdimension",
        "acdbradialdimension",
        "acdb3pointangulardimension",
    },
}


class ComCadAdapter(CadAdapter):
    """ZWCAD Standard adapter using the public ActiveX/COM automation interface."""

    def __init__(self, prog_id: str = "ZWCAD.Application", auto_start: bool = False) -> None:
        self.prog_id = prog_id
        self.auto_start = auto_start
        self._app: Any | None = None
        self._pythoncom: Any | None = None
        self._win32_client: Any | None = None

    def _load_win32(self) -> None:
        if sys.platform != "win32":
            raise CadConnectionError("ZWCAD COM adapter can only run on Windows.")
        if self._pythoncom is not None:
            return
        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise CadConnectionError(
                "pywin32 is not installed. Run: pip install pywin32"
            ) from exc
        self._pythoncom = pythoncom
        self._win32_client = win32com.client

    def _initialize_com(self) -> None:
        self._load_win32()
        try:
            self._pythoncom.CoInitialize()
        except Exception:
            pass

    def _connect(self, force: bool = False) -> Any:
        self._initialize_com()
        if self._app is not None and not force:
            try:
                _ = self._app.Version
                return self._app
            except Exception:
                self._app = None

        try:
            self._app = self._win32_client.GetActiveObject(self.prog_id)
        except Exception as first_error:
            if not self.auto_start:
                raise CadConnectionError(
                    f"Cannot connect to a running ZWCAD instance via '{self.prog_id}'. "
                    "Start ZWCAD and open a DWG first, or set ZWCAD_MCP_AUTO_START=true."
                ) from first_error
            try:
                self._app = self._win32_client.Dispatch(self.prog_id)
                self._app.Visible = True
            except Exception as second_error:
                raise CadConnectionError(
                    f"Cannot start ZWCAD via COM ProgID '{self.prog_id}'."
                ) from second_error
        return self._app

    def _doc(self) -> Any:
        app = self._connect()
        try:
            doc = app.ActiveDocument
        except Exception as exc:
            raise NoActiveDocumentError("ZWCAD has no active document.") from exc
        if doc is None:
            raise NoActiveDocumentError("ZWCAD has no active document.")
        return doc

    @staticmethod
    def _safe_get(obj: Any, name: str, default: Any = None) -> Any:
        try:
            return getattr(obj, name)
        except Exception:
            return default

    @classmethod
    def _json_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        if isinstance(value, dict):
            return {str(k): cls._json_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_value(v) for v in value]
        try:
            return [cls._json_value(v) for v in value]
        except Exception:
            return str(value)

    def _point(self, values: Iterable[float]) -> Any:
        coords = list(values)
        while len(coords) < 3:
            coords.append(0.0)
        return self._win32_client.VARIANT(
            self._pythoncom.VT_ARRAY | self._pythoncom.VT_R8,
            tuple(float(v) for v in coords[:3]),
        )

    def _double_array(self, values: Iterable[float]) -> Any:
        return self._win32_client.VARIANT(
            self._pythoncom.VT_ARRAY | self._pythoncom.VT_R8,
            tuple(float(v) for v in values),
        )

    @staticmethod
    def _iter_collection(collection: Any) -> Iterator[Any]:
        try:
            for item in collection:
                yield item
            return
        except Exception:
            pass
        count = int(getattr(collection, "Count", 0))
        for index in range(count):
            try:
                yield collection.Item(index)
            except Exception:
                yield collection.Item(index + 1)

    def _entity_type(self, entity: Any) -> str:
        object_name = str(self._safe_get(entity, "ObjectName", type(entity).__name__))
        lowered = object_name.lower()
        for alias, candidates in _OBJECT_ALIASES.items():
            if lowered in candidates:
                return alias
        return object_name

    def _block_name(self, entity: Any) -> str | None:
        for name in ("EffectiveName", "Name"):
            value = self._safe_get(entity, name)
            if value:
                return str(value)
        return None

    def _entity_summary(self, entity: Any, layout: str | None = None) -> dict:
        data = {
            "handle": str(self._safe_get(entity, "Handle", "")),
            "object_name": str(self._safe_get(entity, "ObjectName", "")),
            "entity_type": self._entity_type(entity),
            "layer": str(self._safe_get(entity, "Layer", "")),
        }
        if layout is not None:
            data["layout"] = layout
        if data["entity_type"] == "block_reference":
            data["block_name"] = self._block_name(entity)
            data["has_attributes"] = bool(self._safe_get(entity, "HasAttributes", False))
        for prop, key in (("TextString", "text"), ("Visible", "visible")):
            value = self._safe_get(entity, prop)
            if value is not None:
                data[key] = self._json_value(value)
        return data

    def _entity_details(self, entity: Any, layout: str | None = None) -> dict:
        data = self._entity_summary(entity, layout)
        for prop in (
            "Color",
            "Linetype",
            "LinetypeScale",
            "Lineweight",
            "StartPoint",
            "EndPoint",
            "Center",
            "Radius",
            "Diameter",
            "StartAngle",
            "EndAngle",
            "Area",
            "Length",
            "Height",
            "Rotation",
            "InsertionPoint",
            "Closed",
            "Coordinates",
            "Measurement",
        ):
            value = self._safe_get(entity, prop)
            if value is not None:
                data[prop] = self._json_value(value)
        try:
            min_point, max_point = entity.GetBoundingBox()
            data["bounding_box"] = {
                "min": self._json_value(min_point),
                "max": self._json_value(max_point),
            }
        except Exception:
            pass
        if data.get("entity_type") == "block_reference" and data.get("has_attributes"):
            data["attributes"] = self._read_attributes(entity)
        return data

    def _spaces(self, scope: str) -> Iterator[tuple[str, Any]]:
        doc = self._doc()
        if scope == "model":
            yield "Model", doc.ModelSpace
            return
        if scope == "paper":
            active = self._safe_get(doc, "ActiveLayout")
            name = str(self._safe_get(active, "Name", "Paper"))
            yield name, doc.PaperSpace
            return
        if scope != "all_layouts":
            raise ValidationError(f"Unsupported scope: {scope}")
        yield "Model", doc.ModelSpace
        for layout in self._iter_collection(doc.Layouts):
            name = str(self._safe_get(layout, "Name", ""))
            if name.lower() == "model":
                continue
            block = self._safe_get(layout, "Block")
            if block is not None:
                yield name, block

    def _handle_to_object(self, handle: str) -> Any:
        try:
            return self._doc().HandleToObject(handle)
        except Exception as exc:
            raise EntityNotFoundError(f"Entity handle not found: {handle}") from exc

    def _match_type(self, entity: Any, expected: str | None) -> bool:
        if not expected:
            return True
        actual = self._entity_type(entity).lower()
        expected_lower = expected.lower().strip()
        if expected_lower in _OBJECT_ALIASES:
            return actual == expected_lower
        object_name = str(self._safe_get(entity, "ObjectName", "")).lower()
        return expected_lower in {actual, object_name}

    def _read_attributes(self, block_ref: Any) -> list[dict]:
        try:
            attrs = block_ref.GetAttributes()
        except Exception:
            return []
        results: list[dict] = []
        for attr in attrs or []:
            results.append(
                {
                    "tag": str(self._safe_get(attr, "TagString", "")),
                    "text": str(self._safe_get(attr, "TextString", "")),
                    "handle": str(self._safe_get(attr, "Handle", "")),
                    "constant": bool(self._safe_get(attr, "Constant", False)),
                }
            )
        return results

    @contextlib.contextmanager
    def _undo_group(self) -> Iterator[None]:
        self.begin_undo()
        try:
            yield
        finally:
            self.end_undo()

    def diagnose(self) -> dict:
        checks: list[dict] = []
        try:
            app = self._connect(force=True)
            checks.append({"name": "com_connection", "ok": True, "prog_id": self.prog_id})
        except Exception as exc:
            return {
                "success": False,
                "connected": False,
                "checks": [{"name": "com_connection", "ok": False, "error": str(exc)}],
            }
        try:
            version = str(self._safe_get(app, "Version", "unknown"))
            full_name = str(self._safe_get(app, "FullName", ""))
            checks.append(
                {"name": "application", "ok": True, "version": version, "path": full_name}
            )
        except Exception as exc:
            checks.append({"name": "application", "ok": False, "error": str(exc)})
        try:
            doc_info = self.get_current_document()
            checks.append({"name": "active_document", "ok": True, "document": doc_info})
        except Exception as exc:
            checks.append({"name": "active_document", "ok": False, "error": str(exc)})
        return {
            "success": all(check["ok"] for check in checks),
            "connected": True,
            "checks": checks,
        }

    def get_app_info(self) -> dict:
        app = self._connect()
        return {
            "prog_id": self.prog_id,
            "version": str(self._safe_get(app, "Version", "unknown")),
            "path": str(self._safe_get(app, "FullName", "")),
            "visible": bool(self._safe_get(app, "Visible", True)),
            "caption": str(self._safe_get(app, "Caption", "ZWCAD")),
        }

    def get_current_document(self) -> dict:
        doc = self._doc()
        return {
            "name": str(self._safe_get(doc, "Name", "")),
            "full_name": str(self._safe_get(doc, "FullName", "")),
            "path": str(self._safe_get(doc, "Path", "")),
            "saved": bool(self._safe_get(doc, "Saved", False)),
            "readonly": bool(self._safe_get(doc, "ReadOnly", False)),
            "active_layout": str(self._safe_get(self._safe_get(doc, "ActiveLayout"), "Name", "")),
        }

    def list_documents(self) -> list[dict]:
        app = self._connect()
        results = []
        for doc in self._iter_collection(app.Documents):
            results.append(
                {
                    "name": str(self._safe_get(doc, "Name", "")),
                    "full_name": str(self._safe_get(doc, "FullName", "")),
                    "saved": bool(self._safe_get(doc, "Saved", False)),
                    "readonly": bool(self._safe_get(doc, "ReadOnly", False)),
                }
            )
        return results

    def scan_cad_folder(self, path: str, recursive: bool = False) -> dict:
        root = Path(path).expanduser().resolve()
        if not root.exists():
            raise ValidationError(f"Path does not exist: {path}")
        if not root.is_dir():
            raise ValidationError(f"Path is not a directory: {path}")

        cad_extensions = {".dwg", ".dxf", ".dwt"}
        files = []
        iterator = root.rglob("*") if recursive else root.iterdir()
        for item in iterator:
            if item.is_file() and item.suffix.lower() in cad_extensions:
                files.append({"name": item.name, "path": str(item)})
        files.sort(key=lambda f: f["path"])
        return {
            "folder": str(root),
            "recursive": recursive,
            "count": len(files),
            "files": files,
        }

    def open_document(self, path: str, read_only: bool = False) -> dict:
        app = self._connect()
        target = Path(path).expanduser().resolve()
        if not target.exists():
            raise ValidationError(f"File does not exist: {path}")
        try:
            doc = app.Documents.Open(str(target), read_only)
        except Exception as exc:
            raise ValidationError(f"Cannot open document: {path}") from exc
        return {
            "name": str(self._safe_get(doc, "Name", "")),
            "full_name": str(self._safe_get(doc, "FullName", "")),
            "path": str(self._safe_get(doc, "Path", "")),
            "saved": bool(self._safe_get(doc, "Saved", False)),
            "readonly": bool(self._safe_get(doc, "ReadOnly", False)),
        }

    def close_document(self, name: str, save_changes: bool = False) -> dict:
        app = self._connect()
        try:
            doc = app.Documents.Item(name)
        except Exception as exc:
            raise ValidationError(f"Document not found: {name}") from exc
        try:
            doc.Close(save_changes)
        except Exception as exc:
            raise ValidationError(f"Cannot close document: {name}") from exc
        return {"closed": True, "name": name, "save_changes": save_changes}

    def activate_document(self, name: str) -> dict:
        app = self._connect()
        try:
            doc = app.Documents.Item(name)
            doc.Activate()
        except Exception as exc:
            raise ValidationError(f"Document not found or cannot be activated: {name}") from exc
        return self.get_current_document()

    def save_document(self, file_path: str | None = None) -> dict:
        doc = self._doc()
        if bool(self._safe_get(doc, "ReadOnly", False)):
            raise ValidationError("Current document is read-only.")
        if file_path:
            path = str(Path(file_path).expanduser().resolve())
            doc.SaveAs(path)
        else:
            current = str(self._safe_get(doc, "FullName", ""))
            if not current:
                raise ValidationError("The document has no file path; provide file_path for SaveAs.")
            doc.Save()
            path = current
        return {"saved": True, "file_path": path}

    def list_layers(self, detail: bool = True) -> list[dict]:
        doc = self._doc()
        layers = []
        for layer in self._iter_collection(doc.Layers):
            item = {
                "name": str(self._safe_get(layer, "Name", "")),
                "color": int(self._safe_get(layer, "Color", 0)),
            }
            if detail:
                item.update(
                    {
                        "linetype": str(self._safe_get(layer, "Linetype", "")),
                        "on": bool(self._safe_get(layer, "LayerOn", True)),
                        "locked": bool(self._safe_get(layer, "Lock", False)),
                        "frozen": bool(self._safe_get(layer, "Freeze", False)),
                    }
                )
            layers.append(item)
        return layers

    def ensure_layers(self, layers: list[LayerSpec]) -> list[dict]:
        doc = self._doc()
        existing = {item["name"].lower(): item for item in self.list_layers(detail=True)}
        results: list[dict] = []
        with self._undo_group():
            for spec in layers:
                key = spec.name.lower()
                created = key not in existing
                try:
                    layer = doc.Layers.Add(spec.name) if created else doc.Layers.Item(existing[key]["name"])
                    changes = []
                    if spec.color is not None:
                        layer.Color = spec.color
                        changes.append("color")
                    if spec.linetype is not None:
                        layer.Linetype = spec.linetype
                        changes.append("linetype")
                    if spec.on is not None:
                        layer.LayerOn = spec.on
                        changes.append("on")
                    if spec.locked is not None:
                        layer.Lock = spec.locked
                        changes.append("locked")
                    if spec.frozen is not None:
                        layer.Freeze = spec.frozen
                        changes.append("frozen")
                    results.append(
                        {
                            "name": spec.name,
                            "success": True,
                            "created": created,
                            "updated_properties": changes,
                        }
                    )
                except Exception as exc:
                    results.append({"name": spec.name, "success": False, "error": str(exc)})
        return results

    def audit_drawing(self, sample_limit: int) -> dict:
        doc = self._doc()
        type_counts: Counter[str] = Counter()
        layer_counts: Counter[str] = Counter()
        block_counts: Counter[str] = Counter()
        samples: list[dict] = []
        total = 0
        for layout_name, space in self._spaces("all_layouts"):
            for entity in self._iter_collection(space):
                total += 1
                entity_type = self._entity_type(entity)
                layer = str(self._safe_get(entity, "Layer", ""))
                type_counts[entity_type] += 1
                layer_counts[layer] += 1
                if entity_type == "block_reference":
                    block_counts[self._block_name(entity) or "<unknown>"] += 1
                if len(samples) < sample_limit:
                    samples.append(self._entity_summary(entity, layout_name))
        return {
            "document": self.get_current_document(),
            "entity_total": total,
            "entity_types": dict(type_counts.most_common()),
            "entities_by_layer": dict(layer_counts.most_common()),
            "block_references": dict(block_counts.most_common()),
            "layer_count": int(self._safe_get(doc.Layers, "Count", 0)),
            "layout_count": int(self._safe_get(doc.Layouts, "Count", 0)),
            "sample_entities": samples,
        }

    def get_selected_entities(self, limit: int) -> list[dict]:
        doc = self._doc()
        try:
            selection = doc.PickfirstSelectionSet
        except Exception:
            return []
        results = []
        for index, entity in enumerate(self._iter_collection(selection)):
            if index >= limit:
                break
            results.append(self._entity_summary(entity))
        return results

    def query_entities(self, query: EntityQuerySpec) -> list[dict]:
        results: list[dict] = []
        target_block = query.block_name.lower() if query.block_name else None
        target_text = query.text_contains.lower() if query.text_contains else None
        for layout_name, space in self._spaces(query.scope):
            for entity in self._iter_collection(space):
                if not self._match_type(entity, query.entity_type):
                    continue
                if query.layer and str(self._safe_get(entity, "Layer", "")).lower() != query.layer.lower():
                    continue
                if target_block and (self._block_name(entity) or "").lower() != target_block:
                    continue
                if target_text:
                    text = str(self._safe_get(entity, "TextString", "")).lower()
                    if target_text not in text:
                        continue
                results.append(self._entity_summary(entity, layout_name))
                if len(results) >= query.limit:
                    return results
        return results

    def get_entity_details(self, handles: list[str]) -> list[dict]:
        results = []
        for handle in handles:
            try:
                results.append({"success": True, **self._entity_details(self._handle_to_object(handle))})
            except Exception as exc:
                results.append({"success": False, "handle": handle, "error": str(exc)})
        return results

    def update_entity_properties(self, handles: list[str], properties: dict[str, Any]) -> list[dict]:
        mapping = {
            "layer": "Layer",
            "color": "Color",
            "linetype": "Linetype",
            "linetype_scale": "LinetypeScale",
            "lineweight": "Lineweight",
            "visible": "Visible",
        }
        results = []
        with self._undo_group():
            for handle in handles:
                try:
                    entity = self._handle_to_object(handle)
                    before = self._entity_summary(entity)
                    changed = []
                    for key, value in properties.items():
                        if value is None:
                            continue
                        setattr(entity, mapping[key], value)
                        changed.append(key)
                    update = self._safe_get(entity, "Update")
                    if callable(update):
                        update()
                    results.append(
                        {
                            "success": True,
                            "handle": handle,
                            "changed": changed,
                            "before": before,
                            "after": self._entity_summary(entity),
                        }
                    )
                except Exception as exc:
                    results.append({"success": False, "handle": handle, "error": str(exc)})
        return results

    def transform_entities(self, action: str, handles: list[str], params: dict[str, Any]) -> list[dict]:
        results = []
        with self._undo_group():
            for handle in handles:
                try:
                    entity = self._handle_to_object(handle)
                    new_entity = None
                    if action in {"move", "copy"}:
                        from_point = self._point(params["from"])
                        to_point = self._point(params["to"])
                        target = entity.Copy() if action == "copy" else entity
                        target.Move(from_point, to_point)
                        new_entity = target if action == "copy" else None
                    elif action == "rotate":
                        entity.Rotate(self._point(params["base_point"]), float(params["angle_radians"]))
                    elif action == "scale":
                        entity.ScaleEntity(self._point(params["base_point"]), float(params["factor"]))
                    elif action == "mirror":
                        new_entity = entity.Mirror(self._point(params["point1"]), self._point(params["point2"]))
                        if not bool(params.get("keep_original", True)):
                            entity.Delete()
                    else:
                        raise UnsupportedOperationError(f"Unsupported transform action: {action}")
                    item = {"success": True, "handle": handle, "action": action}
                    if new_entity is not None:
                        item["new_handle"] = str(self._safe_get(new_entity, "Handle", ""))
                    results.append(item)
                except Exception as exc:
                    results.append({"success": False, "handle": handle, "action": action, "error": str(exc)})
        return results

    def delete_entities(self, handles: list[str]) -> list[dict]:
        results = []
        with self._undo_group():
            for handle in handles:
                try:
                    entity = self._handle_to_object(handle)
                    summary = self._entity_summary(entity)
                    entity.Delete()
                    results.append({"success": True, "handle": handle, "deleted": summary})
                except Exception as exc:
                    results.append({"success": False, "handle": handle, "error": str(exc)})
        return results

    @staticmethod
    def _require(params: dict[str, Any], names: Iterable[str], entity_type: str) -> None:
        missing = [name for name in names if name not in params]
        if missing:
            raise ValidationError(
                f"{entity_type} is missing required parameters: {', '.join(missing)}"
            )

    def _apply_layer(self, entity: Any, layer: str) -> None:
        if layer:
            entity.Layer = layer

    def _create_entity(self, space: Any, spec: EntityCreateSpec) -> Any:
        p = spec.params
        et = spec.entity_type
        if et == "line":
            self._require(p, ("start", "end"), et)
            entity = space.AddLine(self._point(p["start"]), self._point(p["end"]))
        elif et == "circle":
            self._require(p, ("center", "radius"), et)
            entity = space.AddCircle(self._point(p["center"]), float(p["radius"]))
        elif et == "arc":
            self._require(p, ("center", "radius", "start_angle", "end_angle"), et)
            entity = space.AddArc(
                self._point(p["center"]),
                float(p["radius"]),
                float(p["start_angle"]),
                float(p["end_angle"]),
            )
        elif et == "lwpolyline":
            self._require(p, ("vertices",), et)
            flattened = []
            for point in p["vertices"]:
                flattened.extend([float(point[0]), float(point[1])])
            entity = space.AddLightWeightPolyline(self._double_array(flattened))
            if "closed" in p:
                entity.Closed = bool(p["closed"])
        elif et == "text":
            self._require(p, ("text", "insertion_point", "height"), et)
            entity = space.AddText(
                str(p["text"]), self._point(p["insertion_point"]), float(p["height"])
            )
            if "rotation" in p:
                entity.Rotation = float(p["rotation"])
        elif et == "mtext":
            self._require(p, ("text", "insertion_point", "width"), et)
            entity = space.AddMText(
                self._point(p["insertion_point"]), float(p["width"]), str(p["text"])
            )
            if "height" in p and hasattr(entity, "Height"):
                entity.Height = float(p["height"])
        elif et == "block":
            self._require(p, ("name", "insertion_point"), et)
            scales = p.get("scale", [1.0, 1.0, 1.0])
            entity = space.InsertBlock(
                self._point(p["insertion_point"]),
                str(p["name"]),
                float(scales[0]),
                float(scales[1]),
                float(scales[2]),
                float(p.get("rotation", 0.0)),
            )
        elif et == "dimension_aligned":
            self._require(p, ("point1", "point2", "text_point"), et)
            entity = space.AddDimAligned(
                self._point(p["point1"]), self._point(p["point2"]), self._point(p["text_point"])
            )
        elif et == "dimension_rotated":
            self._require(p, ("point1", "point2", "text_point", "angle_radians"), et)
            entity = space.AddDimRotated(
                self._point(p["point1"]),
                self._point(p["point2"]),
                self._point(p["text_point"]),
                float(p["angle_radians"]),
            )
        elif et == "dimension_radial":
            self._require(p, ("center", "chord_point", "leader_length"), et)
            entity = space.AddDimRadial(
                self._point(p["center"]),
                self._point(p["chord_point"]),
                float(p["leader_length"]),
            )
        elif et == "dimension_diametric":
            self._require(p, ("chord_point", "far_chord_point", "leader_length"), et)
            entity = space.AddDimDiametric(
                self._point(p["chord_point"]),
                self._point(p["far_chord_point"]),
                float(p["leader_length"]),
            )
        else:
            raise UnsupportedOperationError(f"Unsupported entity type: {et}")
        self._apply_layer(entity, spec.layer)
        return entity

    def create_entities(self, entities: list[EntityCreateSpec]) -> list[dict]:
        space = self._doc().ModelSpace
        results = []
        with self._undo_group():
            for index, spec in enumerate(entities):
                try:
                    entity = self._create_entity(space, spec)
                    results.append(
                        {
                            "success": True,
                            "index": index,
                            "entity_type": spec.entity_type,
                            "handle": str(self._safe_get(entity, "Handle", "")),
                            "layer": spec.layer,
                        }
                    )
                except Exception as exc:
                    results.append(
                        {
                            "success": False,
                            "index": index,
                            "entity_type": spec.entity_type,
                            "error": str(exc),
                        }
                    )
        return results

    def list_layouts(self) -> list[dict]:
        doc = self._doc()
        results = []
        active_name = str(self._safe_get(self._safe_get(doc, "ActiveLayout"), "Name", ""))
        for layout in self._iter_collection(doc.Layouts):
            name = str(self._safe_get(layout, "Name", ""))
            results.append(
                {
                    "name": name,
                    "tab_order": int(self._safe_get(layout, "TabOrder", 0)),
                    "model_space": name.lower() == "model",
                    "active": name == active_name,
                    "config_name": str(self._safe_get(layout, "ConfigName", "")),
                    "canonical_media_name": str(self._safe_get(layout, "CanonicalMediaName", "")),
                    "plot_type": self._safe_get(layout, "PlotType"),
                }
            )
        return sorted(results, key=lambda item: item["tab_order"])

    def get_layout_plot_settings(self, layout_name: str | None) -> dict:
        doc = self._doc()
        try:
            if layout_name:
                layout = doc.Layouts.Item(layout_name)
            else:
                layout = self._safe_get(doc, "ActiveLayout")
            if layout is None:
                raise ValidationError("No active layout or layout not found.")
        except Exception as exc:
            raise ValidationError(f"Layout not found: {layout_name}") from exc

        plot_type_raw = self._safe_get(layout, "PlotType")
        plot_type_map = {
            0: "display",
            1: "extents",
            2: "limits",
            3: "view",
            4: "window",
            5: "layout",
        }
        paper_units_raw = self._safe_get(layout, "PaperUnits")
        paper_units_map = {0: "inches", 1: "millimeters", 2: "pixels"}
        rotation_raw = self._safe_get(layout, "PlotRotation")
        rotation_map = {0: "0_degrees", 1: "90_degrees", 2: "180_degrees", 3: "270_degrees"}

        return {
            "name": str(self._safe_get(layout, "Name", "")),
            "config_name": str(self._safe_get(layout, "ConfigName", "")),
            "canonical_media_name": str(self._safe_get(layout, "CanonicalMediaName", "")),
            "plot_type": plot_type_map.get(plot_type_raw, plot_type_raw),
            "paper_units": paper_units_map.get(paper_units_raw, paper_units_raw),
            "plot_scale": self._json_value(self._safe_get(layout, "PlotScale")),
            "std_scale_name": str(self._safe_get(layout, "StdScaleName", "")),
            "std_scale": self._json_value(self._safe_get(layout, "StdScale")),
            "plot_rotation": rotation_map.get(rotation_raw, rotation_raw),
            "plot_origin": self._json_value(self._safe_get(layout, "PlotOrigin")),
            "center_plot": bool(self._safe_get(layout, "CenterPlot", False)),
            "plot_hidden": bool(self._safe_get(layout, "PlotHidden", False)),
            "plot_with_lineweights": bool(self._safe_get(layout, "PlotWithLineweights", False)),
            "plot_with_plot_styles": bool(self._safe_get(layout, "PlotWithPlotStyles", False)),
            "scale_lineweights": bool(self._safe_get(layout, "ScaleLineweights", False)),
            "use_standard_scale": bool(self._safe_get(layout, "UseStandardScale", False)),
        }

    def activate_layout(self, name: str) -> dict:
        doc = self._doc()
        try:
            layout = doc.Layouts.Item(name)
            doc.ActiveLayout = layout
            if name.lower() != "model":
                doc.ActiveSpace = 0
        except Exception as exc:
            raise ValidationError(f"Layout cannot be activated: {name}") from exc
        return {"active_layout": name}

    def plot_layouts(
        self,
        layout_names: list[str],
        output_dir: str,
        plot_configuration: str | None,
        extension: str,
    ) -> list[dict]:
        doc = self._doc()
        output = Path(output_dir).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        original = str(self._safe_get(self._safe_get(doc, "ActiveLayout"), "Name", ""))
        results = []
        for name in layout_names:
            try:
                self.activate_layout(name)
                safe_name = "".join(c if c not in '<>:"/\\|?*' else "_" for c in name)
                file_path = output / f"{Path(str(self._safe_get(doc, 'Name', 'drawing'))).stem}-{safe_name}.{extension.lstrip('.')}"
                config = plot_configuration or str(
                    self._safe_get(self._safe_get(doc, "ActiveLayout"), "ConfigName", "")
                )
                doc.Plot.PlotToFile(str(file_path), config)
                results.append({"success": True, "layout": name, "file_path": str(file_path), "plot_configuration": config})
            except Exception as exc:
                results.append({"success": False, "layout": name, "error": str(exc)})
        if original:
            try:
                self.activate_layout(original)
            except Exception:
                pass
        return results

    def export_drawing(self, base_file_path: str, extension: str) -> dict:
        doc = self._doc()
        selection_name = f"ZWCAD_MCP_EXPORT_{uuid.uuid4().hex[:8]}"
        selection = None
        try:
            selection = doc.SelectionSets.Add(selection_name)
            selection.Select(5)
            doc.Export(str(Path(base_file_path).expanduser().resolve()), extension.upper(), selection)
            return {"success": True, "base_file_path": base_file_path, "extension": extension.upper()}
        finally:
            if selection is not None:
                try:
                    selection.Delete()
                except Exception:
                    pass

    def verify_export_files(self, file_paths: list[str]) -> dict:
        def _detect_signature(path: Path) -> dict:
            signatures = {
                ".pdf": (b"%PDF", "PDF"),
                ".dxf": (None, "DXF"),  # textual, checked separately
                ".dwg": (b"AC", "DWG"),
                ".step": (b"ISO-10303-21", "STEP"),
                ".stp": (b"ISO-10303-21", "STEP"),
                ".stl": (b"solid ", "STL (ASCII)"),
                ".3mf": (b"PK", "3MF (ZIP)"),
                ".png": (b"\x89PNG", "PNG"),
                ".jpg": (b"\xff\xd8", "JPEG"),
                ".jpeg": (b"\xff\xd8", "JPEG"),
            }
            ext = path.suffix.lower()
            marker, label = signatures.get(ext, (None, ext.upper().lstrip(".") or "unknown"))
            try:
                with open(path, "rb") as fh:
                    head = fh.read(16)
            except Exception as exc:
                return {"signature_ok": False, "detected_format": None, "error": str(exc)}
            if ext == ".dxf":
                is_ascii = head.startswith(b"  0\n") or head.startswith(b"0\n") or b"SECTION" in head[:64]
                return {"signature_ok": is_ascii, "detected_format": "DXF" if is_ascii else "unknown"}
            if marker is None:
                return {"signature_ok": True, "detected_format": label, "note": "no signature check for this extension"}
            ok = head.startswith(marker)
            return {"signature_ok": ok, "detected_format": label if ok else "unknown"}

        results = []
        for raw_path in file_paths:
            path = Path(raw_path).expanduser().resolve()
            item = {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "extension": path.suffix.lower(),
            }
            if item["exists"]:
                item.update(_detect_signature(path))
            else:
                item.update({"signature_ok": False, "detected_format": None, "error": "file not found"})
            results.append(item)

        existing = [r for r in results if r["exists"]]
        verified = [r for r in results if r.get("signature_ok")]
        return {
            "total": len(results),
            "existing": len(existing),
            "verified": len(verified),
            "missing": [r["path"] for r in results if not r["exists"]],
            "failed": [r["path"] for r in results if r["exists"] and not r.get("signature_ok")],
            "results": results,
        }

    def list_block_definitions(self, detail: bool) -> list[dict]:
        doc = self._doc()
        results = []
        for block in self._iter_collection(doc.Blocks):
            item = {
                "name": str(self._safe_get(block, "Name", "")),
                "entity_count": int(self._safe_get(block, "Count", 0)),
                "is_layout": bool(self._safe_get(block, "IsLayout", False)),
                "is_xref": bool(self._safe_get(block, "IsXRef", False)),
            }
            if detail:
                item["origin"] = self._json_value(self._safe_get(block, "Origin"))
                entities = []
                for index, entity in enumerate(self._iter_collection(block)):
                    if index >= 50:
                        item["entities_truncated"] = True
                        break
                    entities.append(self._entity_summary(entity))
                item["entities"] = entities
            results.append(item)
        return results

    def list_block_references(
        self,
        scope: str,
        block_name: str | None,
        has_attributes: bool | None,
        limit: int,
    ) -> list[dict]:
        results = []
        target = block_name.lower() if block_name else None
        for layout_name, space in self._spaces(scope):
            for entity in self._iter_collection(space):
                if self._entity_type(entity) != "block_reference":
                    continue
                actual_name = self._block_name(entity) or ""
                actual_has_attrs = bool(self._safe_get(entity, "HasAttributes", False))
                if target and actual_name.lower() != target:
                    continue
                if has_attributes is not None and actual_has_attrs != has_attributes:
                    continue
                item = self._entity_summary(entity, layout_name)
                item["insertion_point"] = self._json_value(self._safe_get(entity, "InsertionPoint"))
                item["rotation"] = self._safe_get(entity, "Rotation")
                results.append(item)
                if len(results) >= limit:
                    return results
        return results

    def get_block_attributes(self, handles: list[str]) -> list[dict]:
        results = []
        for handle in handles:
            try:
                block_ref = self._handle_to_object(handle)
                if self._entity_type(block_ref) != "block_reference":
                    raise ValidationError(f"Handle {handle} is not a block reference.")
                results.append(
                    {
                        "success": True,
                        "handle": handle,
                        "block_name": self._block_name(block_ref),
                        "attributes": self._read_attributes(block_ref),
                    }
                )
            except Exception as exc:
                results.append({"success": False, "handle": handle, "error": str(exc)})
        return results

    def update_block_attributes(self, updates: list[dict[str, Any]]) -> list[dict]:
        results = []
        with self._undo_group():
            for update in updates:
                handle = str(update["handle"])
                requested = {str(k).upper(): str(v) for k, v in update["attributes"].items()}
                try:
                    block_ref = self._handle_to_object(handle)
                    if self._entity_type(block_ref) != "block_reference":
                        raise ValidationError(f"Handle {handle} is not a block reference.")
                    changed = []
                    unmatched = set(requested)
                    for attr in block_ref.GetAttributes() or []:
                        tag = str(self._safe_get(attr, "TagString", "")).upper()
                        if tag not in requested:
                            continue
                        before = str(self._safe_get(attr, "TextString", ""))
                        attr.TextString = requested[tag]
                        update_fn = self._safe_get(attr, "Update")
                        if callable(update_fn):
                            update_fn()
                        changed.append({"tag": tag, "old_value": before, "new_value": requested[tag]})
                        unmatched.discard(tag)
                    results.append(
                        {
                            "success": True,
                            "handle": handle,
                            "block_name": self._block_name(block_ref),
                            "changed": changed,
                            "unmatched_tags": sorted(unmatched),
                            "verified_attributes": self._read_attributes(block_ref),
                        }
                    )
                except Exception as exc:
                    results.append({"success": False, "handle": handle, "error": str(exc)})
        return results

    def insert_blocks(self, blocks: list[dict[str, Any]]) -> list[dict]:
        space = self._doc().ModelSpace
        results = []
        with self._undo_group():
            for index, item in enumerate(blocks):
                try:
                    scales = item.get("scale", [1.0, 1.0, 1.0])
                    ref = space.InsertBlock(
                        self._point(item["insertion_point"]),
                        str(item["name"]),
                        float(scales[0]),
                        float(scales[1]),
                        float(scales[2]),
                        float(item.get("rotation", 0.0)),
                    )
                    if item.get("layer"):
                        ref.Layer = item["layer"]
                    requested = {str(k).upper(): str(v) for k, v in item.get("attributes", {}).items()}
                    for attr in (ref.GetAttributes() or []) if requested else []:
                        tag = str(self._safe_get(attr, "TagString", "")).upper()
                        if tag in requested:
                            attr.TextString = requested[tag]
                            update_fn = self._safe_get(attr, "Update")
                            if callable(update_fn):
                                update_fn()
                    results.append(
                        {
                            "success": True,
                            "index": index,
                            "handle": str(self._safe_get(ref, "Handle", "")),
                            "block_name": self._block_name(ref),
                        }
                    )
                except Exception as exc:
                    results.append({"success": False, "index": index, "error": str(exc)})
        return results

    def begin_undo(self) -> None:
        try:
            self._doc().StartUndoMark()
        except Exception:
            pass

    def end_undo(self) -> None:
        try:
            self._doc().EndUndoMark()
        except Exception:
            pass
