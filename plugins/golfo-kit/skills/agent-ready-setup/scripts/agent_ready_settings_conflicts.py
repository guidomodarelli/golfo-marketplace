"""Hooks, permissions and settings that collide across the layers each provider reads.

Layers, from the engine's own to the user's:

* ``golfo-kit``: what the apply merges (``assets/common/settings.json``, ``assets/codex/hooks.json``);
* ``project``: the rest of ``.claude/settings.json`` or ``.codex/hooks.json``;
* ``local``: ``.claude/settings.local.json``;
* ``user``: ``~/.claude/settings.json`` (or ``$CLAUDE_CONFIG_DIR``) and ``$CODEX_HOME/hooks.json``.

Three checks, read-only:

* a permission pattern that one layer allows and another (or the same) denies;
* the same hook (event and command) registered in two layers, so it runs twice;
* two different formatters on the same event with overlapping matchers, rewriting the same file.
"""

import json
import os
import re
import shlex

import agent_ready_machine as machine

PROVIDER_CLAUDE = "claude"
PROVIDER_CODEX = "codex"
LAYER_GOLFO = "golfo-kit"
LAYER_PROJECT = "project"
LAYER_LOCAL = "local"
LAYER_USER = "user"
CLAUDE_TEMPLATE_RELATIVE_PATH = "assets/common/settings.json"
CODEX_TEMPLATE_RELATIVE_PATH = "assets/codex/hooks.json"
FORMATTERS_RELATIVE_PATH = "assets/formatters.json"
CLAUDE_PROJECT_SETTINGS = ".claude/settings.json"
CLAUDE_LOCAL_SETTINGS = ".claude/settings.local.json"
CODEX_PROJECT_HOOKS = ".codex/hooks.json"
CLAUDE_USER_SETTINGS = "settings.json"
CODEX_USER_HOOKS = "hooks.json"
PERMISSION_ALLOW = "allow"
PERMISSION_DENY = "deny"
DISABLE_ALL_HOOKS_KEY = "disableAllHooks"
# Shell operators between the invocations of a compound hook command.
COMMAND_SEPARATORS = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
# Words of a formatter command that name the runner or the formatter, never a file to format.
COMMAND_WORDS = {"npx", "pnpm", "pnpx", "yarn", "bunx", "bun", "exec", "dlx", "run", "uvx", "pipx", "python", "python3",
                 "prettier", "biome", "format", "check", "lint", "eslint", "dprint", "fmt", "black", "ruff",
                 "gofmt", "goimports", "rustfmt", "cargo"}
# A matcher that is empty, missing or a catch-all applies to every tool.
MATCH_EVERYTHING = ("", "*", ".*")
# The tools a hook matcher names, to test two matchers against the same tool.
KNOWN_TOOL_NAMES = ("Bash", "Edit", "MultiEdit", "Write", "Read", "Glob", "Grep", "LS", "NotebookEdit",
                    "NotebookRead", "WebFetch", "WebSearch", "Task", "TodoWrite", "apply_patch", "shell")


def skill_path(skill_dir, relative):
    return os.path.join(skill_dir, *relative.split("/"))


def read_json(path):
    """The JSON object of a regular file (BOM accepted), or None."""
    if not os.path.isfile(path) or os.path.islink(path):
        return None
    try:
        with open(path, encoding="utf-8-sig") as json_file:
            data = json.load(json_file)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def hook_entries(data):
    """[(event, matcher, command)] of a settings or hooks.json object."""
    entries = []
    hooks = (data or {}).get("hooks")
    if not isinstance(hooks, dict):
        return entries
    for event, groups in hooks.items():
        for group in groups if isinstance(groups, list) else []:
            if not isinstance(group, dict):
                continue
            matcher = str(group.get("matcher", "") or "")
            for hook in group.get("hooks") or []:
                if isinstance(hook, dict) and hook.get("command"):
                    entries.append((event, matcher, str(hook["command"])))
    return entries


def permission_rules(data):
    """{allow: set, deny: set} of the permissions of a Claude Code settings object."""
    permissions = (data or {}).get("permissions")
    rules = {PERMISSION_ALLOW: set(), PERMISSION_DENY: set()}
    if isinstance(permissions, dict):
        for kind in rules:
            rules[kind] = {str(rule) for rule in permissions.get(kind) or [] if isinstance(rule, str)}
    return rules


