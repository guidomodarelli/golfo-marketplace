"""Workspaces: a selection of profiles for one folder of a monorepo.

The manifest keeps the selection of the whole repository in ``profiles`` and, in ``workspaces``, the
profiles of each folder that needs its own:

    "workspaces": [{"path": "apps/web", "profiles": ["nextjs-app-router"]},
                   {"path": "services/api", "profiles": ["node"]}]

Each workspace resolves its profiles like the root does (requires, defaults, excludedDefaults). What
the root selection already resolves applies to the whole repository, so a workspace only owns the
profiles the root does not have. The contract is in references/profiles-and-lockfile.md
("Workspaces").
"""

import agent_ready_blocks as managed_blocks
from agent_ready_common import ProfileError
from agent_ready_nested import folder_problem, is_folder, is_ignored

# What a workspace path is checked against Git with: a file inside it, so an ignored folder counts.
GIT_PROBE_FILE = "AGENTS.md"


def path_problem(project_root, path):
    """Why a folder cannot be a workspace, or None."""
    problem = folder_problem(path)
    if problem is None and not is_folder(project_root, path):
        problem = "does not exist in the repository"
    if problem is None and managed_blocks.has_linked_directory(project_root, f"{path}/{GIT_PROBE_FILE}"):
        problem = "is reached through a symlink, which can leave the repository"
    if problem is None and is_ignored(project_root, f"{path}/{GIT_PROBE_FILE}"):
        problem = "is ignored by Git"
    return problem


def validate(project_root, entries, manifest_path):
    """Raise ProfileError, before anything is written, for a workspace that cannot be one.

    A path has to be a folder of the repository that Git does not ignore, appear once and sit
    outside every other workspace: a folder in two workspaces would have two selections.
    """
    seen = []
    for entry in entries:
        path = entry["path"]
        problem = path_problem(project_root, path)
        if problem:
            raise ProfileError(f"{manifest_path}: the workspace {path!r} {problem}; nothing was written")
        for other in seen:
            if path.casefold() == other.casefold():
                raise ProfileError(f"{manifest_path}: the workspace {path!r} is listed twice; keep one entry")
            inner, outer = sorted((path, other), key=len, reverse=True)
            if inner.casefold().startswith(outer.casefold() + "/"):
                raise ProfileError(f"{manifest_path}: the workspace {inner!r} is inside the workspace {outer!r}; "
                                   "a folder takes the profiles of one workspace only")
        seen.append(path)


def resolve(entries, root_resolved, resolve_selection):
    """[{path, profiles, resolved, own}] of the workspaces, in the order of the manifest.

    ``resolve_selection`` resolves a list of profile names like the root selection. ``own`` keeps the
    resolved profiles the root selection does not have: the ones this workspace adds.
    """
    workspaces = []
    for entry in entries:
        try:
            resolved = resolve_selection(entry["profiles"])
        except ProfileError as profile_error:
            raise ProfileError(f"workspace {entry['path']}: {profile_error}") from profile_error
        workspaces.append({"path": entry["path"], "profiles": list(entry["profiles"]), "resolved": resolved,
                           "own": [name for name in resolved if name not in root_resolved]})
    return workspaces


def describe(workspace):
    """One line of plan or status for a workspace."""
    selected = ", ".join(workspace["profiles"]) or "none"
    if not workspace["own"]:
        return f"{workspace['path']}: {selected} (nothing of its own: the root selection already has it)"
    return f"{workspace['path']}: {selected} (adds {', '.join(workspace['own'])} to the root selection)"


def lock_entries(workspaces):
    """{path: {profiles, own}} of the workspaces, as the lockfile records them."""
    return {workspace["path"]: {"profiles": workspace["profiles"], "own": workspace["own"]} for workspace in workspaces}


def differences(configured, locked):
    """What the manifest says of the workspaces that the last apply did not adopt, one line each."""
    lines = []
    configured_by_path = {entry["path"]: list(entry["profiles"]) for entry in configured}
    for path, profiles in configured_by_path.items():
        if path not in locked:
            lines.append(f"workspace {path} is not applied yet")
        elif locked[path].get("profiles") != profiles:
            lines.append(f"workspace {path} selects {', '.join(profiles) or 'none'}, the lock "
                         f"{', '.join(locked[path].get('profiles') or []) or 'none'}")
    lines += [f"workspace {path} left the manifest" for path in sorted(set(locked) - set(configured_by_path))]
    return lines
