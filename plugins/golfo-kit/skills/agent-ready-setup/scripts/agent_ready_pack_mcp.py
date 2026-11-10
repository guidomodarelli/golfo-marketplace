"""Registration of the MCP servers that profile packs declare, in the project configuration of each
provider: ``.mcp.json`` for Claude Code and ``.codex/config.toml`` for Codex.

Only an apply registers, and only a server the security policy allows (agent_ready_pack_tools.py).
Ownership follows the lock: a server whose name the lock records is managed, so it is replaced or
removed freely; any other server with that name belongs to the project and is never touched. In
Codex the managed servers live between two marker comments, so the project's own tables are never
rewritten.

No secret gets in: an environment variable passes under its own name and a header is a reference,
written the way each provider expands it (``${VAR}`` in Claude Code; ``env_vars``,
``bearer_token_env_var`` and ``env_http_headers`` in Codex).
"""

import hashlib
import json
import os
import re

from agent_ready_common import is_link, write_text_atomically

try:
    import tomllib
except ImportError:  # Python before 3.11: the conflicts are found in the text instead.
    tomllib = None

PROVIDER_CLAUDE = "claude"
PROVIDER_CODEX = "codex"
CLAUDE_CONFIG_RELATIVE_PATH = ".mcp.json"
CODEX_CONFIG_RELATIVE_PATH = ".codex/config.toml"
CLAUDE_SERVERS_KEY = "mcpServers"
CODEX_SERVERS_KEY = "mcp_servers"
CLAUDE_HTTP_TYPE = "http"
CODEX_BLOCK_START = "# BEGIN AGENT-READY PACK MCP SERVERS"
CODEX_BLOCK_END = "# END AGENT-READY PACK MCP SERVERS"
CODEX_BLOCK_NOTE = "# Managed by agent-ready-setup from the profile packs; change the pack, not these lines."
REFERENCE = re.compile(r"^\$\{(?P<name>[A-Z][A-Z0-9_]*)\}$")
BEARER_REFERENCE = re.compile(r"^Bearer \$\{(?P<name>[A-Z][A-Z0-9_]*)\}$")
AUTHORIZATION_HEADER = "authorization"


class RegistrationError(RuntimeError):
    """A provider configuration that cannot be read or edited safely; it stays as it was."""


