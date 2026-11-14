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
for Codex (index_content) next to the section of each stack it adds (with_workspace_references). Their
skills, subagents and commands go to .agents/ once for the whole repository, because the providers do
not scope them by folder. The contract is in references/profiles-and-lockfile.md ("Workspaces").
"""

import fnmatch
import glob
import json
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
# How a section of AGENTS.md, a skill, a subagent or a command names a rule; scoped_references moves it
# to the rule of each workspace.
RULE_REFERENCE = "`.agents/rules/{}`"
# After the references to the rule of several workspaces, in a skill, subagent or command they share.
WORKSPACE_CHOICE_HINT = " (the one of the workspace you work in)"
# Files Git and Docker read for their own folder: the block a workspace profile publishes for one of them
# goes to the file of the workspace. Every other block goes to the root, once for the repository.
FOLDER_BLOCK_FILES = (".gitignore", ".gitattributes", ".dockerignore")
FRONTMATTER_FENCE = "---"
PATHS_KEY = "paths"
PATHS_LINE = re.compile(r"^paths:\s*(.*)$")
# YAML takes the items of a sequence indented or not ("paths:" then "- src/**").
LIST_ITEM = re.compile(r"^\s*-\s*(.*)$")
INLINE_LIST = re.compile(r"^\[(.*)\]$")


# Where a monorepo keeps its packages, besides what its package managers declare (declared_patterns).
CONVENTIONAL_PARENTS = ("apps", "packages", "services")
PACKAGE_MANIFEST = "package.json"
PNPM_WORKSPACE_FILE = "pnpm-workspace.yaml"
GO_WORK_FILE = "go.work"
# The folders detection looks into at most, besides the workspaces it skips: each one asks Git about the
# folder and runs the detection.
MAX_SUGGESTION_CANDIDATES = 50
# Folders a recursive pattern (modules/**) never goes into: installed dependencies, besides the hidden ones.
PRUNED_FOLDER_NAMES = ("node_modules",)
RECURSIVE_WILDCARD = "**"
PNPM_PACKAGES_LINE = re.compile(r"^packages:\s*(.*)$")
GO_USE_LINE = re.compile(r"^use\s+(\(|\S+)")


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
# Suggested workspaces
# ---------------------------------------------------------------------------

def read_text(path):
    """The text of a file of the repository, or None when it cannot be read."""
    if is_link(path) or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8-sig") as text_file:
            return text_file.read()
    except (OSError, UnicodeDecodeError):
        return None


def package_workspaces(text):
    """The patterns of "workspaces" in a package.json: a list, or {"packages": [...]}."""
    try:
        manifest = json.loads(text)
    except ValueError:
        return []
    declared = manifest.get("workspaces") if isinstance(manifest, dict) else None
    if isinstance(declared, dict):
        declared = declared.get("packages")
    return [pattern for pattern in declared if isinstance(pattern, str)] if isinstance(declared, list) else []


def pnpm_packages(text):
    """The patterns of packages: in a pnpm-workspace.yaml, as a list below the key or inline (["libs/*"])."""
    patterns, inside = [], False
    for line in text.splitlines():
        # without_comment keeps a # inside quotes: packages: # the apps, or - "libs/*" # shared.
        content = without_comment(line)
        key = PNPM_PACKAGES_LINE.match(content)
        if key and key.group(1):
            inline = INLINE_LIST.match(key.group(1))
            return inline_items(inline.group(1)) if inline else [unquoted(key.group(1))]
        if key:
            inside = True
        elif inside and content:
            item = LIST_ITEM.match(content)
            if not item:
                break
            patterns.append(unquoted(item.group(1)))
    return patterns


def go_work_uses(text):
    """The folders a go.work uses: use ./api, or a use ( ... ) block."""
    folders, block = [], False
    for line in text.splitlines():
        stripped = line.split("//", 1)[0].strip()
        if block:
            if stripped == ")":
                block = False
            elif stripped:
                folders.append(unquoted(stripped))
            continue
        use = GO_USE_LINE.match(stripped)
        if use and use.group(1) == "(":
            block = True
        elif use:
            folders.append(unquoted(use.group(1)))
    return folders


def declared_patterns(project_root):
    """The folders, or patterns of folders, the package managers of the repository declare as workspaces."""
    patterns = []
    for name, parse in ((PACKAGE_MANIFEST, package_workspaces), (PNPM_WORKSPACE_FILE, pnpm_packages),
                        (GO_WORK_FILE, go_work_uses)):
        text = read_text(os.path.join(project_root, name))
        if text is not None:
            patterns += parse(text)
    return patterns


def is_pruned_name(name):
    """True for the name of a folder that is never a workspace: installed dependencies or a hidden folder."""
    return name in PRUNED_FOLDER_NAMES or name.startswith(".")


def relative_folder(project_root, path):
    return os.path.relpath(path, project_root).replace(os.sep, "/")


def matches_segments(parts, pattern):
    """True when the folders ``parts`` match the segments ``pattern``, where a ** segment stands for any
    number of folders, none included, and any other segment is matched with fnmatch."""
    if not pattern:
        return not parts
    if pattern[0] == RECURSIVE_WILDCARD:
        return any(matches_segments(parts[index:], pattern[1:]) for index in range(len(parts) + 1))
    return bool(parts) and fnmatch.fnmatchcase(parts[0], pattern[0]) and matches_segments(parts[1:], pattern[1:])


def recursive_matches(project_root, parts):
    """The folders a pattern with ** segments matches (modules/**, packages/**/app/**), below its base.

    The tree is walked once and the walk never goes into an is_pruned_name folder or through a link, so
    the installed dependencies of a monorepo are never read.
    """
    index = parts.index(RECURSIVE_WILDCARD)
    prefix, remainder = parts[:index], [part for part in parts[index:] if part]
    bases = glob.glob(os.path.join(project_root, *prefix)) if prefix else [project_root]
    folders = []
    for base in bases:
        if not os.path.isdir(base) or is_link(base) or is_pruned_name(os.path.basename(base)):
            continue
        for current, names, _ in os.walk(base):
            names[:] = sorted(name for name in names
                              if not is_pruned_name(name) and not is_link(os.path.join(current, name)))
            for name in names:
                path = os.path.join(current, name)
                if matches_segments(relative_folder(base, path).split("/"), remainder):
                    folders.append(relative_folder(project_root, path))
    return folders


def candidate_folders(project_root):
    """Folders that look like a workspace, sorted: the declared ones (declared_patterns), literal or with
    wildcards (recursive_matches for **), and those under CONVENTIONAL_PARENTS, without the is_pruned_name
    ones; suggestions checks that each one can be a workspace."""
    patterns = [pattern for pattern in declared_patterns(project_root) if not pattern.startswith("!")]
    patterns += [f"{parent}/*" for parent in CONVENTIONAL_PARENTS]
    folders = set()
    for pattern in patterns:
        pattern = pattern.strip().rstrip("/")
        while pattern.startswith("./"):
            pattern = pattern[2:]
        parts = pattern.split("/")
        if not pattern or pattern.startswith("/") or ".." in parts:
            continue
        if RECURSIVE_WILDCARD in parts:
            matches = recursive_matches(project_root, parts)
        else:
            matches = [relative_folder(project_root, match) for match in glob.glob(os.path.join(project_root, *parts))
                       if os.path.isdir(match)]
        folders.update(folder for folder in matches
                       if not any(is_pruned_name(part) for part in folder.split("/")))
    return sorted(folders)


def suggestions(project_root, profiles, root_resolved, entries, detect):
    """[{path, profiles, evidence}] of the folders whose own stack the root selection does not have.

    ``detect(profiles, folder)`` is the detection of the repository run on one folder. A folder that is a
    workspace, or sits inside or around one, is not suggested; nor is one inside another suggestion. Those
    do not count for MAX_SUGGESTION_CANDIDATES: only the folders detection looks into do.
    """
    taken = [entry["path"] for entry in entries]
    found, inspected = [], 0
    for folder in candidate_folders(project_root):
        if inspected == MAX_SUGGESTION_CANDIDATES:
            break
        if any(is_inside(folder, path) or is_inside(path, folder) for path in taken):
            continue
        if path_problem(project_root, folder) is not None:
            continue
        inspected += 1
        detection = detect(profiles, os.path.join(project_root, *folder.split("/")))
        stack = detection["primaryStack"]
        if not stack or stack in root_resolved:
            continue
        evidence = [dict(item, file=f"{folder}/{item['file']}") for item in detection["stacks"][stack]]
        found.append({"path": folder, "profiles": [stack], "evidence": evidence})
        taken.append(folder)
    return found


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


def without_comment(value):
    """The value without its YAML comment: a # at the start or after a space, outside quotes."""
    quote = None
    for index, character in enumerate(value):
        if quote:
            quote = None if character == quote else quote
        elif character in "\"'":
            quote = character
        elif character == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].strip()
    return value.strip()


def is_skipped_line(line):
    """True for a blank or comment line: inside a sequence YAML skips it without ending the sequence."""
    return not line.strip() or line.strip().startswith("#")


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


def added_profiles(root_resolved, workspaces):
    """The profiles only workspaces select, each once, in the order of the manifest."""
    return selected_profiles(root_resolved, workspaces)[len(root_resolved):]


def block_destination(workspace_path, destination):
    """Where the block a workspace profile publishes for ``destination`` goes (FOLDER_BLOCK_FILES)."""
    if destination in FOLDER_BLOCK_FILES:
        return f"{workspace_path}/{destination}"
    return destination


def frontmatter_patterns(lines, start, rule):
    """(patterns, end) of the paths: key at lines[start]: its patterns and the first line after them."""
    value = without_comment(PATHS_LINE.match(lines[start]).group(1))
    if value:
        inline = INLINE_LIST.match(value)
        patterns = inline_items(inline.group(1)) if inline else [unquoted(value)]
        return patterns, start + 1
    patterns, end = [], start + 1
    # A blank or comment line between the items stays out of the list without ending it.
    while end < len(lines) and (LIST_ITEM.match(lines[end]) or is_skipped_line(lines[end])):
        item = LIST_ITEM.match(lines[end])
        if item and not is_skipped_line(lines[end]):
            patterns.append(unquoted(without_comment(item.group(1))))
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


def scoped_references(text, rule_workspaces):
    """``text`` with each reference to a rule of ``rule_workspaces`` ({rule path: [workspace]}) moved to where
    the rule of each workspace goes: one reference for one workspace, or the references of every workspace
    joined with " or " and WORKSPACE_CHOICE_HINT, for a skill, subagent or command they share. A reference
    to a rule of the root selection stays as it is."""
    for rule_path, workspace_paths in sorted(rule_workspaces.items()):
        references = [RULE_REFERENCE.format(f"{WORKSPACE_RULES_DIRECTORY}/{workspace_path}/{rule_path}")
                      for workspace_path in sorted(workspace_paths)]
        replacement = references[0] if len(references) == 1 else " or ".join(references) + WORKSPACE_CHOICE_HINT
        text = text.replace(RULE_REFERENCE.format(rule_path), replacement)
    return text


def with_workspace_references(text, workspace_path, rule_paths):
    """The section of a stack, or a nested target, with its references to the rules of one workspace moved
    to where those rules go (scoped_references)."""
    return scoped_references(text, {rule_path: [workspace_path] for rule_path in rule_paths})


def is_inside(folder, workspace_path):
    """True when ``folder`` is the workspace or a folder under it."""
    return folder == workspace_path or folder.startswith(workspace_path + "/")


def index_content(workspace_path, rule_destinations):
    """The block of the AGENTS.md of a workspace: the rules of its own profiles, to read before working there."""
    lines = [f"## Workspace `{workspace_path}`", "",
             "This folder has profiles of its own. Read and follow these rules before you change its files:", ""]
    lines += [f"- Read and follow `{destination}`." for destination in sorted(rule_destinations)]
    return "\n".join(lines) + "\n"

