#!/usr/bin/env python3
"""Merge the Codex hooks template into the project hooks without losing custom hooks."""

import json
import sys
from pathlib import Path


def merge_configuration(current, incoming, managed_commands):
    """Merge objects and distinct list entries; current scalar metadata wins."""
    if isinstance(current, dict) and isinstance(incoming, dict):
        merged = dict(current)
        for key, value in incoming.items():
            merged[key] = merge_configuration(merged[key], value, managed_commands) if key in merged else value
        return merged
    if isinstance(current, list) and isinstance(incoming, list):
        merged = list(current)
        for entry in incoming:
            if entry in merged:
                continue
            # Matcher groups with identical options share their handler list.
            matching_index = next((index for index, existing in enumerate(merged)
                                   if isinstance(entry, dict) and isinstance(existing, dict)
                                   and ((isinstance(entry.get("hooks"), list)
                                         and isinstance(existing.get("hooks"), list)
                                         and {key: value for key, value in existing.items() if key != "hooks"}
                                         == {key: value for key, value in entry.items() if key != "hooks"})
                                        or (entry.get("type") == "command"
                                            and entry.get("command") in managed_commands
                                            and existing.get("type") == "command"
                                            and entry.get("command") == existing.get("command")))), None)
            if matching_index is None:
                merged.append(entry)
            else:
                merged[matching_index] = merge_configuration(merged[matching_index], entry, managed_commands)
        return merged
    return current


def refresh_managed_handlers(configuration, template):
    """Refresh known managed commands while keeping handler options and custom groups."""
    for event, groups in configuration.get("hooks", {}).items():
        template_groups = template.get("hooks", {}).get(event, [])
        managed_handlers = {handler.get("command"): handler
                            for group in template_groups for handler in group.get("hooks", [])
                            if handler.get("type") == "command"}
        for group in groups:
            for handler in group.get("hooks", []):
                managed = managed_handlers.get(handler.get("command"))
                if handler.get("type") == "command" and managed is not None:
                    handler.update(managed)
    return configuration


def read_configuration(path):
    """Read a hook object, treating missing sources as empty configurations."""
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8") as source:
        configuration = json.load(source)
    if not isinstance(configuration, dict):
        raise ValueError("hook configuration must be an object")
    hooks = configuration.get("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    for groups in hooks.values():
        if not isinstance(groups, list) or any(not isinstance(group, dict) for group in groups):
            raise ValueError("hook matcher groups must be objects in an array")
        for group in groups:
            handlers = group.get("hooks", [])
            if not isinstance(handlers, list) or any(not isinstance(handler, dict) for handler in handlers):
                raise ValueError("hook handlers must be objects in an array")
    return configuration


def main():
    """Print merged configuration; the caller persists it after checking the source is unchanged."""
    # Windows stdout defaults to CRLF and the locale code page; the generated JSON is LF UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    try:
        template, destination = (read_configuration(path) for path in sys.argv[1:])
        managed_commands = {handler.get("command")
                            for groups in template.get("hooks", {}).values()
                            for group in groups for handler in group.get("hooks", [])
                            if handler.get("type") == "command"}
        merged = merge_configuration(refresh_managed_handlers(destination, template), template, managed_commands)
    except (OSError, ValueError, TypeError) as error:
        print(f"Codex hook merge failed: {error}", file=sys.stderr)
        return 1
    if merged == template:
        sys.stdout.write(Path(sys.argv[1]).read_text(encoding="utf-8"))
        return 0
    json.dump(merged, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
