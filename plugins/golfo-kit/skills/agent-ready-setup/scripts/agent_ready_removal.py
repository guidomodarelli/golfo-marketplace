"""agent-ready remove: what it deletes, edits and keeps, and the removal itself.

It reads only the lockfile and the files, not the configuration, so a repository with an invalid manifest can
still be cleaned. The catalog loader comes from the caller, the entry point.
"""

import json
import os
import subprocess
import sys

import agent_ready_blocks as managed_blocks
import agent_ready_conflicts as conflicts_review
import agent_ready_content
import agent_ready_nested as nested
import agent_ready_pack_clis as pack_clis
import agent_ready_pack_mcp as pack_mcp
from agent_ready_actions import ACTION_DROP, ACTION_RETIRE_CONFLICT, LINKED_PARENT_REASON, classify_retired
from agent_ready_common import (
    LOCAL_ABSENT,
    LOCAL_NOT_A_FILE,
    LOCAL_SYMLINK,
    ProfileError,
    StateError,
    has_linked_parent,
    is_link,
    local_state,
    remove_empty_parents,
    run_quiet,
    sha256_of_file,
    write_text_atomically,
)
from agent_ready_layout import (
    AGENTS_SKELETON_NAME,
    CLAUDE_PROXY_RELATIVE_PATH,
    CLAUDE_VIEW_DIRECTORIES,
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_START,
    MANIFEST_RELATIVE_PATH,
    PROFILE_CATALOG_RELATIVE_PATH,
    claude_proxy_text,
    review_cache_module,
    settings_templates,
)
from agent_ready_lockfile import LOCK_RELATIVE_PATH, read_lock
from agent_ready_output import paint, write_line

REMOVAL_REMOVE = "remove"
REMOVAL_EDIT = "edit"
REMOVAL_KEEP = "keep"
REMOVAL_SYMBOLS = {REMOVAL_REMOVE: "-", REMOVAL_EDIT: "~", REMOVAL_KEEP: "="}
REMOVAL_COLORS = {REMOVAL_REMOVE: "retire", REMOVAL_EDIT: "update", REMOVAL_KEEP: "muted"}
# What each entry is, in the order a removal runs: the lockfile goes last, so an
# interrupted removal can run again and finish.
REMOVAL_KINDS = ("pack-mcp", "pack-cli", "browser", "git-config", "git-hook", "review-cache", "view", "asset", "block",
                 "instructions", "settings", "state", "config")
# Not a project path: the CLIs live in the cache of the user, shared by the repositories of the machine.
PACK_CLI_REMOVAL_LABEL = "CLIs of profile packs (cache of the user)"
# Same values as asset-sync-common.sh, which writes them.
HARD_LINK_VIEWS_MANIFEST = ".claude/.agent-ready-hard-link-views"
GIT_HOOK_SECTION = "hook.agent-ready-relink"
GIT_HOOK_COMMAND = "sh .agents/hooks/relink-hard-link-views.sh"
GIT_HOOK_FILE_NAME = "post-index-change"
GIT_HOOK_MARKER = "# agent-ready-setup: relinks .claude hard-link views detached by git."
# Same place as review-cache.py, which writes it: the info directory every worktree shares.
REVIEW_CACHE_INFO_PATH = "info/agent-ready/reviews.json"
# Same values as setup-browser-tools.py, which registers the servers.
BROWSER_SERVERS_MARKER = "/agent-ready-setup/browser-tools/"
BROWSER_REGISTRATION_FILES = (".mcp.json", ".codex/config.toml")
BROWSER_METADATA_RELATIVE_PATH = ".agents/browser-tools.json"
UNREGISTER_BROWSER_RELATIVE_PATH = "scripts/unregister-browser-servers.py"
MANAGED_ROOT_DIRECTORIES = (".agents", ".claude", ".codex", ".github")
CHANGED_DURING_REMOVAL_REASON = "changed while removing; it was kept"
# Same directories as SYNC_LOCK_DIRECTORY in bootstrap.sh and the session hook, and as
# MERGE_LOCK_DIRECTORY in managed-block.sh, which the detached instruction review holds.
SYNC_LOCK_RELATIVE_PATH = ".agents/.agent-ready-assets.lock"
INSTRUCTIONS_LOCK_RELATIVE_PATH = ".agents/.agent-ready-instructions.lock"
REMOVAL_LOCKS = (
    (SYNC_LOCK_RELATIVE_PATH, "an apply or a session sync is running"),
    (INSTRUCTIONS_LOCK_RELATIVE_PATH, "an AGENTS.md review is running"),
)
AMBIGUOUS_MARKERS_REASON = "its managed block markers are not one pair of whole lines; remove the block by hand"
# Kinds the lockfile inventories: while one of them is left, the lockfile stays for the next run.
LOCK_INVENTORIED_KINDS = ("asset", "view", "block")
INVENTORY_KEPT_REASON = "kept because a managed path could not be removed; run agent-ready remove again"


