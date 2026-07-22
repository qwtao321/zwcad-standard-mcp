from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Scope = Literal["model", "paper", "all_layouts"]


class LayerSpec(BaseModel):
    name: str = Field(min_length=1, description="Layer name")
    color: int | None = Field(default=None, ge=0, le=256)
    linetype: str | None = None
    on: bool | None = None
    locked: bool | None = None
    frozen: bool | None = None


class EntityCreateSpec(BaseModel):
    entity_type: Literal[
        "line",
        "circle",
        "arc",
        "lwpolyline",
        "text",
        "mtext",
        "block",
        "dimension_aligned",
        "dimension_rotated",
        "dimension_radial",
        "dimension_diametric",
    ]
    params: dict[str, Any]
    layer: str = "0"


class EntityQuerySpec(BaseModel):
    scope: Scope = "model"
    entity_type: str | None = None
    layer: str | None = None
    text_contains: str | None = None
    block_name: str | None = None
    limit: int = Field(default=200, ge=1, le=5000)


class EntityPropertyPatch(BaseModel):
    handles: list[str] = Field(min_length=1)
    layer: str | None = None
    color: int | None = Field(default=None, ge=0, le=256)
    linetype: str | None = None
    linetype_scale: float | None = Field(default=None, gt=0)
    lineweight: int | None = None
    visible: bool | None = None

    @field_validator("handles")
    @classmethod
    def unique_handles(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(handle.strip() for handle in value if handle.strip()))


class BlockAttributePatch(BaseModel):
    handle: str = Field(min_length=1)
    attributes: dict[str, str] = Field(min_length=1)


class PlotScopeRequest(BaseModel):
    """Request to preview the final plot area for a given scope."""

    scope_type: Literal["display", "extents", "limits", "view", "window", "layout"] | None = Field(
        default=None,
        description="Plot scope type to preview. If omitted, the active layout's current PlotType is used.",
    )
    layout_name: str | None = Field(
        default=None,
        description="Layout to inspect. Defaults to the active layout.",
    )
    window_lower_left: list[float] | None = Field(
        default=None,
        description="Lower-left corner of the plot window (only for scope_type='window').",
    )
    window_upper_right: list[float] | None = Field(
        default=None,
        description="Upper-right corner of the plot window (only for scope_type='window').",
    )
    selected_handles: list[str] | None = Field(
        default=None,
        description="Handles to use when previewing a 'selected' scope.",
    )

    @field_validator("window_lower_left", "window_upper_right")
    @classmethod
    def _window_corner_2d(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if len(value) < 2:
            raise ValueError("Window corner must have at least [x, y].")
        return [float(v) for v in value[:3]]


class TransformRequest(BaseModel):
    action: Literal["move", "copy", "rotate", "scale", "mirror"]
    handles: list[str] = Field(min_length=1)
    params: dict[str, Any]

    @field_validator("handles")
    @classmethod
    def unique_handles(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(handle.strip() for handle in value if handle.strip()))

