"""What the user's machine already has that a selection collides with: skills, subagents and commands
of the same name, and MCP servers the user registered for every project.

Read-only: it reads the user's provider configuration (``~/.claude``, ``~/.claude.json``,
``~/.agents/skills``, ``$CODEX_HOME/config.toml``) and never writes it. Paths in the findings are
written from ``~`` so no path of this machine ends up in a report.

Precedence, from the provider documentation:

* Claude Code, skills (commands are skills too): a personal skill in ``~/.claude/skills`` wins over a
  project skill of the same name. Plugin skills are namespaced (``/plugin:skill``), so both load.
* Claude Code, subagents: project wins over user, and user over plugin.
* Codex, skills: repository ``.agents/skills`` and ``~/.agents/skills`` are not merged; both appear
  in the selector and no order is documented.
"""

import json
import os
import re

import agent_ready_pack_mcp as pack_mcp

try:
    import tomllib
except ImportError:  # Python before 3.11 cannot read config.toml: the Codex comparison is skipped.
    tomllib = None

KIND_SKILL = "skill"
KIND_AGENT = "agent"
KIND_COMMAND = "command"
PROVIDER_CLAUDE = "claude"
PROVIDER_CODEX = "codex"
CLAUDE_USER_SERVERS_FILE = ".claude.json"
CODEX_CONFIG_FILE = "config.toml"
INSTALLED_PLUGINS_RELATIVE_PATH = os.path.join("plugins", "installed_plugins.json")
PLUGIN_SCOPE_USER = "user"
PLUGIN_SCOPE_PROJECT = "project"
# Where each kind lives in the user's Claude Code directory and inside a plugin.
CLAUDE_KIND_DIRECTORIES = {KIND_SKILL: "skills", KIND_AGENT: "agents", KIND_COMMAND: "commands"}
# What each provider does with a project asset and a user one of the same name.
CLAUDE_USER_WINS = "Claude Code uses the user's"
CLAUDE_PROJECT_WINS = "Claude Code uses the project's"
CLAUDE_BOTH_NAMESPACED = "Claude Code loads both (the plugin's as {plugin}:{name})"
CLAUDE_PROJECT_OVER_PLUGIN = "Claude Code uses the project's over the plugin's"
CODEX_BOTH_LISTED = "Codex lists both, with no documented order"
# Claude Code merged commands into skills: a skill and a command share one slash-command name space,
# so either collides with a personal skill or command of the same name. Subagents are separate.
CLAUDE_SHARED_NAMESPACE = {KIND_SKILL: (KIND_SKILL, KIND_COMMAND), KIND_COMMAND: (KIND_SKILL, KIND_COMMAND)}
# An npm package in the arguments of a server: its identity, whatever version it pins.
PACKAGE_ARGUMENT = re.compile(r"^(?P<name>(@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*)(@[^/\s]+)?$")
CODEX_ENV_VARS_KEY = "env_vars"
# Keys of a server entry that say where it runs or how the provider treats it, not what it does.
IDENTITY_IGNORED_KEYS = {"command", "args", "url", "type", "enabled", "startup_timeout_sec", "tool_timeout_sec"}
PACKAGE_RUNNERS = ("npx", "pnpm", "bunx", "uvx", "pipx", "dlx", "exec", "-y", "--yes")


def user_home():
    """HOME when it is set, like the rest of the engine (Python ignores it on Windows), else ~."""
    return os.environ.get("HOME") or os.path.expanduser("~")


def home_display(path):
    """The path from ~ when it is under the home directory, as reports write it."""
    home = user_home()
    try:
        relative = os.path.relpath(path, home)
    except ValueError:
        return path
    if relative.startswith(".."):
        return path
    return "~/" + relative.replace(os.sep, "/")


def claude_home():
    """The user's Claude Code directory: CLAUDE_CONFIG_DIR, or ~/.claude."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(user_home(), ".claude")


def claude_user_servers_path():
    """~/.claude.json, or .claude.json inside CLAUDE_CONFIG_DIR when it is set."""
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return os.path.join(os.environ["CLAUDE_CONFIG_DIR"], CLAUDE_USER_SERVERS_FILE)
    return os.path.join(user_home(), CLAUDE_USER_SERVERS_FILE)


def codex_home():
    """The user's Codex directory: CODEX_HOME, or ~/.codex."""
    return os.environ.get("CODEX_HOME") or os.path.join(user_home(), ".codex")