def removal_entry(path, action, reason, kind, local=None):
    """One line of the removal plan; ``local`` is the state it had, checked again before acting."""
    return {"path": path, "action": action, "reason": reason, "kind": kind, "local": local}


def view_mirrors(project_root, view, asset, base_hash):
    """True when a .claude path is a view an apply made of an .agents path."""
    view_path = os.path.join(project_root, view)
    asset_path = os.path.join(project_root, asset)
    if os.path.islink(view_path):
        target = os.path.normpath(os.path.join(os.path.dirname(view_path), os.readlink(view_path)))
        return target == os.path.normpath(asset_path)
    if not os.path.isfile(view_path):
        return False
    if os.path.isfile(asset_path) and os.path.samefile(view_path, asset_path):
        return True
    # A hard link that git detached still holds what the apply wrote.
    return base_hash is not None and sha256_of_file(view_path) == base_hash


def asset_removal_entries(project_root, locked_assets):
    """Managed assets go unless they changed since the last apply; project files always stay."""
    entries = []
    for destination, lock_entry in sorted(locked_assets.items()):
        local = local_state(os.path.join(project_root, destination))
        action, reason = classify_retired(local, lock_entry)
        if action == ACTION_DROP:
            if local != LOCAL_ABSENT:
                entries.append(removal_entry(destination, REMOVAL_KEEP, reason, "asset"))
            continue
        if has_linked_parent(project_root, destination):
            entries.append(removal_entry(destination, REMOVAL_KEEP, LINKED_PARENT_REASON, "asset"))
        elif action == ACTION_RETIRE_CONFLICT:
            entries.append(removal_entry(destination, REMOVAL_KEEP, "not a regular file", "asset"))
        elif local != lock_entry.get("sha256"):
            entries.append(removal_entry(destination, REMOVAL_KEEP,
                                         "changed since the last apply; delete it by hand if you no longer need it", "asset"))
        else:
            entries.append(removal_entry(destination, REMOVAL_REMOVE, "published by agent-ready-setup", "asset", local))
    return entries


def view_removal_entries(project_root, locked_assets):
    """Every .claude view of an .agents path: of managed assets and of the project's own rules."""
    entries = []
    for directory in CLAUDE_VIEW_DIRECTORIES:
        root = os.path.join(project_root, ".claude", directory)
        if is_link(root) or not os.path.isdir(root):
            continue
        for current, _, file_names in os.walk(root):
            for file_name in sorted(file_names):
                view = os.path.relpath(os.path.join(current, file_name), project_root).replace(os.sep, "/")
                asset = ".agents/" + view[len(".claude/"):]
                if has_linked_parent(project_root, view):
                    continue
                if view_mirrors(project_root, view, asset, locked_assets.get(asset, {}).get("sha256")):
                    entries.append(removal_entry(view, REMOVAL_REMOVE, f"view of {asset}", "view",
                                                 local_state(os.path.join(project_root, view))))
    return entries


def without_managed_block(text):
    """AGENTS.md text without its managed block, or None when it has no block.

    Like managed-block.sh, only whole lines are markers, so a line that mentions one stays.
    Raises ValueError when the markers are not exactly one pair in order.
    """
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == MANAGED_BLOCK_START]
    ends = [index for index, line in enumerate(lines) if line == MANAGED_BLOCK_END]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or starts[0] > ends[0]:
        raise ValueError(AMBIGUOUS_MARKERS_REASON)
    before = "\n".join(lines[:starts[0]]).rstrip()
    after = "\n".join(lines[ends[0] + 1:]).lstrip("\n").rstrip()
    remaining = "\n\n".join(part for part in (before, after) if part)
    return remaining + "\n" if remaining else ""


def normalized_lines(text):
    """Text compared without line endings or trailing spaces."""
    return [line.rstrip() for line in text.replace("\r\n", "\n").strip().split("\n")]


