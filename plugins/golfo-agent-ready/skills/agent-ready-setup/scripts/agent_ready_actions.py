"""What a plan does with each destination: its actions, how they show, and why.

classify_retired decides for an asset the lock has and no selected profile publishes anymore.
"""

from agent_ready_common import LOCAL_ABSENT, LOCAL_NOT_A_FILE
from agent_ready_lockfile import was_applied

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_ADOPT = "adopt"
ACTION_UNCHANGED = "unchanged"
ACTION_CONFLICT = "conflict"
ACTION_RETIRE = "retire"
ACTION_RETIRE_CONFLICT = "retire-conflict"
ACTION_DROP = "drop"

# Why a plan keeps a destination instead of deleting or relinking it.
LINKED_PARENT_REASON = "a parent directory is a symlink; deleting through it would reach files outside the project"
DETACHED_VIEW_REASON = "regular file that no apply wrote; it is preserved instead of relinked"
EDITED_VIEW_REASON = "regular file with local changes; relinking the view overwrites them"

# How each action shows in the text of a plan.
ACTION_SYMBOLS = {
    ACTION_CREATE: "+",
    ACTION_UPDATE: "~",
    ACTION_ADOPT: "~",
    ACTION_CONFLICT: "!",
    ACTION_RETIRE: "-",
    ACTION_RETIRE_CONFLICT: "!",
    ACTION_DROP: "-",
    ACTION_UNCHANGED: "=",
}


def classify_retired(local, lock_entry):
    """Decision for a locked asset that no selected profile publishes anymore."""
    if local == LOCAL_ABSENT:
        return ACTION_DROP, "already removed"
    if not was_applied(lock_entry):
        return ACTION_DROP, "never applied by agent-ready-setup; it stays as a project file"
    if local == LOCAL_NOT_A_FILE:
        return ACTION_RETIRE_CONFLICT, "retired from the profiles but it is not a regular file"
    if local == lock_entry.get("sha256"):
        return ACTION_RETIRE, "no longer published by the selected profiles"
    return ACTION_RETIRE, "no longer published by the selected profiles; removes its local changes"
