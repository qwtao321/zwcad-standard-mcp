from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from zwcad_standard_mcp.adapters import build_adapter
from zwcad_standard_mcp.config import Settings
from zwcad_standard_mcp.services import CadService
from zwcad_standard_mcp.tools import register_all_tools


SERVER_INSTRUCTIONS = """
Operate the locally running ZWCAD Standard application through its public COM API.
The server is designed around common user pain points: diagnosing connection issues,
understanding unfamiliar drawings, normalizing imported entities, batch drafting,
multi-layout plotting, and block/title-block attribute maintenance.

Safety rules:
- Mutating tools default to dry_run=true.
- Write operations are disabled unless ZWCAD_MCP_ALLOW_WRITE=true.
- Delete and save require explicit confirmation parameters.
- Batch edits use a ZWCAD undo mark where the COM API supports it.
- Prefer querying or reading selected objects before modifying them.
""".strip()


def create_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or Settings.from_env()
    adapter = build_adapter(settings)
    service = CadService(adapter, settings)
    mcp = FastMCP(
        name="ZWCAD Standard MCP",
        instructions=SERVER_INSTRUCTIONS,
        json_response=True,
    )
    register_all_tools(mcp, service)
    return mcp


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, settings.log_level, logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    mcp = create_server(settings)
    if settings.transport in {"streamable-http", "streamable_http", "http"}:
        mcp.run(transport="streamable-http")
    elif settings.transport == "stdio":
        mcp.run()
    else:
        raise ValueError(
            "ZWCAD_MCP_TRANSPORT must be 'stdio' or 'streamable-http'."
        )


if __name__ == "__main__":
    main()
