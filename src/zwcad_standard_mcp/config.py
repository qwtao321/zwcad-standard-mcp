from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    prog_id: str = "ZWCAD.Application"
    allow_write: bool = False
    auto_start_cad: bool = False
    max_query_results: int = 500
    max_batch_size: int = 200
    transport: str = "stdio"
    adapter: str = "com"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            prog_id=os.getenv("ZWCAD_MCP_PROG_ID", "ZWCAD.Application"),
            allow_write=_as_bool(os.getenv("ZWCAD_MCP_ALLOW_WRITE"), False),
            auto_start_cad=_as_bool(os.getenv("ZWCAD_MCP_AUTO_START"), False),
            max_query_results=max(1, int(os.getenv("ZWCAD_MCP_MAX_QUERY_RESULTS", "500"))),
            max_batch_size=max(1, int(os.getenv("ZWCAD_MCP_MAX_BATCH_SIZE", "200"))),
            transport=os.getenv("ZWCAD_MCP_TRANSPORT", "stdio").strip().lower(),
            adapter=os.getenv("ZWCAD_MCP_ADAPTER", "com").strip().lower(),
            log_level=os.getenv("ZWCAD_MCP_LOG_LEVEL", "INFO").strip().upper(),
        )