def template_skeletons(skill_dir, lock, load_catalog):
    """What a new AGENTS.md held outside the managed block: the template's skeleton, and the skeleton
    a profile of the locked selection publishes in its place (software-development). Empty when unknown."""
    skeletons = []
    template = ((lock or {}).get("merged") or {}).get("AGENTS.md", {}).get("template")
    path = os.path.join(skill_dir, template) if template else None
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as file_handle:
            try:
                skeletons.append(without_managed_block(file_handle.read()))
            except ValueError:
                pass
    try:
        catalog = load_catalog(skill_dir)
    except ProfileError:
        return skeletons
    for name in (lock or {}).get("profileOrder") or []:
        relative_root = catalog["profiles"].get(name, {}).get("assets")
        skeleton_path = os.path.join(skill_dir, relative_root, AGENTS_SKELETON_NAME) if relative_root else None
        if skeleton_path and os.path.isfile(skeleton_path):
            with open(skeleton_path, encoding="utf-8") as file_handle:
                skeletons.append(file_handle.read())
    return skeletons


def block_removal_entries(project_root, skill_dir, lock):
    """Each file with managed blocks loses them; a file that only held blocks goes, and so does the
    proxy next to a nested AGENTS.md that goes."""
    entries = []
    for destination, blocks in sorted(((lock or {}).get("blocks") or {}).items()):
        if destination == managed_blocks.INSTRUCTION_SECTIONS_DESTINATION:
            # The stack sections go with the managed block (instruction_removal_entries).
            continue
        path = os.path.join(project_root, destination)
        local = local_state(path)
        if local == LOCAL_ABSENT:
            continue
        if local in (LOCAL_SYMLINK, LOCAL_NOT_A_FILE) or managed_blocks.has_linked_directory(project_root, destination):
            entries.append(removal_entry(destination, REMOVAL_KEEP, "not a regular file; remove its managed blocks by hand",
                                         "block"))
            continue
        with open(path, encoding="utf-8", newline="") as file_handle:
            text = file_handle.read()
        try:
            remaining = text
            for block_id in sorted(blocks):
                remaining = managed_blocks.without_block(remaining, destination, block_id)
        except managed_blocks.MarkerError:
            entries.append(removal_entry(destination, REMOVAL_KEEP, AMBIGUOUS_MARKERS_REASON, "block"))
            continue
        if remaining == text:
            continue
        if managed_blocks.is_empty(remaining):
            entry = removal_entry(destination, REMOVAL_REMOVE, "only holds managed blocks", "block", local)
        else:
            entry = removal_entry(destination, REMOVAL_EDIT, "removes its managed blocks; the project's content stays",
                                  "block", local)
        entry["blocks"] = sorted(blocks)
        entries.append(entry)
        proxy = nested.proxy_of(destination)
        proxy_path = os.path.join(project_root, *proxy.split("/"))
        if entry["action"] == REMOVAL_REMOVE and nested.is_nested_destination(destination) and \
                nested.is_proxy(proxy_path, claude_proxy_text(skill_dir)):
            proxy_entry = removal_entry(proxy, REMOVAL_REMOVE, f"proxy of {destination}", "instructions",
                                        local_state(proxy_path))
            # It goes only if its AGENTS.md really goes: one edited meanwhile keeps its blocks out but stays.
            proxy_entry["proxyOf"] = destination
            entries.append(proxy_entry)
    return entries


def section_ids(lock):
    """Ids of the stack sections the lock records in AGENTS.md."""
    return sorted((((lock or {}).get("blocks") or {}).get(managed_blocks.INSTRUCTION_SECTIONS_DESTINATION) or {}))


def without_instruction_blocks(text, sections):
    """AGENTS.md without the stack sections and the managed block, or None when it holds none of them.

    Raises ValueError when the markers of either kind do not pair up.
    """
    destination = managed_blocks.INSTRUCTION_SECTIONS_DESTINATION
    try:
        stripped = text
        for block_id in sections:
            stripped = managed_blocks.without_block(stripped, destination, block_id)
    except managed_blocks.MarkerError as marker_error:
        raise ValueError(AMBIGUOUS_MARKERS_REASON) from marker_error
    remaining = without_managed_block(stripped)
    if remaining is None and stripped != text:
        return stripped.rstrip("\n") + "\n" if stripped.strip() else ""
    return remaining


