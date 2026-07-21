from .policy import PermissionLevel

class PermissionManager:
    def require_confirmation(self, level: PermissionLevel):
        return level in [
            PermissionLevel.MODIFY,
            PermissionLevel.DELETE,
            PermissionLevel.SAVE,
        ]

    def check(self, level, confirmed=False):
        if self.require_confirmation(level) and not confirmed:
            return {
                "allowed": False,
                "requires_confirmation": True,
                "permission": level.value
            }
        return {
            "allowed": True,
            "requires_confirmation": False,
            "permission": level.value
        }