def without_template(data, template):
    """A merged project file without what the template put there: its hooks and permissions."""
    if data is None:
        return None
    template_hooks = set(hook_entries(template))
    template_rules = permission_rules(template)
    hooks = {}
    for event, matcher, command in hook_entries(data):
        if (event, matcher, command) not in template_hooks:
            hooks.setdefault(event, []).append({"matcher": matcher, "hooks": [{"type": "command", "command": command}]})
    rules = permission_rules(data)
    return {"hooks": hooks,
            "permissions": {kind: sorted(rules[kind] - template_rules[kind]) for kind in rules}}


def layers(project_root, skill_dir):
    """[{provider, layer, file, data}] of every configuration this report compares."""
    claude_template = read_json(skill_path(skill_dir, CLAUDE_TEMPLATE_RELATIVE_PATH))
    codex_template = read_json(skill_path(skill_dir, CODEX_TEMPLATE_RELATIVE_PATH))
    claude_project = read_json(os.path.join(project_root, CLAUDE_PROJECT_SETTINGS))
    claude_user = os.path.join(machine.claude_home(), CLAUDE_USER_SETTINGS)
    codex_user = os.path.join(machine.codex_home(), CODEX_USER_HOOKS)
    found = [
        {"provider": PROVIDER_CLAUDE, "layer": LAYER_GOLFO, "file": f"{CLAUDE_PROJECT_SETTINGS} ({LAYER_GOLFO})",
         "data": claude_template},
        {"provider": PROVIDER_CLAUDE, "layer": LAYER_PROJECT, "file": CLAUDE_PROJECT_SETTINGS,
         "data": without_template(claude_project, claude_template), "raw": claude_project},
        {"provider": PROVIDER_CLAUDE, "layer": LAYER_LOCAL, "file": CLAUDE_LOCAL_SETTINGS,
         "data": read_json(os.path.join(project_root, CLAUDE_LOCAL_SETTINGS))},
        {"provider": PROVIDER_CLAUDE, "layer": LAYER_USER, "file": machine.home_display(claude_user),
         "data": read_json(claude_user)},
        {"provider": PROVIDER_CODEX, "layer": LAYER_GOLFO, "file": f"{CODEX_PROJECT_HOOKS} ({LAYER_GOLFO})",
         "data": codex_template},
        {"provider": PROVIDER_CODEX, "layer": LAYER_PROJECT, "file": CODEX_PROJECT_HOOKS,
         "data": without_template(read_json(os.path.join(project_root, CODEX_PROJECT_HOOKS)), codex_template)},
        {"provider": PROVIDER_CODEX, "layer": LAYER_USER, "file": machine.home_display(codex_user),
         "data": read_json(codex_user)},
    ]
    return [layer for layer in found if layer["data"]]


def permission_conflicts(found):
    """A Claude Code pattern allowed in one layer and denied in another (or the same)."""
    allowed, denied = {}, {}
    for layer in found:
        if layer["provider"] != PROVIDER_CLAUDE:
            continue
        rules = permission_rules(layer["data"])
        for pattern in rules[PERMISSION_ALLOW]:
            allowed.setdefault(pattern, []).append(layer["file"])
        for pattern in rules[PERMISSION_DENY]:
            denied.setdefault(pattern, []).append(layer["file"])
    return [{"pattern": pattern, "allow": allowed[pattern], "deny": denied[pattern]}
            for pattern in sorted(set(allowed) & set(denied))]


def duplicated_hooks(found):
    """The same command on the same event in two layers of one provider, with matchers that overlap:
    it runs once per registration."""
    places = {}
    for layer in found:
        for event, matcher, command in set(hook_entries(layer["data"])):
            places.setdefault((layer["provider"], event, command), []).append((layer["file"], matcher))
    findings = []
    for (provider, event, command), registrations in sorted(places.items()):
        files = set()
        for position, (first_file, first_matcher) in enumerate(registrations):
            for second_file, second_matcher in registrations[position + 1:]:
                if first_file != second_file and matchers_overlap(first_matcher, second_matcher):
                    files.update((first_file, second_file))
        if files:
            ordered = [registration[0] for registration in registrations if registration[0] in files]
            findings.append({"provider": provider, "event": event, "command": command,
                             "files": list(dict.fromkeys(ordered))})
    return findings


def matcher_candidates(*matchers):
    """Tool names to try two matchers against: the known tools and every name the matchers spell."""
    candidates = set(KNOWN_TOOL_NAMES)
    for matcher in matchers:
        candidates.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", matcher))
    return candidates


def matcher_matches(matcher, tool):
    """True when a hook matcher fires on a tool: an exact name, or a regular expression over it."""
    if matcher in MATCH_EVERYTHING or matcher == tool:
        return True
    return re.fullmatch(matcher, tool) is not None