def instruction_removal_entries(project_root, skill_dir, lock, load_catalog):
    """The managed block of AGENTS.md and the sections of the stacks go; the file goes too when nothing of
    the project is left."""
    path = os.path.join(project_root, "AGENTS.md")
    local = local_state(path)
    if local in (LOCAL_ABSENT, LOCAL_NOT_A_FILE):
        return []
    if local == LOCAL_SYMLINK:
        return [removal_entry("AGENTS.md", REMOVAL_KEEP, "a symlink; remove its managed block by hand", "instructions")]
    with open(path, encoding="utf-8", newline="") as file_handle:
        try:
            remaining = without_instruction_blocks(file_handle.read(), section_ids(lock))
        except ValueError:
            return [removal_entry("AGENTS.md", REMOVAL_KEEP, AMBIGUOUS_MARKERS_REASON, "instructions")]
    if remaining is None:
        return []
    skeletons = [normalized_lines(skeleton) for skeleton in template_skeletons(skill_dir, lock, load_catalog)]
    if remaining.strip() and normalized_lines(remaining) not in skeletons:
        entry = removal_entry("AGENTS.md", REMOVAL_EDIT,
                              "removes the managed block and the stack sections; the project's content stays",
                              "instructions", local)
        entry["blocks"] = section_ids(lock)
        return [entry]
    entries = [removal_entry("AGENTS.md", REMOVAL_REMOVE,
                             "only holds the managed block, the stack sections and the template", "instructions", local)]
    proxy = os.path.join(project_root, "CLAUDE.md")
    proxy_local = local_state(proxy)
    if proxy_local == sha256_of_file(os.path.join(skill_dir, CLAUDE_PROXY_RELATIVE_PATH)):
        entries.append(removal_entry("CLAUDE.md", REMOVAL_REMOVE, "proxy of AGENTS.md", "instructions", proxy_local))
    return entries


def without_managed_entries(document, template):
    """A Claude settings or Codex hooks document without the permissions and hooks its template manages."""
    result = json.loads(json.dumps(document))
    managed_rules = template.get("permissions", {}).get("allow", [])
    permissions = result.get("permissions")
    if isinstance(permissions, dict) and isinstance(permissions.get("allow"), list):
        permissions["allow"] = [rule for rule in permissions["allow"] if rule not in managed_rules]
        if not permissions["allow"]:
            del permissions["allow"]
        if not permissions:
            del result["permissions"]
    managed_commands = {handler.get("command") for groups in template.get("hooks", {}).values()
                        for group in groups for handler in group.get("hooks", [])}
    hooks = result.get("hooks")
    if not isinstance(hooks, dict):
        return result
    for event in list(hooks):
        if not isinstance(hooks[event], list):
            continue
        kept_groups = []
        for group in hooks[event]:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if isinstance(handlers, list) and handlers:
                handlers = [handler for handler in handlers
                            if not (isinstance(handler, dict) and handler.get("command") in managed_commands)]
                if not handlers:
                    continue
                group = dict(group, hooks=handlers)
            kept_groups.append(group)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    if not hooks:
        del result["hooks"]
    return result


def serialize_settings(document):
    """Settings in the format merge-managed-settings.py writes them."""
    return json.dumps(document, indent=2) + "\n"


def settings_without_managed_entries(project_root, destination, template_path):
    """(current document, document without the managed entries), or None when it cannot be read."""
    try:
        with open(os.path.join(project_root, destination), encoding="utf-8") as file_handle:
            current = json.load(file_handle)
        with open(template_path, encoding="utf-8") as file_handle:
            template = json.load(file_handle)
    except (OSError, ValueError):
        return None
    if not isinstance(current, dict):
        return None
    return current, without_managed_entries(current, template)


def settings_removal_entries(project_root, skill_dir):
    """Managed hooks and permissions leave the merged JSON files; custom entries stay."""
    entries = []
    for destination, template_path in settings_templates(skill_dir):
        local = local_state(os.path.join(project_root, destination))
        if local in (LOCAL_ABSENT, LOCAL_NOT_A_FILE):
            continue
        if local == LOCAL_SYMLINK:
            entries.append(removal_entry(destination, REMOVAL_KEEP, "a symlink; remove its agent-ready hooks by hand", "settings"))
            continue
        documents = settings_without_managed_entries(project_root, destination, template_path)
        if documents is None:
            entries.append(removal_entry(destination, REMOVAL_KEEP, "invalid JSON; remove its agent-ready hooks by hand", "settings"))
        elif documents[1] == documents[0]:
            continue
        elif not documents[1]:
            entries.append(removal_entry(destination, REMOVAL_REMOVE, "only holds agent-ready hooks and permissions", "settings", local))
        else:
            entries.append(removal_entry(destination, REMOVAL_EDIT,
                                         "removes the agent-ready hooks and permissions; custom entries stay", "settings", local))
    return entries


