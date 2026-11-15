"""The lockfile of a repository: where it lives and how it is read.

The engine never follows a symlink at the lockfile path, and a lockfile without an assets inventory is not one.
"""

import os

from agent_ready_common import StateError, read_json_file

# The schemaVersion of the lock and of the plan, and the stateSchemaVersion of the engine that wrote them.
SCHEMA_VERSION = 1
LOCK_RELATIVE_PATH = ".agents/agent-ready.lock.json"
# The state of an asset or a block in the lock.
STATE_APPLIED = "applied"
STATE_CONFLICT = "conflict"
STATE_FAILED = "failed"
STATE_RETIRED_PRESERVED = "retired-preserved"


def read_lock(project_root):
    """Read the lockfile, or None when the repository was never locked."""
    path = os.path.join(project_root, LOCK_RELATIVE_PATH)
    if not os.path.exists(path) and not os.path.islink(path):
        return None
    if os.path.islink(path):
        raise StateError(f"{path} is a symlink; Agent Ready does not follow it")
    lock = read_json_file(path, "Agent Ready lockfile")
    if not isinstance(lock.get("assets"), dict):
        raise StateError(f"{path} has no 'assets' inventory")
    return lock


def was_applied(lock_entry):
    """True when an apply wrote this destination, which is what makes it managed.

    A preserved project file stays in the lock without an applied base. A failed
    write also has no base, but the apply did try to own that destination.
    """
    return bool(lock_entry) and (bool(lock_entry.get("sha256")) or lock_entry.get("state") == STATE_FAILED)
