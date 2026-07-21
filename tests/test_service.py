from __future__ import annotations

import pytest

from zwcad_standard_mcp.adapters.fake import FakeCadAdapter
from zwcad_standard_mcp.config import Settings
from zwcad_standard_mcp.errors import ValidationError, WriteDisabledError
from zwcad_standard_mcp.models import BlockAttributePatch, EntityCreateSpec, EntityPropertyPatch, LayerSpec
from zwcad_standard_mcp.services import CadService


def build_service(*, allow_write: bool = False) -> tuple[CadService, FakeCadAdapter]:
    adapter = FakeCadAdapter()
    settings = Settings(adapter="fake", allow_write=allow_write, max_batch_size=20)
    return CadService(adapter, settings), adapter


def test_diagnose_exposes_server_policy() -> None:
    service, _ = build_service()
    result = service.diagnose_cad()
    assert result["success"] is True
    assert result["server_policy"]["allow_write"] is False
    assert result["server_policy"]["adapter"] == "fake"


def test_ensure_layers_dry_run_does_not_mutate() -> None:
    service, adapter = build_service()
    result = service.ensure_layers([LayerSpec(name="CENTER", color=3)], dry_run=True)
    assert result["dry_run"] is True
    assert "CENTER" not in adapter.layers
    assert result["planned"][0]["operation"] == "create"


def test_write_is_blocked_by_default() -> None:
    service, _ = build_service(allow_write=False)
    patch = EntityPropertyPatch(handles=["10"], layer="OUTLINE")
    with pytest.raises(WriteDisabledError):
        service.update_entity_properties(patch, dry_run=False)


def test_update_entity_properties_when_enabled() -> None:
    service, adapter = build_service(allow_write=True)
    patch = EntityPropertyPatch(handles=["10"], layer="OUTLINE", color=256)
    result = service.update_entity_properties(patch, dry_run=False)
    assert result["failure_count"] == 0
    assert adapter.entities["10"]["layer"] == "OUTLINE"
    assert adapter.entities["10"]["color"] == 256


def test_create_entities_batch() -> None:
    service, adapter = build_service(allow_write=True)
    before = len(adapter.entities)
    result = service.create_entities(
        [EntityCreateSpec(entity_type="circle", layer="OUTLINE", params={"center": [0, 0, 0], "radius": 5})],
        dry_run=False,
    )
    assert result["success_count"] == 1
    assert len(adapter.entities) == before + 1


def test_title_block_attribute_preview_and_apply() -> None:
    service, adapter = build_service(allow_write=True)
    updates = [BlockAttributePatch(handle="12", attributes={"DESIGNER": "张三", "DATE": "2026-07-21"})]
    preview = service.update_block_attributes(updates, dry_run=True)
    assert preview["planned"][0]["changes"]
    assert adapter.entities["12"]["attributes"][0]["text"] == "Alice"

    applied = service.update_block_attributes(updates, dry_run=False)
    assert applied["failure_count"] == 0
    values = {item["tag"]: item["text"] for item in adapter.entities["12"]["attributes"]}
    assert values == {"DESIGNER": "张三", "DATE": "2026-07-21"}


def test_delete_requires_confirmation() -> None:
    service, adapter = build_service(allow_write=True)
    with pytest.raises(ValidationError):
        service.delete_entities(["10"], dry_run=False, confirm=False)
    assert "10" in adapter.entities


def test_plot_layouts_preview() -> None:
    service, _ = build_service()
    result = service.plot_layouts(["Layout1"], "C:/output", None, "pdf", dry_run=True)
    assert result["planned"][0]["layout"] == "Layout1"
    assert result["planned"][0]["file_path"].endswith("sample-Layout1.pdf")
