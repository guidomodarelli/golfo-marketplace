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
# A matcher that is empty or missing applies to every tool.
MATCH_EVERYTHING = ("", "*")


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
    claude_user = os.path.join(machine.claude_home(), CLAUDE_USER_SETTINGS)
    codex_user = os.path.join(machine.codex_home(), CODEX_USER_HOOKS)
    found = [
        {"provider": PROVIDER_CLAUDE, "layer": LAYER_GOLFO, "file": f"{CLAUDE_PROJECT_SETTINGS} ({LAYER_GOLFO})",
         "data": claude_template},
        {"provider": PROVIDER_CLAUDE, "layer": LAYER_PROJECT, "file": CLAUDE_PROJECT_SETTINGS,
         "data": without_template(read_json(os.path.join(project_root, CLAUDE_PROJECT_SETTINGS)), claude_template)},
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
    """The same command on the same event in two layers of one provider: it runs twice."""
    places = {}
    for layer in found:
        for event, _, command in set(hook_entries(layer["data"])):
            places.setdefault((layer["provider"], event, command), []).append(layer["file"])
    return [{"provider": provider, "event": event, "command": command, "files": files}
            for (provider, event, command), files in sorted(places.items()) if len(files) > 1]


def matchers_overlap(first, second):
    """True when two hook matchers can fire on the same tool."""
    if first in MATCH_EVERYTHING or second in MATCH_EVERYTHING:
        return True
    return bool(set(first.split("|")) & set(second.split("|")))


def competing_formatters(found, skill_dir):
    """Two different formatters on the same event of a provider with overlapping matchers."""
    with open(skill_path(skill_dir, FORMATTERS_RELATIVE_PATH), encoding="utf-8") as formatters_file:
        patterns = {name: re.compile(pattern) for name, pattern in json.load(formatters_file).items()}
    hooks = []
    for layer in found:
        for event, matcher, command in hook_entries(layer["data"]):
            for name, pattern in patterns.items():
                if pattern.search(command):
                    hooks.append({"provider": layer["provider"], "event": event, "matcher": matcher,
                                  "formatter": name, "command": command, "file": layer["file"]})
                    break
    findings, seen = [], set()
    for position, first in enumerate(hooks):
        for second in hooks[position + 1:]:
            if (first["provider"], first["event"]) != (second["provider"], second["event"]):
                continue
            if first["formatter"] == second["formatter"] or not matchers_overlap(first["matcher"], second["matcher"]):
                continue
            key = (first["provider"], first["event"], frozenset((first["formatter"], second["formatter"])))
            if key not in seen:
                seen.add(key)
                findings.append({"provider": first["provider"], "event": first["event"], "hooks": [first, second]})
    return findings


def report(project_root, skill_dir, hooks_enabled, permissions_enabled):
    """{permissions, duplicatedHooks, formatters} of the enabled checks."""
    found = layers(project_root, skill_dir)
    result = {}
    if permissions_enabled:
        result["permissions"] = permission_conflicts(found)
    if hooks_enabled:
        result["duplicatedHooks"] = duplicated_hooks(found)
        result["formatters"] = competing_formatters(found, skill_dir)
    return result
