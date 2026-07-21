from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from zwcad_standard_mcp.errors import ZWCADMCPError

logger = logging.getLogger(__name__)


def invoke(fn: Callable[..., dict], *args: Any, **kwargs: Any) -> dict:
    try:
        return fn(*args, **kwargs)
    except ZWCADMCPError as exc:
        logger.warning("tool_error code=%s error=%s", exc.code, exc)
        return exc.as_dict()
    except Exception as exc:  # defensive boundary for COM failures
        logger.exception("unexpected_tool_error")
        return {
            "success": False,
            "code": "UNEXPECTED_ERROR",
            "error": str(exc),
        }
