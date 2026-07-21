from enum import Enum

class PermissionLevel(str, Enum):
    READ = "read"
    MODIFY = "modify"
    DELETE = "delete"
    SAVE = "save"
