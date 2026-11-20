"""The repository manifest (.agents/agent-ready.json) and the effective configuration it resolves: reading it,
the manifest an apply writes, the profile sources it declares and the warnings about values a layer could not set.
"""

from agent_ready_config import format_value

import json
import os

from agent_ready_config import (
    IGNORED_LOCKED,
    IGNORED_LOOSENS,
    describe_ignored,
    load_schema,
    resolve_configuration,
    set_sparse,
)
from agent_ready_layout import MANIFEST_RELATIVE_PATH
from agent_ready_options import (
    PROFILES_KEY,
    SOURCES_ENABLED_KEY,
    SOURCES_PACKS_KEY,
    UPDATES_MODE_KEY,
    UPDATES_REFRESH_KEY,
)
from agent_ready_output import paint, write_line
from agent_ready_packs import parse_profile_sources, source_update_mode_is_ignored

# The entry point, which `trust` runs to approve a repository on this machine.
STATE_SCRIPT_NAME = "agent-ready-state.py"


def state_script_path():
    """Path of the entry point, which lives beside this module."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), STATE_SCRIPT_NAME)


def configuration_of(project_root, offline=False):
    """Effective configuration of a repository; ``offline`` is the --offline flag of this run."""
    return resolve_configuration(project_root, flags={UPDATES_REFRESH_KEY: False} if offline else None)


def declared_sources(project_root):
    """Profile sources of the manifest, in a stable order; none while sources are off."""
    configuration = configuration_of(project_root)
    if not configuration.value(SOURCES_ENABLED_KEY):
        return []
    return parse_profile_sources(configuration.value(SOURCES_PACKS_KEY), os.path.join(project_root, MANIFEST_RELATIVE_PATH))


def read_manifest(project_root):
    """The repository manifest (the project layer), validated, or None when there is none.

    Reading it resolves every layer, so an invalid organization, user or project file
    stops here, before anything is written.
    """
    configuration = configuration_of(project_root)
    if configuration.project_document is not None:
        parse_profile_sources(configuration.project_document.get("sources", {}).get("packs", []),
                              os.path.join(project_root, MANIFEST_RELATIVE_PATH))
    return configuration.project_document


def build_manifest(previous, profiles, updates):
    """Manifest after an apply: the profiles it applied and, with --updates, the new mode.

    The apply never writes a default: --updates with the default value removes the key, so
    the repository follows whatever the lower layers say. What people wrote stays as is,
    because a value equal to the default may override the organization or the user.
    """
    manifest = json.loads(json.dumps(previous or {}))
    manifest[PROFILES_KEY] = list(profiles)
    if updates:
        set_sparse(manifest, UPDATES_MODE_KEY, updates, load_schema())
    return manifest


def approval_hint(project_root):
    """The exact command that approves a repository on this machine."""
    return f'approve it with: python3 "{state_script_path()}" trust --project "{project_root}"'


def print_ignored_configuration(configuration, stream):
    """Warn about every value a layer could not set, and about ignored source update modes."""
    hint = approval_hint(configuration.project_root)
    for item in configuration.ignored:
        write_line(paint(f"WARNING: {describe_ignored(item, hint)}", "warning", stream), stream)
    for declaration in declared_sources(configuration.project_root):
        reason = source_update_mode_is_ignored(configuration, declaration)
        if reason is None:
            continue
        item = {"key": f"{SOURCES_PACKS_KEY}[{declaration['name']}].updates", "value": declaration["updates"],
                "layer": "project", "reason": reason}
        if reason in (IGNORED_LOCKED, IGNORED_LOOSENS):
            message = describe_ignored(item, hint)
        else:
            message = f"{item['key']}={declaration['updates']} was ignored: {reason}"
        write_line(paint(f"WARNING: {message}", "warning", stream), stream)


def print_configuration_values(configuration, indent="  "):
    """Every option with its effective value and the layer it comes from."""
    values = {key: format_value(configuration.value(key)) or "-" for key in configuration.schema.leaves}
    key_width = max(len(key) for key in values)
    value_width = max(len(value) for value in values.values())
    for key in sorted(values):
        write_line(f"{indent}{key:<{key_width}}  {values[key]:<{value_width}}  ({configuration.origin(key)})")
