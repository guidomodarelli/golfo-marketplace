"""Workspaces: a selection of profiles for one folder of a monorepo.

The manifest keeps the selection of the whole repository in ``profiles`` and, in ``workspaces``, the
profiles of each folder that needs its own:

    "workspaces": [{"path": "apps/web", "profiles": ["nextjs-app-router"]},
                   {"path": "services/api", "profiles": ["node"]}]

Each workspace resolves its profiles like the root does (requires, defaults, excludedDefaults). What
the root selection already resolves applies to the whole repository, so a workspace only owns the
profiles the root does not have.

The rules of those profiles go to ``.agents/rules/workspaces/<path>/`` with ``paths:`` limited to the
workspace, so Claude Code loads them only for its files, and the AGENTS.md of the workspace lists them
for Codex (index_content). The contract is in references/profiles-and-lockfile.md ("Workspaces").
"""

import os
import re

from agent_ready_common import ProfileError, is_link
from agent_ready_nested import folder_problem, is_folder, is_ignored

RULES_DIRECTORY = "rules"
# Under .agents/rules/: the rules of each workspace, which the root AGENTS.md does not list.
WORKSPACE_RULES_DIRECTORY = "workspaces"
# The block of the AGENTS.md of a workspace that lists its rules. Its id cannot be a profile name.
INDEX_BLOCK_ID = "agent-ready:workspace"
INDEX_SOURCE = "agent-ready:workspace"
FRONTMATTER_FENCE = "---"
PATHS_KEY = "paths"
PATHS_LINE = re.compile(r"^paths:\s*(.*)$")
LIST_ITEM = re.compile(r"^\s+-\s*(.*)$")
INLINE_LIST = re.compile(r"^\[(.*)\]$")


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


# ---------------------------------------------------------------------------
# Rules of a workspace
# ---------------------------------------------------------------------------

def rule_tree_path(workspace_path, rule_path):
    """Where a rule of a workspace goes, under the composed tree and under .agents/:
    rules/workspaces/<workspace>/<path of the rule under rules/>."""
    return f"{RULES_DIRECTORY}/{WORKSPACE_RULES_DIRECTORY}/{workspace_path}/{rule_path}"


def is_workspace_rule(rule_path):
    """True for a path under rules/ that belongs to a workspace (rules/workspaces/...)."""
    return rule_path.startswith(WORKSPACE_RULES_DIRECTORY + "/")


def unquoted(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def quoted(pattern):
    return '"' + pattern.replace("\\", "\\\\").replace('"', '\\"') + '"'


def inline_items(value):
    """The items of an inline YAML list, split on the commas outside quotes and braces ({ts,tsx})."""
    items, current, quote, depth = [], "", None, 0
    for character in value:
        if quote:
            quote = None if character == quote else quote
        elif character in "\"'":
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth = max(depth - 1, 0)
        elif character == "," and depth == 0:
            items.append(current)
            current = ""
            continue
        current += character
    items.append(current)
    return [unquoted(item) for item in items if item.strip()]


def selected_profiles(root_resolved, workspaces):
    """The root selection followed by the profiles each workspace adds: every profile an apply projects,
    whose sources, digests and pinned mode count as much as those of the root."""
    names = list(root_resolved)
    for workspace in workspaces:
        names += [name for name in workspace["own"] if name not in names]
    return names


def frontmatter_patterns(lines, start, rule):
    """(patterns, end) of the paths: key at lines[start]: its patterns and the first line after them."""
    value = PATHS_LINE.match(lines[start]).group(1).strip()
    if value:
        inline = INLINE_LIST.match(value)
        patterns = inline_items(inline.group(1)) if inline else [unquoted(value)]
        return patterns, start + 1
    patterns, end = [], start + 1
    while end < len(lines) and LIST_ITEM.match(lines[end]):
        patterns.append(unquoted(LIST_ITEM.match(lines[end]).group(1)))
        end += 1
    if not patterns:
        raise ProfileError(f"rule {rule}: paths: in its frontmatter is not a list of patterns")
    return patterns, end


def scoped_rule_text(text, workspace_path, rule):
    """The rule with paths: limited to the workspace, so Claude Code loads it only for its files.

    A rule without frontmatter gets one with paths: <workspace>/**, a frontmatter without paths: gets
    the key, and the patterns a rule already has stay, under the workspace. The rest of the
    frontmatter and the body stay as they are.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == FRONTMATTER_FENCE and FRONTMATTER_FENCE in [line.strip() for line in lines[1:]]:
        close = 1 + [line.strip() for line in lines[1:]].index(FRONTMATTER_FENCE)
        header = lines[1:close]
        body = lines[close + 1:]
    else:
        header, body = [], lines
    start = next((index for index, line in enumerate(header) if PATHS_LINE.match(line)), None)
    if start is None:
        patterns, before, after = ["**"], header, []
    else:
        patterns, end = frontmatter_patterns(header, start, rule)
        before, after = header[:start], header[end:]
    for pattern in patterns:
        if not pattern or pattern.startswith("/") or ".." in pattern.split("/"):
            raise ProfileError(f"rule {rule}: the pattern {pattern!r} of paths: does not stay inside the repository")
    scoped = [f"{workspace_path}/{pattern[2:] if pattern.startswith('./') else pattern}" for pattern in patterns]
    paths = [f"{PATHS_KEY}:"] + [f"  - {quoted(pattern)}" for pattern in scoped]
    return "\n".join([FRONTMATTER_FENCE] + before + paths + after + [FRONTMATTER_FENCE] + body)


def index_content(workspace_path, rule_destinations):
    """The block of the AGENTS.md of a workspace: the rules of its own profiles, to read before working there."""
    lines = [f"## Workspace `{workspace_path}`", "",
             "This folder has profiles of its own. Read and follow these rules before you change its files:", ""]
    lines += [f"- Read and follow `{destination}`." for destination in sorted(rule_destinations)]
    return "\n".join(lines) + "\n"