def pack_mcp_removal_entries(project_root, lock):
    """The provider configurations that hold MCP servers of profile packs, from the lock."""
    managed = (lock or {}).get("mcpServers", {})
    return [removal_entry(path, REMOVAL_EDIT, "unregisters the MCP servers of profile packs; the project's own stay", "pack-mcp")
            for path in pack_mcp.managed_files(project_root, managed)]


def pack_cli_removal_entries(project_root, lock):
    """The CLIs of profile packs this repository uses, from the lock; the cache keeps what other repositories use."""
    if not (lock or {}).get("clis"):
        return []
    return [removal_entry(PACK_CLI_REMOVAL_LABEL, REMOVAL_EDIT,
                          "stops using the CLIs of profile packs; the ones no other repository uses are deleted",
                          "pack-cli")]


def browser_removal_entries(project_root):
    """Browser MCP servers that agent-ready registered, and the metadata of this machine."""
    entries = []
    for destination in BROWSER_REGISTRATION_FILES:
        path = os.path.join(project_root, destination)
        if os.path.isfile(path) and not os.path.islink(path):
            with open(path, encoding="utf-8", errors="replace") as file_handle:
                if BROWSER_SERVERS_MARKER in file_handle.read():
                    entries.append(removal_entry(destination, REMOVAL_EDIT,
                                                 "unregisters the browser MCP servers agent-ready added; other servers stay", "browser"))
    if os.path.isfile(os.path.join(project_root, BROWSER_METADATA_RELATIVE_PATH)):
        entries.append(removal_entry(BROWSER_METADATA_RELATIVE_PATH, REMOVAL_REMOVE, "browser tools metadata of this machine", "browser"))
    # The line that ignores it lives in the .gitignore block of the common profile: block_removal_entries.
    return entries


def git_path(project_root, relative):
    """Absolute path of a file inside the Git directory, or None outside a Git worktree."""
    located = run_quiet(["git", "rev-parse", "--git-path", relative], cwd=project_root)
    return os.path.normpath(os.path.join(project_root, located)) if located else None


def display_path(project_root, path):
    """Path relative to the project, with forward slashes."""
    return os.path.relpath(path, project_root).replace(os.sep, "/")


def other_worktree_using_agent_ready(project_root):
    """Another worktree of the same repository with a lockfile: it shares the Git config and hooks."""
    listed = run_quiet(["git", "worktree", "list", "--porcelain"], cwd=project_root) or ""
    here = os.path.normcase(os.path.realpath(project_root))
    for line in listed.splitlines():
        if not line.startswith("worktree "):
            continue
        worktree = line[len("worktree "):]
        if os.path.normcase(os.path.realpath(worktree)) != here and os.path.isfile(os.path.join(worktree, LOCK_RELATIVE_PATH)):
            return worktree
    return None


def local_removal_entries(project_root):
    """Git hooks and files of agent-ready-setup that the lockfile does not list."""
    entries = []
    # Only the repository config: the setup registers the hook there, and removing it never touches the user's.
    if run_quiet(["git", "config", "--local", "--get", f"{GIT_HOOK_SECTION}.command"], cwd=project_root) == GIT_HOOK_COMMAND:
        entries.append(removal_entry(f"git config {GIT_HOOK_SECTION}", REMOVAL_REMOVE,
                                     "relinks .claude hard-link views after git operations", "git-config"))
    hook = git_path(project_root, f"hooks/{GIT_HOOK_FILE_NAME}")
    if hook and os.path.isfile(hook) and not os.path.islink(hook):
        with open(hook, encoding="utf-8", errors="replace") as file_handle:
            if GIT_HOOK_MARKER in file_handle.read():
                entries.append(removal_entry(display_path(project_root, hook), REMOVAL_REMOVE,
                                             "relinks .claude hard-link views after git operations", "git-hook", local_state(hook)))
    review_cache = git_path(project_root, REVIEW_CACHE_INFO_PATH)
    if review_cache and os.path.isfile(review_cache) and not os.path.islink(review_cache):
        entries.append(removal_entry(display_path(project_root, review_cache), REMOVAL_REMOVE,
                                     "cache of the AI reviews", "review-cache", local_state(review_cache)))
    sharing_worktree = other_worktree_using_agent_ready(project_root)
    if sharing_worktree:
        # The Git config and the hooks directory belong to every worktree of the repository.
        for entry in entries:
            entry.update(action=REMOVAL_KEEP, local=None,
                         reason=f"shared with the worktree {sharing_worktree}, which still uses agent-ready-setup")
    for path, reason in ((os.path.join(project_root, HARD_LINK_VIEWS_MANIFEST), "list of .claude hard-link views"),
                         (os.path.join(project_root, review_cache_module().SHARED_CACHE_RELATIVE_PATH),
                          "shared cache of the AI reviews (reviews.commit)"),
                         (conflicts_review.pending_path(project_root), "semantic conflicts of the last plan")):
        if path and os.path.isfile(path) and not os.path.islink(path):
            entries.append(removal_entry(display_path(project_root, path), REMOVAL_REMOVE, reason, "state", local_state(path)))
    return entries