def read_json(path):
    """The JSON of a regular file, or None when it is missing, a symlink or not valid JSON."""
    if not os.path.isfile(path) or os.path.islink(path):
        return None
    try:
        with open(path, encoding="utf-8") as json_file:
            return json.load(json_file)
    except (OSError, ValueError):
        return None


def names_in(directory, kind):
    """{name: path} of the skills (folders with SKILL.md) or the .md files of a directory."""
    found = {}
    if not os.path.isdir(directory):
        return found
    for entry in sorted(os.listdir(directory)):
        path = os.path.join(directory, entry)
        if kind == KIND_SKILL:
            if os.path.isfile(os.path.join(path, "SKILL.md")):
                found[entry] = path
        elif entry.endswith(".md") and os.path.isfile(path):
            found[entry[:-len(".md")]] = path
    return found


def installed_plugins(project_root):
    """[(plugin name, install path)] of the Claude Code plugins enabled for this project."""
    data = read_json(os.path.join(claude_home(), INSTALLED_PLUGINS_RELATIVE_PATH))
    plugins = []
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), dict):
        return plugins
    project = os.path.normcase(os.path.realpath(project_root))
    for key, installs in sorted(data["plugins"].items()):
        for install in installs if isinstance(installs, list) else []:
            if not isinstance(install, dict) or not install.get("installPath"):
                continue
            scope = install.get("scope")
            project_path = install.get("projectPath")
            if scope == PLUGIN_SCOPE_USER or (scope == PLUGIN_SCOPE_PROJECT and project_path
                                              and os.path.normcase(os.path.realpath(project_path)) == project):
                plugins.append((key.split("@", 1)[0], install["installPath"]))
    return plugins


def project_assets(destinations):
    """{(kind, name): destination} of the skills, subagents and commands a selection projects."""
    assets = {}
    for destination in sorted(destinations):
        parts = destination.split("/")
        if len(parts) == 4 and parts[:2] == [".agents", "skills"] and parts[3] == "SKILL.md":
            assets.setdefault((KIND_SKILL, parts[2]), destination)
        elif len(parts) == 3 and parts[0] == ".agents" and parts[1] in ("agents", "commands") and parts[2].endswith(".md"):
            kind = KIND_AGENT if parts[1] == "agents" else KIND_COMMAND
            assets[(kind, parts[2][:-len(".md")])] = destination
    return assets


def shadowed_assets(project_root, entries):
    """One finding per managed skill, subagent or command with the same name as one on the machine.

    ``entries`` are the plan entries the apply writes (destination and profile).
    """
    profiles = {entry["destination"]: entry["profile"] for entry in entries if entry.get("sha256")}
    assets = project_assets(profiles)
    # A subagent or a command reaches Codex as a skill adapter of the same name, so the skill entry
    # of that name is the same asset and is not reported twice.
    adapters = {name for kind, name in assets if kind != KIND_SKILL}
    user_claude = {kind: names_in(os.path.join(claude_home(), directory), kind)
                   for kind, directory in CLAUDE_KIND_DIRECTORIES.items()}
    user_codex_skills = names_in(os.path.join(user_home(), ".agents", "skills"), KIND_SKILL)
    plugins = [(plugin, {kind: names_in(os.path.join(path, directory), kind)
                         for kind, directory in CLAUDE_KIND_DIRECTORIES.items()})
               for plugin, path in installed_plugins(project_root)]
    findings = []
    for (kind, name), destination in sorted(assets.items()):
        if kind == KIND_SKILL and name in adapters:
            continue
        profile = profiles[destination]
        for machine_kind in CLAUDE_SHARED_NAMESPACE.get(kind, (kind,)):
            if name in user_claude[machine_kind]:
                findings.append({"kind": kind, "name": name, "profile": profile, "provider": PROVIDER_CLAUDE,
                                 "machine": home_display(user_claude[machine_kind][name]),
                                 "winner": CLAUDE_PROJECT_WINS if kind == KIND_AGENT else CLAUDE_USER_WINS})
            for plugin, plugin_names in plugins:
                if name in plugin_names[machine_kind]:
                    findings.append({"kind": kind, "name": name, "profile": profile, "provider": PROVIDER_CLAUDE,
                                     "machine": home_display(plugin_names[machine_kind][name]),
                                     "winner": CLAUDE_PROJECT_OVER_PLUGIN if kind == KIND_AGENT
                                     else CLAUDE_BOTH_NAMESPACED.format(plugin=plugin, name=name)})
        if name in user_codex_skills:
            findings.append({"kind": kind, "name": name, "profile": profile, "provider": PROVIDER_CODEX,
                             "machine": home_display(user_codex_skills[name]), "winner": CODEX_BOTH_LISTED})
    return findings


