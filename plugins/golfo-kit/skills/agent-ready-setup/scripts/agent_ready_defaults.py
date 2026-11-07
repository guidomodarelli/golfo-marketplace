"""Default of every option of ``.agents/agent-ready.json``, in one place.

Each mechanism is optional and configured on its own: a field in the manifest and an
environment variable that overrides it on one machine or in a CI job. Nothing is needed
to start, and the apply only writes what differs from these defaults, so a default that
improves reaches every repository.
"""

from agent_ready_common import StateError

UPDATES_FIELD = "updates"
CI_FIELD = "ci"
DETECTION_FIELD = "detection"
REFRESH_FIELD = "refresh"
PROVIDERS_FIELD = "providers"

UPDATES_AUTO = "auto"
UPDATES_PINNED = "pinned"
CI_FAIL = "fail"
CI_WARN = "warn"
CI_OFF = "off"
TOGGLE_ON = "on"
TOGGLE_OFF = "off"

OPTIONS = {
    UPDATES_FIELD: {
        "default": UPDATES_AUTO,
        "supported": (UPDATES_AUTO, UPDATES_PINNED),
        "override": "AGENT_READY_SETUP_UPDATES",
    },
    CI_FIELD: {
        "default": CI_FAIL,
        "supported": (CI_FAIL, CI_WARN, CI_OFF),
        "override": "AGENT_READY_SETUP_CI",
    },
    DETECTION_FIELD: {
        "default": TOGGLE_ON,
        "supported": (TOGGLE_ON, TOGGLE_OFF),
        "override": "AGENT_READY_SETUP_DETECTION",
    },
    REFRESH_FIELD: {
        "default": TOGGLE_ON,
        "supported": (TOGGLE_ON, TOGGLE_OFF),
        "override": "AGENT_READY_SETUP_REFRESH",
    },
}
DEFAULT_PROVIDERS = ("claude", "codex")


def validate_manifest_options(manifest, manifest_path):
    """Reject a value that an option of the manifest does not support."""
    for field, option in OPTIONS.items():
        if manifest.get(field, option["default"]) not in option["supported"]:
            raise StateError(f"{manifest_path} '{field}' must be one of {', '.join(option['supported'])}")


def effective_option(manifest, field, environment):
    """Value in force of an option: the environment, then the manifest, then the default."""
    option = OPTIONS[field]
    override = environment.get(option["override"])
    if override:
        if override not in option["supported"]:
            raise StateError(f"{option['override']} must be one of {', '.join(option['supported'])}")
        return override
    return (manifest or {}).get(field, option["default"])


def without_default_values(manifest):
    """The manifest with only what someone changed: defaults stay out of the file."""
    sparse = dict(manifest)
    for field, option in OPTIONS.items():
        if sparse.get(field) == option["default"]:
            del sparse[field]
    if sorted(sparse.get(PROVIDERS_FIELD, DEFAULT_PROVIDERS)) == sorted(DEFAULT_PROVIDERS):
        sparse.pop(PROVIDERS_FIELD, None)
    return sparse