def config_removal_entries(project_root):
    """The manifest and the lockfile, which make agent-ready-setup manage the repository."""
    entries = []
    for relative, reason in ((MANIFEST_RELATIVE_PATH, "agent-ready-setup configuration of the repository"),
                             (LOCK_RELATIVE_PATH, "lockfile of the managed assets")):
        local = local_state(os.path.join(project_root, relative))
        if local == LOCAL_ABSENT:
            continue
        if local in (LOCAL_SYMLINK, LOCAL_NOT_A_FILE):
            entries.append(removal_entry(relative, REMOVAL_KEEP, "not a regular file", "config"))
        else:
            entries.append(removal_entry(relative, REMOVAL_REMOVE, reason, "config", local))
    return entries


def removal_content_dir(skill_dir, lock):
    """The skill directory with the content that generated this repository, to recognize what it wrote.

    The engine carries no templates: without the content of the lock, the generated AGENTS.md and its
    blocks look like the project's own and stay.
    """
    if not lock or os.path.isfile(os.path.join(skill_dir, PROFILE_CATALOG_RELATIVE_PATH)):
        return skill_dir
    try:
        return agent_ready_content.locked_content_dir(skill_dir, lock.get("source"))
    except ProfileError as content_error:
        write_line(f"WARNING: agent-ready remove: the content of the lock is not available ({content_error}); "
                   "the generated AGENTS.md text and managed blocks are kept as the project's own", sys.stderr)
        return skill_dir


def plan_removal(project_root, skill_dir, load_catalog):
    """What `agent-ready remove` deletes, edits and keeps, without writing anything.

    It reads only the lockfile and the files themselves, not the configuration, so a
    repository with an invalid manifest can still be cleaned.
    """
    lock = read_lock(project_root)
    locked_assets = lock["assets"] if lock else {}
    content_dir = removal_content_dir(skill_dir, lock)
    entries = (
        pack_mcp_removal_entries(project_root, lock)
        + pack_cli_removal_entries(project_root, lock)
        + browser_removal_entries(project_root)
        + local_removal_entries(project_root)
        + view_removal_entries(project_root, locked_assets)
        + asset_removal_entries(project_root, locked_assets)
        + block_removal_entries(project_root, content_dir, lock)
        + instruction_removal_entries(project_root, content_dir, lock, load_catalog)
        + settings_removal_entries(project_root, skill_dir)
        + config_removal_entries(project_root)
    )
    for entry in entries:
        # A directory linked to ~/.claude or another shared place leads outside the repository.
        if entry["action"] != REMOVAL_KEEP and entry["kind"] not in ("git-config", "git-hook", "pack-cli") \
                and has_linked_parent(project_root, entry["path"]):
            entry.update(action=REMOVAL_KEEP, reason=LINKED_PARENT_REASON, local=None)
    entries.sort(key=lambda entry: (REMOVAL_KINDS.index(entry["kind"]), entry["path"]))
    return {"entries": entries, "changes": sum(entry["action"] != REMOVAL_KEEP for entry in entries)}


def unchanged_since_plan(project_root, entry):
    """True when a file still has the state the plan saw."""
    return entry["local"] is None or local_state(os.path.join(project_root, entry["path"])) == entry["local"]


def remove_managed_roots_if_empty(project_root):
    """Drop .agents, .claude, .codex and .github when the removal left them empty."""
    for directory in MANAGED_ROOT_DIRECTORIES:
        path = os.path.join(project_root, directory)
        if os.path.isdir(path) and not is_link(path):
            try:
                os.rmdir(path)
            except OSError:
                pass