def matchers_overlap(first, second):
    """True when two hook matchers can fire on the same tool. A matcher that is not a valid
    expression cannot be ruled out, so it overlaps."""
    if first in MATCH_EVERYTHING or second in MATCH_EVERYTHING:
        return True
    try:
        re.compile(first)
        re.compile(second)
    except re.error:
        return True
    return any(matcher_matches(first, tool) and matcher_matches(second, tool)
               for tool in matcher_candidates(first, second))


def formatter_of(command, formatters):
    """The formatter a hook command runs in a mode that rewrites files, or None."""
    for name, definition in formatters.items():
        if not re.search(definition["command"], command):
            continue
        if definition.get("writes") and not re.search(definition["writes"], command):
            return None
        if definition.get("checkOnly") and re.search(definition["checkOnly"], command):
            return None
        return name
    return None


def formatter_targets(command):
    """The paths a formatter command names, or None when it can reach any file of the repository
    (no path, ".", a glob or a variable such as $FILE that the hook fills in)."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    targets = set()
    for token in tokens:
        # Flags, the runner and the formatter with its subcommand are not targets; any other
        # positional word is one, a bare directory such as src included.
        if token.startswith("-") or token.lower() in COMMAND_WORDS or os.path.basename(token).split(".")[0] in COMMAND_WORDS:
            continue
        if token in (".", "./") or any(marker in token for marker in ("$", "*", "?", "{")):
            return None
        targets.add(token[2:] if token.startswith("./") else token.rstrip("/"))
    return targets or None


def targets_overlap(first, second):
    """True unless both commands name paths and none of one contains or equals one of the other."""
    first, second = formatter_targets(first), formatter_targets(second)
    if first is None or second is None:
        return True
    return any(one == other or one.startswith(other + "/") or other.startswith(one + "/")
               for one in first for other in second)


def competing_formatters(found, skill_dir):
    """Two different formatters that rewrite files on the same event of a provider, with matchers
    that overlap. A check-only invocation (prettier --check, black --check) rewrites nothing."""
    with open(skill_path(skill_dir, FORMATTERS_RELATIVE_PATH), encoding="utf-8") as formatters_file:
        formatters = json.load(formatters_file)
    hooks = []
    for layer in found:
        for event, matcher, command in hook_entries(layer["data"]):
            # Each invocation of a compound command keeps its own flags: --write of one is not of another.
            for invocation in COMMAND_SEPARATORS.split(command):
                name = formatter_of(invocation.strip(), formatters)
                if name:
                    hooks.append({"provider": layer["provider"], "event": event, "matcher": matcher,
                                  "formatter": name, "command": invocation.strip(), "file": layer["file"]})
    findings, seen = [], set()
    for position, first in enumerate(hooks):
        for second in hooks[position + 1:]:
            if (first["provider"], first["event"]) != (second["provider"], second["event"]):
                continue
            if first["formatter"] == second["formatter"] or not matchers_overlap(first["matcher"], second["matcher"]):
                continue
            if not targets_overlap(first["command"], second["command"]):
                continue
            key = (first["provider"], first["event"], frozenset((first["formatter"], second["formatter"])))
            if key not in seen:
                seen.add(key)
                findings.append({"provider": first["provider"], "event": first["event"], "hooks": [first, second]})
    return findings


def claude_hooks_disabled(found):
    """The effective disableAllHooks of Claude Code: local over project over user."""
    disabled = False
    for layer_name in (LAYER_USER, LAYER_PROJECT, LAYER_LOCAL):
        for layer in found:
            if layer["provider"] == PROVIDER_CLAUDE and layer["layer"] == layer_name:
                value = layer.get("raw", layer["data"]).get(DISABLE_ALL_HOOKS_KEY)
                if isinstance(value, bool):
                    disabled = value
    return disabled


def report(project_root, skill_dir, hooks_enabled, permissions_enabled):
    """{permissions, duplicatedHooks, formatters} of the enabled checks."""
    found = layers(project_root, skill_dir)
    result = {}
    if permissions_enabled:
        result["permissions"] = permission_conflicts(found)
    if hooks_enabled:
        # Hooks that disableAllHooks turns off never run: they collide with nothing.
        running = found if not claude_hooks_disabled(found) else [
            layer for layer in found if layer["provider"] != PROVIDER_CLAUDE]
        result["duplicatedHooks"] = duplicated_hooks(running)
        result["formatters"] = competing_formatters(running, skill_dir)
    return result
