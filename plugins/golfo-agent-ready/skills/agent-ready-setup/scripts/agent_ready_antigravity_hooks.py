"""The hooks of Antigravity: the managed group of .agents/hooks.json, and its shape for the comparisons.

Antigravity reads its hooks from .agents/hooks.json, keyed by a hook name: each name maps events to
handlers. PreToolUse and PostToolUse take matcher groups (``{"matcher", "hooks": [...]}``); the other
events (SessionStart, PreInvocation, PostInvocation, Stop) take the handlers directly. The apply owns one
name, MANAGED_GROUP, replaced whole from assets/antigravity/hooks.json; every other name is the project's
and is never touched. ``as_claude_hooks`` turns the file into the shape of .claude/settings.json and
.codex/hooks.json, so the hook comparisons read the three providers alike.
"""

import json
import os

MANAGED_GROUP = "agent-ready"
HOOKS_RELATIVE_PATH = ".agents/hooks.json"
TEMPLATE_RELATIVE_PATH = "assets/antigravity/hooks.json"
HOOKS_KEY = "hooks"
MATCHER_KEY = "matcher"
COMMAND_KEY = "command"
ENABLED_KEY = "enabled"
# The events whose handlers sit in matcher groups; the rest take the handlers directly.
TOOL_EVENTS = ("PreToolUse", "PostToolUse")


class HooksError(ValueError):
    """A .agents/hooks.json that is not the shape Antigravity reads; it is left as it is."""


def validate(document):
    """Raise HooksError unless ``document`` is {name: {event: [handler or matcher group]}}."""
    if not isinstance(document, dict):
        raise HooksError(f"{HOOKS_RELATIVE_PATH} must be an object of hook names")
    for name, events in document.items():
        if not isinstance(events, dict):
            raise HooksError(f"{HOOKS_RELATIVE_PATH}: the hook {name!r} must be an object of events")
        for event, items in events.items():
            if event == ENABLED_KEY:
                continue
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise HooksError(f"{HOOKS_RELATIVE_PATH}: {name}.{event} must be an array of objects")
    return document


def read(path):
    """The validated document of ``path``, or {} when it does not exist."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as hooks_file:
        try:
            return validate(json.load(hooks_file))
        except ValueError as invalid:
            raise HooksError(f"{HOOKS_RELATIVE_PATH} is not valid JSON: {invalid}") from invalid


def merged(current, template):
    """``current`` with the managed group of ``template`` in place of its own; the other groups stay first."""
    result = {name: events for name, events in current.items() if name != MANAGED_GROUP}
    if MANAGED_GROUP in template:
        result[MANAGED_GROUP] = template[MANAGED_GROUP]
    return result


def without_managed(current):
    """``current`` without the managed group: what agent-ready remove, or dropping Antigravity, leaves."""
    return {name: events for name, events in current.items() if name != MANAGED_GROUP}


def serialize(document):
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def as_claude_hooks(document, only_managed=None):
    """``{"hooks": {event: [{"matcher", "hooks"}]}}`` of an Antigravity document, like .codex/hooks.json.

    ``only_managed`` True keeps only the managed group, False only the project's; None keeps both. A hook
    name with ``enabled: false`` runs nothing, so it is left out.
    """
    hooks = {}
    for name, events in (document or {}).items():
        if not isinstance(events, dict) or events.get(ENABLED_KEY) is False:
            continue
        if only_managed is not None and (name == MANAGED_GROUP) != only_managed:
            continue
        for event, items in events.items():
            if event == ENABLED_KEY or not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                if event in TOOL_EVENTS:
                    group = {MATCHER_KEY: str(item.get(MATCHER_KEY, "") or ""), HOOKS_KEY: list(item.get(HOOKS_KEY) or [])}
                else:
                    group = {HOOKS_KEY: [item]}
                hooks.setdefault(event, []).append(group)
    return {HOOKS_KEY: hooks} if hooks else {}