def unregister_pack_mcp_servers(project_root, report):
    """Drop every MCP server of the packs that the lock records; the project's own servers stay."""
    lock = read_lock(project_root) or {}
    result = pack_mcp.unregister_all(project_root, lock.get("mcpServers", {}))
    for path, names in result["removed"].items():
        if names:
            report["edited"].append(path)
    report["failed"] += result["failed"]


def uninstall_pack_clis(project_root, report):
    """This repository stops using the CLIs of the packs; the cache deletes the ones no repository uses."""
    try:
        pack_clis.uninstall_all(project_root)
    except (pack_clis.InstallError, OSError) as problem:
        report["failed"].append(f"CLIs of profile packs: {problem}")
        return
    report["edited"].append(PACK_CLI_REMOVAL_LABEL)


def unregister_browser_servers(project_root, skill_dir, report):
    """Run the dedicated entry point once; it knows how to edit the TOML of Codex."""
    command = [sys.executable, os.path.join(skill_dir, UNREGISTER_BROWSER_RELATIVE_PATH), "--project", project_root]
    completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", check=False)
    # One "<removed|edited><TAB><path>" line per file the entry point changed.
    for line in completed.stdout.splitlines():
        outcome, _, changed_path = line.partition("\t")
        if outcome in ("removed", "edited") and changed_path:
            report[outcome].append(changed_path)
    if completed.returncode != 0:
        problem = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "the browser servers could not be removed"
        report["failed"].append(problem)


def sections_remain(project_root, sections):
    """True when AGENTS.md still holds one of these stack sections, or its markers cannot tell."""
    path = os.path.join(project_root, managed_blocks.INSTRUCTION_SECTIONS_DESTINATION)
    if not sections or local_state(path) in (LOCAL_ABSENT, LOCAL_NOT_A_FILE):
        return False
    if local_state(path) == LOCAL_SYMLINK:
        return True
    with open(path, encoding="utf-8", newline="") as file_handle:
        text = file_handle.read()
    try:
        return bool(set(sections) & set(managed_blocks.parse(text, managed_blocks.INSTRUCTION_SECTIONS_DESTINATION)))
    except managed_blocks.MarkerError:
        return True


def remove_blocks_now(project_root, entry, report):
    """Take the blocks of one file out of what it holds now; False when the file keeps them."""
    path = os.path.join(project_root, entry["path"])
    if local_state(path) in (LOCAL_ABSENT, LOCAL_SYMLINK, LOCAL_NOT_A_FILE) or \
            managed_blocks.has_linked_directory(project_root, entry["path"]):
        report["kept"].append(f"{entry['path']}: {CHANGED_DURING_REMOVAL_REASON}")
        return False
    with open(path, encoding="utf-8", newline="") as file_handle:
        remaining = file_handle.read()
    try:
        for block_id in entry["blocks"]:
            remaining = managed_blocks.without_block(remaining, entry["path"], block_id)
    except managed_blocks.MarkerError:
        report["kept"].append(f"{entry['path']}: {AMBIGUOUS_MARKERS_REASON}")
        return False
    if managed_blocks.is_empty(remaining):
        os.unlink(path)
        report["removed"].append(entry["path"])
    else:
        write_text_atomically(path, remaining)
        report["edited"].append(entry["path"])
    return True