def server_identity(server):
    """What makes two MCP servers the same, whatever their name.

    The endpoint (the URL, the package a runner starts with the arguments that configure it, or the
    command with its full path and arguments) plus the rest of its configuration (env, headers,
    credentials). Only a pinned package version and the provider's own switches are ignored, so a
    server counts as the user's only when it would do exactly the same: anything else registers both.
    """
    if not isinstance(server, dict):
        return None
    if server.get("url"):
        endpoint = ["url", str(server["url"]).rstrip("/")]
    elif server.get("command"):
        command = str(server["command"])
        arguments = [str(argument) for argument in server.get("args") or []]
        endpoint = ["command", command] + arguments
        if os.path.basename(command).split(".")[0] in PACKAGE_RUNNERS:
            for position, argument in enumerate(arguments):
                if argument in PACKAGE_RUNNERS or argument.startswith("-"):
                    continue
                match = PACKAGE_ARGUMENT.match(argument)
                if match:
                    endpoint = ["package", match.group("name")] + arguments[position + 1:]
                break
    else:
        return None
    configuration = {key: value for key, value in server.items() if key not in IDENTITY_IGNORED_KEYS}
    # Codex lists the variables it passes; their order does not change the server.
    if isinstance(configuration.get(CODEX_ENV_VARS_KEY), list):
        configuration[CODEX_ENV_VARS_KEY] = sorted(str(name) for name in configuration[CODEX_ENV_VARS_KEY])
    # A structured value keeps every argument whole: "a b" is not "a" and "b".
    return json.dumps([endpoint, configuration], sort_keys=True, ensure_ascii=False)


def user_servers():
    """{provider: {name: server}} the user registered for every project; a provider whose
    configuration cannot be read is left out."""
    servers = {}
    claude = read_json(claude_user_servers_path())
    if isinstance(claude, dict) and isinstance(claude.get("mcpServers"), dict):
        servers[PROVIDER_CLAUDE] = {name: entry for name, entry in claude["mcpServers"].items() if isinstance(entry, dict)}
    codex_path = os.path.join(codex_home(), CODEX_CONFIG_FILE)
    if tomllib is not None and os.path.isfile(codex_path) and not os.path.islink(codex_path):
        try:
            with open(codex_path, "rb") as config_file:
                codex = tomllib.load(config_file)
        except (OSError, ValueError):
            codex = None
        if isinstance(codex, dict) and isinstance(codex.get("mcp_servers"), dict):
            # A server the user turned off (enabled = false) does not stand in for the project's.
            servers[PROVIDER_CODEX] = {name: entry for name, entry in codex["mcp_servers"].items()
                                       if isinstance(entry, dict) and entry.get("enabled", True) is not False}
    return servers


def user_server_paths():
    """Where each provider keeps the servers of the user, from ~."""
    return {PROVIDER_CLAUDE: home_display(claude_user_servers_path()),
            PROVIDER_CODEX: home_display(os.path.join(codex_home(), CODEX_CONFIG_FILE))}


# How the apply writes a pack declaration for each provider (agent_ready_pack_mcp.py).
PROVIDER_ENTRIES = {PROVIDER_CLAUDE: pack_mcp.claude_entry, PROVIDER_CODEX: pack_mcp.codex_entry}


def duplicated_servers(desired, providers):
    """{provider: {name: user server name}} of the desired servers the user already has, by identity.

    ``desired`` is {name: {source, profile, server}} as agent_ready_pack_mcp.desired_servers returns it.
    """
    known = user_servers()
    duplicates = {}
    for provider in providers:
        if provider not in PROVIDER_ENTRIES:
            continue
        identities = {server_identity(entry): user_name for user_name, entry in known.get(provider, {}).items()}
        identities.pop(None, None)
        to_provider_entry = PROVIDER_ENTRIES[provider]
        for name, item in desired.items():
            # Compared as the apply would write it for that provider, the way the user's entry is written.
            user_name = identities.get(server_identity(to_provider_entry(item["server"])))
            if user_name:
                duplicates.setdefault(provider, {})[name] = user_name
    return duplicates
