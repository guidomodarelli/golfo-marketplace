"""agent-ready workspaces list|add|remove: the workspaces of a monorepo in the manifest.

A workspace gives a folder a selection of its own next to the one of the repository
(references/profiles-and-lockfile.md, «Workspaces»). These subcommands edit the ``workspaces`` of the
project layer, validate every change with the engine before writing (the folder, the profiles and their
resolution with the root selection) and leave the projection to ``apply``. Data goes to stdout; hints
and progress to stderr.
"""

import os
import sys

from agent_ready_cli_common import (
    CLI_NAME,
    EXIT_OK,
    UsageError,
    content_root,
    engine,
    write_project_workspaces,
)
from agent_ready_cli_selection import apply_command_for, profile_names, selected_profiles
from agent_ready_common import ProfileError, serialize_json
from agent_ready_config import PROJECT_CONFIG_RELATIVE_PATH
from agent_ready_options import WORKSPACES_KEY


def manifest_workspaces(project_root):
    """The workspaces of the manifest, as [{path, profiles}]."""
    return [dict(entry) for entry in engine().configuration_of(project_root).value(WORKSPACES_KEY) or []]


def normalized_path(path):
    """A folder as the manifest writes it: relative, with / and without ./ or a final /."""
    path = path.replace("\\", "/").strip().rstrip("/")
    while path.startswith("./"):
        path = path[2:]
    return path


def resolution(project_root, entries):
    """(catalog, resolved root selection, resolved workspaces) of ``entries``; ProfileError when they cannot be."""
    state = engine()
    catalog = state.load_effective_catalog(project_root, content_root(project_root))
    names = selected_profiles(project_root) or []
    resolved = state.resolve_project_profiles(catalog, names, project_root)
    return catalog, resolved, state.resolve_workspaces(project_root, catalog, names, resolved, entries)


def require_selection(project_root):
    """A workspace sits next to the selection of the repository: without one there is nothing to add to."""
    if selected_profiles(project_root) is None:
        raise UsageError(f"this repository has no selection yet; start it with {CLI_NAME} init")


def write_and_report(project_root, entries, summary):
    """Write the workspaces and say how to project them."""
    path = write_project_workspaces(project_root, entries)
    apply_command = apply_command_for(project_root, selected_profiles(project_root) or [])
    sys.stderr.write(f"{summary} in {path}. Run {apply_command} to project it "
                     f"({apply_command} --dry-run shows what would change).\n")
    return EXIT_OK


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def command_workspaces_list(arguments):
    """Each workspace with the profiles it adds to the root selection, and the folders detection suggests."""
    entries = manifest_workspaces(arguments.project_root)
    try:
        catalog, resolved, workspaces = resolution(arguments.project_root, entries)
    except ProfileError as profile_error:
        raise UsageError(str(profile_error)) from profile_error
    suggestions = engine().workspace_suggestions(arguments.project_root, catalog, resolved)
    rows = [{"path": workspace["path"], "profiles": workspace["profiles"], "adds": workspace["own"]}
            for workspace in workspaces]
    if arguments.json:
        sys.stdout.write(serialize_json({"workspaces": rows, "suggestions": suggestions}))
        return EXIT_OK
    width = max([len(row["path"]) for row in rows] + [len("path")])
    for row in rows:
        adds = ", ".join(row["adds"]) or "nothing: the root selection already has it"
        sys.stdout.write(f"{row['path']:<{width}}  {', '.join(row['profiles']) or 'none'}  (adds {adds})\n")
    if not rows:
        sys.stderr.write(f"No workspaces in {PROJECT_CONFIG_RELATIVE_PATH}.\n")
    for suggestion in suggestions:
        evidence = engine().format_evidence_list(suggestion["evidence"])
        sys.stderr.write(f"Suggested: {suggestion['path']}: {', '.join(suggestion['profiles'])} ({evidence}). "
                         f"Add it with {CLI_NAME} workspaces add {suggestion['path']}\n")
    return EXIT_OK


# ---------------------------------------------------------------------------
# add|remove
# ---------------------------------------------------------------------------

