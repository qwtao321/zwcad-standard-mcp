"""Bridge that wires v2's runtime permission model into v1's service layer.

v2's design gates every mutating operation on a per-call confirmation flag
instead of a process-startup write switch. This module exposes a single
helper used by CadService: ``require_permission``. It returns ``None`` when
the operation may proceed, or a structured rejection dict otherwise. Every
decision is recorded to the v2 audit log.
"""

from __future__ import annotations

from typing import Any

from zwcad_standard_mcp.audit.operation_log import record
from zwcad_standard_mcp.permissions.manager import PermissionManager
from zwcad_standard_mcp.permissions.policy import PermissionLevel

_manager = PermissionManager()


def require_permission(
    level: PermissionLevel,
    confirm: bool = False,
    second_confirm: bool = False,
    file_path: str | None = None,
) -> dict[str, Any] | None:
    """Runtime, per-call permission gate.

    Returns a rejection dict when the operation is not allowed, else ``None``.

    - MODIFY: allowed only when ``confirm`` is True.
    - DELETE: allowed only when ``confirm`` and ``second_confirm`` are True.
    - SAVE:   allowed only when ``file_path`` is provided and ``confirm`` is True.
    """
    if level == PermissionLevel.SAVE:
        rejection: dict[str, Any] | None = (
            None
            if (file_path and confirm)
            else {
                "success": False,
                "permission": "save",
                "message": "Need explicit path and confirmation",
            }
        )
    elif level == PermissionLevel.DELETE:
        base = _manager.check(level, confirmed=confirm)
        if not base["allowed"]:
            rejection = base
        elif not second_confirm:
            rejection = {
                "allowed": False,
                "requires_second_confirmation": True,
                "permission": "delete",
            }
        else:
            rejection = None
    else:  # MODIFY (READ never calls this helper)
        base = _manager.check(level, confirmed=confirm)
        rejection = None if base["allowed"] else base

    record(
        operation=level.value,
        permission=level.value,
        result="allowed" if rejection is None else "denied",
    )
    return rejection
