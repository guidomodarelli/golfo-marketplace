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

import os

from agent_ready_common import ProfileError, is_link
from agent_ready_nested import folder_problem, is_folder, is_ignored


def is_linked(project_root, path):
    """True when the folder, or a folder above it, is a symlink or a Windows junction."""
    parts = path.split("/")
    return any(is_link(os.path.join(project_root, *parts[:depth])) for depth in range(1, len(parts) + 1))


def path_problem(project_root, path):
    """Why a folder cannot be a workspace, or None. Git is asked about the folder itself: whether it
    ignores one file in it says nothing of the workspace."""
    problem = folder_problem(path)
    if problem is None and not is_folder(project_root, path):
        problem = "does not exist in the repository"
    if problem is None and is_linked(project_root, path):
        problem = "is reached through a symlink, which can leave the repository"
    if problem is None and is_ignored(project_root, path):
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


def resolve(entries, root_names, root_resolved, resolve_selection):
    """[{path, profiles, resolved, own}] of the workspaces, in the order of the manifest.

    A workspace takes the root selection too, so ``resolve_selection`` resolves the root names
    followed by its own: a profile of the workspace that conflicts with one of the root fails like
    it would in the root selection. Different workspaces stay independent. ``own`` keeps the
    resolved profiles the root selection does not have: the ones this workspace adds.
    """
    workspaces = []
    for entry in entries:
        names = list(root_names) + [name for name in entry["profiles"] if name not in root_names]
        try:
            resolved = resolve_selection(names)
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
    """What the manifest says of the workspaces that the lock does not have, one line each.

    ``configured`` holds the entries of the manifest, or the resolved workspaces of a plan: those also
    carry ``own``, which --from-lock compares too, so a catalog that resolves differently is caught.
    """
    lines = []
    for entry in configured:
        path, profiles, locked_entry = entry["path"], list(entry["profiles"]), locked.get(entry["path"])
        if locked_entry is None:
            lines.append(f"workspace {path} is not applied yet")
        elif locked_entry.get("profiles") != profiles:
            lines.append(f"workspace {path} selects {', '.join(profiles) or 'none'}, the lock "
                         f"{', '.join(locked_entry.get('profiles') or []) or 'none'}")
        elif "own" in entry and locked_entry.get("own") != entry["own"]:
            lines.append(f"workspace {path} adds {', '.join(entry['own']) or 'nothing'}, the lock "
                         f"{', '.join(locked_entry.get('own') or []) or 'nothing'}")
    configured_paths = {entry["path"] for entry in configured}
    lines += [f"workspace {path} left the manifest" for path in sorted(set(locked) - configured_paths)]
    return lines