def apply_removal_entry(project_root, skill_dir, entry, report):
    """Carry out one removal or edit, after checking that the file did not change."""
    path = os.path.join(project_root, entry["path"])
    if entry["kind"] == "git-config":
        if subprocess.call(["git", "config", "--remove-section", GIT_HOOK_SECTION], cwd=project_root,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            report["removed"].append(entry["path"])
        else:
            report["failed"].append(f"{entry['path']}: git config --remove-section failed")
        return
    if not unchanged_since_plan(project_root, entry):
        report["kept"].append(f"{entry['path']}: {CHANGED_DURING_REMOVAL_REASON}")
        return
    if entry["action"] == REMOVAL_REMOVE:
        os.unlink(path)
        if entry["kind"] in ("view", "asset"):
            # Only the folders that assets created; the Git directory keeps its own.
            remove_empty_parents(project_root, path)
        elif entry["kind"] == "review-cache":
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
        report["removed"].append(entry["path"])
        return
    if entry["kind"] == "instructions":
        # Read and close before replacing: Windows refuses to replace an open file.
        with open(path, encoding="utf-8", newline="") as file_handle:
            current = file_handle.read()
        write_text_atomically(path, without_instruction_blocks(current, entry.get("blocks", [])))
    else:
        template_path = dict(settings_templates(skill_dir))[entry["path"]]
        write_text_atomically(path, serialize_settings(settings_without_managed_entries(project_root, entry["path"], template_path)[1]))
    report["edited"].append(entry["path"])


def apply_removal(project_root, skill_dir, plan):
    """Remove agent-ready-setup from the repository following a plan; returns what happened."""
    report = {"removed": [], "edited": [], "kept": [], "failed": []}
    report["kept"] += [f"{entry['path']}: {entry['reason']}" for entry in plan["entries"] if entry["action"] == REMOVAL_KEEP]
    # Stack sections that stay in AGENTS.md need the lock: it is how the next remove finds them.
    sections = section_ids(read_lock(project_root))
    browser_done = False
    pack_mcp_done = False
    inventory_left = False
    for entry in plan["entries"]:
        if entry["action"] == REMOVAL_KEEP:
            continue
        if entry["kind"] == "pack-mcp":
            if not pack_mcp_done:
                failures_before = len(report["failed"])
                unregister_pack_mcp_servers(project_root, report)
                pack_mcp_done = True
                # The lock is the only record of which servers are the packs': it stays for a retry.
                inventory_left = inventory_left or len(report["failed"]) > failures_before
            continue
        if entry["kind"] == "pack-cli":
            failures_before = len(report["failed"])
            uninstall_pack_clis(project_root, report)
            # The lock says which CLIs the repository used: it stays for a retry.
            inventory_left = inventory_left or len(report["failed"]) > failures_before
            continue
        if entry["kind"] == "browser":
            if not browser_done:
                unregister_browser_servers(project_root, skill_dir, report)
                browser_done = True
            continue
        if entry["kind"] == "config" and (inventory_left or sections_remain(project_root, sections)):
            # Without the lockfile, the next run would not know which files are still managed.
            report["kept"].append(f"{entry['path']}: {INVENTORY_KEPT_REASON}")
            continue
        if entry["kind"] == "block":
            try:
                # A file that keeps its blocks keeps the lock, so the next remove finds them.
                inventory_left = not remove_blocks_now(project_root, entry, report) or inventory_left
            except OSError as caught_error:
                report["failed"].append(f"{entry['path']}: {caught_error}")
                inventory_left = True
            continue
        if entry.get("proxyOf") and entry["proxyOf"] not in report["removed"]:
            report["kept"].append(f"{entry['path']}: {entry['proxyOf']} stays, and so does its proxy")
            continue
        try:
            apply_removal_entry(project_root, skill_dir, entry, report)
        except OSError as caught_error:
            report["failed"].append(f"{entry['path']}: {caught_error}")
            inventory_left = inventory_left or entry["kind"] in LOCK_INVENTORIED_KINDS
    return report


def remove_from_repository(project_root, skill_dir, load_catalog):
    """Plan again and remove holding the locks of apply, the session hook and the AGENTS.md review.

    Without them, a projection or a review already running would write the assets, the
    lockfile or AGENTS.md back after the removal reported success.
    """
    held = []
    agents_directory = os.path.join(project_root, ".agents")
    try:
        if not is_link(agents_directory):
            os.makedirs(agents_directory, exist_ok=True)
            for relative, running in REMOVAL_LOCKS:
                try:
                    os.mkdir(os.path.join(project_root, relative))
                except FileExistsError:
                    raise StateError(f"{running} ({relative} exists); run agent-ready remove again when it finishes, "
                                     "or delete that directory if no agent-ready process is running") from None
                held.append(relative)
        report = apply_removal(project_root, skill_dir, plan_removal(project_root, skill_dir, load_catalog))
    finally:
        for relative in reversed(held):
            try:
                os.rmdir(os.path.join(project_root, relative))
            except OSError:
                pass
    remove_managed_roots_if_empty(project_root)
    return report


def print_removal_plan(plan, stream):
    """Text plan: one line per path with what happens to it and why."""
    for entry in plan["entries"]:
        symbol = REMOVAL_SYMBOLS[entry["action"]]
        label = paint(f"{symbol} {entry['action']:<6}", REMOVAL_COLORS[entry["action"]], stream)
        write_line(f"  {label} {entry['path']}  ({entry['reason']})", stream)
