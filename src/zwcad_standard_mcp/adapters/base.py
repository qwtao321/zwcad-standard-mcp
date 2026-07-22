from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from zwcad_standard_mcp.models import (
    EntityCreateSpec,
    EntityQuerySpec,
    LayerSpec,
    PlotScopeRequest,
)


class CadAdapter(ABC):
    """Boundary between MCP-facing business logic and a concrete CAD API."""

    @abstractmethod
    def diagnose(self) -> dict: ...

    @abstractmethod
    def get_app_info(self) -> dict: ...

    @abstractmethod
    def get_current_document(self) -> dict: ...

    @abstractmethod
    def list_documents(self) -> list[dict]: ...

    @abstractmethod
    def scan_cad_folder(self, path: str, recursive: bool = False) -> dict: ...

    @abstractmethod
    def open_document(self, path: str, read_only: bool = False) -> dict: ...

    @abstractmethod
    def close_document(self, name: str, save_changes: bool = False) -> dict: ...

    @abstractmethod
    def activate_document(self, name: str) -> dict: ...

    @abstractmethod
    def save_document(self, file_path: str | None = None) -> dict: ...

    @abstractmethod
    def list_layers(self, detail: bool = True) -> list[dict]: ...

    @abstractmethod
    def ensure_layers(self, layers: list[LayerSpec]) -> list[dict]: ...

    @abstractmethod
    def audit_drawing(self, sample_limit: int) -> dict: ...

    @abstractmethod
    def get_selected_entities(self, limit: int) -> list[dict]: ...

    @abstractmethod
    def query_entities(self, query: EntityQuerySpec) -> list[dict]: ...

    @abstractmethod
    def get_entity_details(self, handles: list[str]) -> list[dict]: ...

    @abstractmethod
    def update_entity_properties(self, handles: list[str], properties: dict[str, Any]) -> list[dict]: ...

    @abstractmethod
    def transform_entities(self, action: str, handles: list[str], params: dict[str, Any]) -> list[dict]: ...

    @abstractmethod
    def delete_entities(self, handles: list[str]) -> list[dict]: ...

    @abstractmethod
    def create_entities(self, entities: list[EntityCreateSpec]) -> list[dict]: ...

    @abstractmethod
    def list_layouts(self) -> list[dict]: ...

    @abstractmethod
    def get_layout_plot_settings(self, layout_name: str | None) -> dict: ...

    @abstractmethod
    def get_plot_capabilities(self) -> dict: ...

    @abstractmethod
    def preview_plot_scope(self, request: PlotScopeRequest) -> dict: ...

    @abstractmethod
    def get_current_view(self) -> dict: ...

    @abstractmethod
    def get_drawing_extents(self) -> dict: ...

    @abstractmethod
    def activate_layout(self, name: str) -> dict: ...

    @abstractmethod
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
    ) -> list[dict]: ...

    @abstractmethod
    def export_drawing(self, base_file_path: str, extension: str) -> dict: ...

    @abstractmethod
    def verify_export_files(
        self,
        file_paths: list[str],
        layout_names: list[str] | None = None,
        min_size_bytes: int = 1024,
        expected_plot_range: dict[str, list[float]] | None = None,
    ) -> dict: ...

    @abstractmethod
    def list_block_definitions(self, detail: bool) -> list[dict]: ...

    @abstractmethod
    def list_block_references(
        self,
        scope: str,
        block_name: str | None,
        has_attributes: bool | None,
        limit: int,
    ) -> list[dict]: ...

    @abstractmethod
    def get_block_attributes(self, handles: list[str]) -> list[dict]: ...

    @abstractmethod
    def update_block_attributes(self, updates: list[dict[str, Any]]) -> list[dict]: ...

    @abstractmethod
    def insert_blocks(self, blocks: list[dict[str, Any]]) -> list[dict]: ...

    @abstractmethod
    def begin_undo(self) -> None: ...

    @abstractmethod
    def end_undo(self) -> None: ...