def declaration_digest(server):
    return hashlib.sha256(json.dumps(server, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def desired_servers(report):
    """{name: {source, profile, server}} for each MCP server the policy allows, and the names two packs declare."""
    desired, duplicated = {}, []
    for tool in (report or {}).get("tools", []):
        if tool.get("type") != "mcpServer" or tool.get("decision") != "allowed":
            continue
        if tool["name"] in desired:
            duplicated.append(f"{tool['name']}: declared by {desired[tool['name']]['profile']} and {tool['profile']}; "
                              "only the first one is registered")
            continue
        desired[tool["name"]] = {"source": tool["source"], "profile": tool["profile"], "server": tool["server"]}
    return desired, duplicated


# ---------------------------------------------------------------------------
# Claude Code: .mcp.json
# ---------------------------------------------------------------------------

def claude_entry(server):
    """The .mcp.json entry; Claude Code expands ${VAR} in env and headers."""
    if "url" in server:
        entry = {"type": CLAUDE_HTTP_TYPE, "url": server["url"]}
        if server.get("headers"):
            entry["headers"] = dict(server["headers"])
        return entry
    entry = {"command": server["command"]}
    if server.get("args"):
        entry["args"] = list(server["args"])
    if server.get("env"):
        entry["env"] = dict(server["env"])
    return entry


def read_regular_file(path):
    """The text of a project configuration, or None when it does not exist; a symlink is never followed."""
    if os.path.lexists(path) and (is_link(path) or not os.path.isfile(path)):
        raise RegistrationError(f"{path} is a symlink or not a regular file, so its MCP servers were not changed")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as config_file:
        return config_file.read()


def sync_claude(project_root, desired, previous):
    """Write the managed servers into .mcp.json; returns (registered, removed, conflicts)."""
    path = os.path.join(project_root, CLAUDE_CONFIG_RELATIVE_PATH)
    original = read_regular_file(path)
    try:
        document = json.loads(original) if original and original.strip() else {}
    except ValueError as invalid:
        raise RegistrationError(f"{CLAUDE_CONFIG_RELATIVE_PATH} is not valid JSON, so its MCP servers were not changed") from invalid
    servers = document.get(CLAUDE_SERVERS_KEY, {})
    if not isinstance(document, dict) or not isinstance(servers, dict):
        raise RegistrationError(f"{CLAUDE_CONFIG_RELATIVE_PATH} has no object of {CLAUDE_SERVERS_KEY}, so it was not changed")
    registered, removed, conflicts = [], [], []
    for name in sorted(previous):
        if name not in desired and name in servers:
            del servers[name]
            removed.append(name)
    for name, item in sorted(desired.items()):
        if name in servers and name not in previous:
            conflicts.append(f"{name}: {CLAUDE_CONFIG_RELATIVE_PATH} already has a server with that name, which belongs "
                             "to the project; rename one of them")
            continue
        servers[name] = claude_entry(item["server"])
        registered.append(name)
    if servers:
        document[CLAUDE_SERVERS_KEY] = servers
    else:
        document.pop(CLAUDE_SERVERS_KEY, None)
    write_or_remove(path, original, json.dumps(document, indent=2, ensure_ascii=False) + "\n" if document else None)
    return registered, removed, conflicts


def write_or_remove(path, original, text):
    """Write ``text`` when it changed; None removes the file the managed servers alone kept."""
    if text is None:
        if original is not None:
            os.unlink(path)
        return
    if text != original:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text_atomically(path, text)


# ---------------------------------------------------------------------------
# Codex: .codex/config.toml
# ---------------------------------------------------------------------------

def toml_value(value):
    """A TOML literal: basic strings use the escapes JSON also writes."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(key, ensure_ascii=False)} = {toml_value(item)}" for key, item in value.items()) + " }"
    raise TypeError(f"no TOML form for {type(value).__name__}")


def codex_entry(server):
    """The [mcp_servers.<name>] fields; Codex reads the referenced variables from its environment."""
    if "url" in server:
        entry = {"url": server["url"]}
        environment_headers = {}
        for header, value in (server.get("headers") or {}).items():
            bearer = BEARER_REFERENCE.fullmatch(value) if header.lower() == AUTHORIZATION_HEADER else None
            if bearer:
                entry["bearer_token_env_var"] = bearer.group("name")
            else:
                environment_headers[header] = REFERENCE.fullmatch(value).group("name")
        if environment_headers:
            entry["env_http_headers"] = environment_headers
        return entry
    entry = {"command": server["command"]}
    if server.get("args"):
        entry["args"] = list(server["args"])
    if server.get("env"):
        entry["env_vars"] = sorted(server["env"])
    return entry


def without_block(text):
    """The configuration without the managed block, and whether it had one."""
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip("\r\n") == CODEX_BLOCK_START]
    ends = [index for index, line in enumerate(lines) if line.rstrip("\r\n") == CODEX_BLOCK_END]
    if not starts and not ends:
        return text, False
    if len(starts) != 1 or len(ends) != 1 or starts[0] > ends[0]:
        raise RegistrationError(f"{CODEX_CONFIG_RELATIVE_PATH} has broken {CODEX_BLOCK_START} markers, so it was not changed")
    remaining = lines[:starts[0]] + lines[ends[0] + 1:]
    return "".join(remaining).rstrip("\n") + ("\n" if "".join(remaining).strip() else ""), True


def project_codex_servers(text):
    """Names of the servers the project defines itself, outside the managed block."""
    if tomllib is not None:
        try:
            document = tomllib.loads(text)
        except tomllib.TOMLDecodeError as invalid:
            raise RegistrationError(f"{CODEX_CONFIG_RELATIVE_PATH} is not valid TOML, so its MCP servers were not changed") from invalid
        servers = document.get(CODEX_SERVERS_KEY, {})
        return set(servers) if isinstance(servers, dict) else set()
    names = set(re.findall(r'^\s*\[\s*mcp_servers\.(?:"([^"]+)"|([A-Za-z0-9_-]+))\s*\]', text, re.M))
    return {quoted or bare for quoted, bare in names}


def codex_block(desired):
    lines = [CODEX_BLOCK_START, CODEX_BLOCK_NOTE]
    for name, item in sorted(desired.items()):
        lines += ["", f"[{CODEX_SERVERS_KEY}.{name}]"]
        lines += [f"{field} = {toml_value(value)}" for field, value in codex_entry(item["server"]).items()]
    return "\n".join(lines + [CODEX_BLOCK_END]) + "\n"


def sync_codex(project_root, desired, previous):
    """Rewrite the managed block of .codex/config.toml; returns (registered, removed, conflicts)."""
    path = os.path.join(project_root, CODEX_CONFIG_RELATIVE_PATH)
    original = read_regular_file(path)
    rest, _ = without_block(original or "")
    if rest.strip() and re.search(r"^\s*mcp_servers\s*=", rest, re.M):
        raise RegistrationError(f"{CODEX_CONFIG_RELATIVE_PATH} declares mcp_servers inline, so the pack servers were not added")
    own = project_codex_servers(rest)
    conflicts = [f"{name}: {CODEX_CONFIG_RELATIVE_PATH} already has a server with that name, which belongs to the project; "
                 "rename one of them" for name in sorted(desired) if name in own]
    registered = {name: item for name, item in desired.items() if name not in own}
    removed = sorted(name for name in previous if name not in desired)
    block = codex_block(registered) if registered else ""
    text = (rest + ("\n" if rest.strip() and block else "") + block) if (rest.strip() or block) else None
    if text is not None and tomllib is not None:
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as invalid:
            raise RegistrationError(f"the pack servers would leave {CODEX_CONFIG_RELATIVE_PATH} invalid, so it was not changed") from invalid
    write_or_remove(path, original, text)
    return sorted(registered), removed, conflicts


# ---------------------------------------------------------------------------
# Apply and remove
# ---------------------------------------------------------------------------

PROVIDER_SYNC = {PROVIDER_CLAUDE: sync_claude, PROVIDER_CODEX: sync_codex}
PROVIDER_FILES = {PROVIDER_CLAUDE: CLAUDE_CONFIG_RELATIVE_PATH, PROVIDER_CODEX: CODEX_CONFIG_RELATIVE_PATH}


def register(project_root, report, previous, providers):
    """Register the allowed servers and drop the managed ones that are no longer allowed or selected.

    ``previous`` is the mcpServers of the lock. Returns what changed and the entries the new lock records.
    """
    desired, duplicated = desired_servers(report)
    result = {"registered": {}, "removed": {}, "conflicts": list(duplicated), "failed": [], "lock": {}}
    for provider in providers:
        if provider not in PROVIDER_SYNC:
            continue
        before = {name for name, entry in previous.items() if provider in entry.get("providers", [])}
        if not desired and not before:
            # Nothing of the packs to add or remove: the configuration of the provider is not even read.
            continue
        try:
            registered, removed, conflicts = PROVIDER_SYNC[provider](project_root, desired, before)
        except (RegistrationError, OSError) as problem:
            result["failed"].append(str(problem))
            # Nothing changed for this provider: what the lock had stays recorded.
            for name in before:
                result["lock"].setdefault(name, dict(previous[name], providers=[]))["providers"].append(provider)
            continue
        result["registered"][PROVIDER_FILES[provider]] = registered
        result["removed"][PROVIDER_FILES[provider]] = removed
        result["conflicts"] += conflicts
        for name in registered:
            item = desired[name]
            entry = result["lock"].setdefault(name, {"source": item["source"], "profile": item["profile"],
                                                     "sha256": declaration_digest(item["server"]), "providers": []})
            entry["providers"].append(provider)
    for entry in result["lock"].values():
        entry["providers"] = sorted(set(entry["providers"]))
    return result


def unregister_all(project_root, previous):
    """Drop every managed server of the lock, as agent-ready remove does; the project's own stay."""
    return register(project_root, None, previous, sorted(PROVIDER_SYNC))


def managed_files(project_root, previous):
    """The provider configurations that hold managed servers of the lock."""
    files = []
    for provider, relative in PROVIDER_FILES.items():
        if any(provider in entry.get("providers", []) for entry in previous.values()):
            if os.path.isfile(os.path.join(project_root, relative)):
                files.append(relative)
    return files