def detected_profiles(project_root, path):
    """The stack detection finds in the folder, for an add that names no profile."""
    state = engine()
    catalog = state.load_effective_catalog(project_root, content_root(project_root))
    detection = state.detect_profiles(catalog["profiles"], os.path.join(project_root, *path.split("/")))
    if detection["primaryStack"]:
        return [detection["primaryStack"]]
    if detection["candidates"]:
        raise UsageError(f"the signals of {path} point to several stacks ({', '.join(detection['candidates'])}); "
                         f"name one: {CLI_NAME} workspaces add {path} <profile>")
    raise UsageError(f"no stack detected in {path}; name its profiles: {CLI_NAME} workspaces add {path} <profile>")


def command_workspaces_add(arguments):
    """Add a workspace, or profiles to one, after the engine validates the result."""
    require_selection(arguments.project_root)
    path = normalized_path(arguments.path)
    added = profile_names(",".join(arguments.names)) if arguments.names else \
        detected_profiles(arguments.project_root, path)
    entries = manifest_workspaces(arguments.project_root)
    entry = next((entry for entry in entries if entry["path"] == path), None)
    if entry is None:
        entry = {"path": path, "profiles": []}
        entries.append(entry)
    entry["profiles"] = list(entry["profiles"]) + [name for name in added if name not in entry["profiles"]]
    try:
        resolution(arguments.project_root, entries)
    except ProfileError as profile_error:
        raise UsageError(str(profile_error)) from profile_error
    return write_and_report(arguments.project_root, entries, f"Workspace {path}: {', '.join(entry['profiles'])}")


def command_workspaces_remove(arguments):
    """Remove a workspace, or some of its profiles; a workspace left without profiles goes too."""
    path = normalized_path(arguments.path)
    entries = manifest_workspaces(arguments.project_root)
    entry = next((entry for entry in entries if entry["path"] == path), None)
    if entry is None:
        listed = ", ".join(workspace["path"] for workspace in entries) or "none"
        raise UsageError(f"{path} is not a workspace of {PROJECT_CONFIG_RELATIVE_PATH}; the workspaces are: {listed}")
    if arguments.names:
        missing = [name for name in arguments.names if name not in entry["profiles"]]
        if missing:
            raise UsageError(f"workspace {path} does not select {', '.join(missing)}; it selects "
                             f"{', '.join(entry['profiles']) or 'nothing'}")
        entry["profiles"] = [name for name in entry["profiles"] if name not in arguments.names]
    if not arguments.names or not entry["profiles"]:
        entries.remove(entry)
        return write_and_report(arguments.project_root, entries, f"Workspace {path} removed")
    return write_and_report(arguments.project_root, entries, f"Workspace {path}: {', '.join(entry['profiles'])}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def register(subparsers, new_subparser):
    """Add workspaces to the parser of the CLI."""
    workspaces = new_subparser(subparsers, "workspaces", "List and change the workspaces of a monorepo.",
                               "  agent-ready workspaces list\n  agent-ready workspaces add apps/web nextjs-app-router",
                               None, with_project=False)
    actions = workspaces.add_subparsers(dest="workspaces_command", metavar="<action>", required=True)
    listing = new_subparser(actions, "list", "Each workspace, what it adds to the root selection, and the suggested ones.",
                            "  agent-ready workspaces list --json", command_workspaces_list)
    listing.add_argument("--json", action="store_true", help="print the workspaces and suggestions as JSON on stdout")
    add = new_subparser(actions, "add", "Add a workspace, or profiles to one; without profiles, the stack detected there.",
                        "  agent-ready workspaces add apps/web\n  agent-ready workspaces add services/api go",
                        command_workspaces_add)
    add.add_argument("path", help="folder of the repository, e.g. apps/web")
    add.add_argument("names", nargs="*", metavar="profile", help="profiles of the workspace (default: the detected stack)")
    remove = new_subparser(actions, "remove", "Remove a workspace, or some of its profiles.",
                           "  agent-ready workspaces remove apps/web\n  agent-ready workspaces remove apps/web business-flows",
                           command_workspaces_remove)
    remove.add_argument("path", help="the workspace, e.g. apps/web")
    remove.add_argument("names", nargs="*", metavar="profile", help="profiles to remove (default: the whole workspace)")
