from __future__ import annotations

from zwcad_standard_mcp.config import Settings

from .base import CadAdapter


def build_adapter(settings: Settings) -> CadAdapter:
    if settings.adapter == "fake":
        from .fake import FakeCadAdapter

        return FakeCadAdapter()

    if settings.adapter != "com":
        raise ValueError(f"Unsupported adapter: {settings.adapter}")

    from .com import ComCadAdapter

    return ComCadAdapter(
        prog_id=settings.prog_id,
        auto_start=settings.auto_start_cad,
    )
