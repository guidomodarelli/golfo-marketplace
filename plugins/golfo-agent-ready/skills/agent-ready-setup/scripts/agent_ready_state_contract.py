"""What the callers of agent-ready-state.py rely on: bootstrap.sh, the hooks, the agent-ready CLI and CI pipelines.
The exit statuses, the results of check and the status of each, the moments and the prefix of the conflicts
hook, the plan formats that print only the conflicts, the source modes and where a selection came from.
"""

# Results of `check` and their exit statuses: the stable contract of a CI pipeline.
CHECK_UP_TO_DATE = "up-to-date"
CHECK_OUTDATED = "outdated"
CHECK_SOURCE_UNAVAILABLE = "source-unavailable"
CHECK_CONFIG_ERROR = "config-error"
CHECK_SKIPPED = "skipped"
CHECK_CONFLICTS = "conflicts"
# Exit status when the selected profiles cannot be resolved or composed.
PROFILE_ERROR_STATUS = 2
# Exit status of `detect` when the signals do not determine one primary stack.
DETECTION_UNRESOLVED_STATUS = 3
# Exit status of `status --check` when the checkout or the source drifted from the lock.
DRIFT_STATUS = 4
# Exit status when a profile source the selection needs is not available or not adopted.
INCOMPLETE_EVALUATION_STATUS = 5
# agent-ready conflicts and agent-ready check found conflicts between the profiles.
CONFLICTS_STATUS = 6
# content-source: the content pack of the repository is not on this machine yet (sync-marketplace.sh).
CONTENT_PENDING_STATUS = 7
# The moments a hook asks status for the conflicts alone, and the prefix of each line it prints.
CONFLICTS_MOMENT_SESSION_START = "session-start"
CONFLICTS_MOMENT_EDIT = "edit"
CONFLICTS_HOOK_PREFIX = "[conflicts]"
# plan formats that print only the conflicts, for agent-ready conflicts.
CONFLICTS_FORMAT = "conflicts"
CONFLICTS_JSON_FORMAT = "conflicts-json"
CHECK_EXIT_STATUSES = {
    CHECK_UP_TO_DATE: 0,
    CHECK_SKIPPED: 0,
    CHECK_CONFIG_ERROR: PROFILE_ERROR_STATUS,
    CHECK_OUTDATED: DRIFT_STATUS,
    CHECK_SOURCE_UNAVAILABLE: INCOMPLETE_EVALUATION_STATUS,
    CHECK_CONFLICTS: CONFLICTS_STATUS,
}
# How a command treats profile sources. Read-only evaluates what is there and reports
# differences. Sync (SessionStart with automatic updates) also refuses to adopt them.
SOURCE_MODE_READ_ONLY = "read-only"
SOURCE_MODE_SYNC = "sync"
# Where the effective selection came from, by precedence.
SELECTION_PROFILES_FLAG = "--profiles"
SELECTION_STACK_FLAG = "--stack"
SELECTION_MANIFEST = "manifest"
SELECTION_DETECTION = "detection"
