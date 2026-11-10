"""What a pack declares besides rules and skills, and whether the security policy lets it run.

A profile of a pack can declare ``clis``, ``mcpServers`` and ``scripts``. This module validates
those declarations (a closed schema: no free fields, environment values only by reference) and
evaluates, for each one, the ``security`` policy of the layered configuration:

1. ``execution.enabled`` and, for a script, ``execution.events``;
2. the ``checks``: a trusted source, its signature and the sha256 of each artifact;
3. ``deny``, which always wins; then ``rules``, where a deny rule wins over an allow rule; then
   the ``allow`` lists, which restrict only when they are not empty.

An apply registers the MCP servers the policy allows (agent_ready_pack_mcp.py) and installs its
CLIs in the cache of the user (agent_ready_pack_clis.py); it does not run scripts yet. plan and
status report the verdict of every declared tool.
"""

import fnmatch
import os
import re
import urllib.parse

from agent_ready_common import is_link

TOOL_CLI = "cli"
TOOL_MCP_SERVER = "mcpServer"
TOOL_SCRIPT = "script"
DECLARATION_KEYS = ("clis", "mcpServers", "scripts")

EVENT_INSTALL = "install"
EVENT_POST_APPLY = "post-apply"
EVENT_SESSION_START = "session-start"
SCRIPT_EVENTS = (EVENT_INSTALL, EVENT_POST_APPLY, EVENT_SESSION_START)
SCRIPT_INTERPRETERS = ("bash", "python3", "node", "pwsh")
PLATFORMS = ("linux-x64", "linux-arm64", "darwin-x64", "darwin-arm64", "windows-x64", "windows-arm64")
PACKAGE_MANAGERS = ("npm", "pip", "brew", "winget")
MAX_SCRIPT_TIMEOUT_SECONDS = 3600
ARTIFACT_URL_SCHEME = "https"

CLI_KEYS = ("name", "version", "artifacts", "package")
ARTIFACT_KEYS = ("platform", "url", "sha256", "binary")
PACKAGE_KEYS = ("manager", "name", "binary", "sha256")
MCP_COMMAND_KEYS = ("command", "args", "env")
MCP_URL_KEYS = ("url", "headers")
SCRIPT_KEYS = ("event", "path", "interpreter", "timeoutSeconds")

TOOL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# An exact version: no ranges, tags like latest or spaces.
EXACT_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+)*(?:[-+][0-9A-Za-z.-]+)?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A bare executable name, resolved from the PATH; never a path or a shell line.
COMMAND_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
# Values only by reference, in a form both providers expand without a secret in their config:
# a variable passes under its own name (${ACME_TOKEN} for ACME_TOKEN), a header is ${VAR}, and
# only Authorization takes Bearer ${VAR}.
REFERENCE = re.compile(r"^\$\{(?P<name>[A-Z][A-Z0-9_]*)\}$")
BEARER_REFERENCE = re.compile(r"^Bearer \$\{(?P<name>[A-Z][A-Z0-9_]*)\}$")
HEADER_NAME = re.compile(r"^[A-Za-z0-9-]+$")
AUTHORIZATION_HEADER = "authorization"

APPLIED_TOOL_TYPES = (TOOL_CLI, TOOL_MCP_SERVER)
DECISION_ALLOWED = "allowed"
DECISION_BLOCKED = "blocked"
SOURCE_TYPE_PATH = "path"

EXECUTION_ENABLED_KEY = "security.execution.enabled"
EXECUTION_EVENTS_KEY = "security.execution.events"
CHECK_TRUSTED_SOURCE_KEY = "security.checks.trustedSource"
CHECK_SIGNATURE_KEY = "security.checks.signature"
CHECK_ARTIFACT_SHA256_KEY = "security.checks.artifactSha256"
CHECK_LOCK_DIGEST_KEY = "security.checks.lockDigest"
ALLOW_CLIS_KEY = "security.allow.clis"
ALLOW_COMMANDS_KEY = "security.allow.commands"
ALLOW_SCRIPTS_KEY = "security.allow.scripts"
ALLOW_MCP_SERVERS_KEY = "security.allow.mcpServers"
DENY_COMMANDS_KEY = "security.deny.commands"
DENY_SCRIPTS_KEY = "security.deny.scripts"
RULES_KEY = "security.rules"
TRUSTED_SOURCES_KEY = "security.trustedSources"
POLICY_KEYS = (EXECUTION_ENABLED_KEY, EXECUTION_EVENTS_KEY, CHECK_TRUSTED_SOURCE_KEY, CHECK_SIGNATURE_KEY,
               CHECK_ARTIFACT_SHA256_KEY, CHECK_LOCK_DIGEST_KEY, ALLOW_CLIS_KEY, ALLOW_COMMANDS_KEY,
               ALLOW_SCRIPTS_KEY, ALLOW_MCP_SERVERS_KEY, DENY_COMMANDS_KEY, DENY_SCRIPTS_KEY, RULES_KEY,
               TRUSTED_SOURCES_KEY)
RULE_ALLOW = "allow"
RULE_DENY = "deny"


class DeclarationError(ValueError):
    """A declaration of a pack profile that the schema does not accept."""


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------

def unknown_keys(entry, allowed):
    return sorted(set(entry) - set(allowed))


def require_object(value, what):
    if not isinstance(value, dict):
        raise DeclarationError(f"{what} must be an object")


def require_list(value, what):
    if not isinstance(value, list):
        raise DeclarationError(f"{what} must be a list")


def require_keys(entry, allowed, what):
    extra = unknown_keys(entry, allowed)
    if extra:
        raise DeclarationError(f"{what} has unknown keys: {', '.join(extra)}")


def validate_name(name, what):
    if not isinstance(name, str) or not TOOL_NAME.fullmatch(name):
        raise DeclarationError(f"{what} needs a kebab-case name")


def validate_artifact(artifact, what):
    require_object(artifact, what)
    require_keys(artifact, ARTIFACT_KEYS, what)
    if artifact.get("platform") not in PLATFORMS:
        raise DeclarationError(f"{what} needs a platform: one of {', '.join(PLATFORMS)}")
    url = artifact.get("url")
    parsed = urllib.parse.urlsplit(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme != ARTIFACT_URL_SCHEME or not parsed.netloc or parsed.username or parsed.password:
        raise DeclarationError(f"{what} needs an https url without credentials")
    if not isinstance(artifact.get("sha256"), str) or not SHA256.fullmatch(artifact["sha256"]):
        raise DeclarationError(f"{what} needs the sha256 of the file, 64 lowercase hex characters")
    if "binary" in artifact and (not isinstance(artifact["binary"], str) or not COMMAND_NAME.fullmatch(artifact["binary"])):
        raise DeclarationError(f"{what}: binary is the name of the executable inside the artifact")


def validate_cli(cli, what):
    require_object(cli, what)
    require_keys(cli, CLI_KEYS, what)
    validate_name(cli.get("name"), what)
    what = f"cli '{cli['name']}'"
    if not isinstance(cli.get("version"), str) or not EXACT_VERSION.fullmatch(cli["version"]):
        raise DeclarationError(f"{what} needs an exact version, such as 1.4.2; ranges and tags are not reproducible")
    if ("artifacts" in cli) == ("package" in cli):
        raise DeclarationError(f"{what} declares either artifacts (a file per platform) or a package")
    if "artifacts" in cli:
        require_list(cli["artifacts"], f"{what} artifacts")
        if not cli["artifacts"]:
            raise DeclarationError(f"{what} needs at least one artifact")
        platforms = []
        for index, artifact in enumerate(cli["artifacts"]):
            validate_artifact(artifact, f"{what} artifact {index + 1}")
            platforms.append(artifact["platform"])
        if len(platforms) != len(set(platforms)):
            raise DeclarationError(f"{what} declares the same platform twice")
        return
    package = cli["package"]
    require_object(package, f"{what} package")
    require_keys(package, PACKAGE_KEYS, f"{what} package")
    if package.get("manager") not in PACKAGE_MANAGERS:
        raise DeclarationError(f"{what} package needs a manager: one of {', '.join(PACKAGE_MANAGERS)}")
    if not isinstance(package.get("name"), str) or not package["name"].strip():
        raise DeclarationError(f"{what} package needs the name of the package")
    if "sha256" in package and (not isinstance(package["sha256"], str) or not SHA256.fullmatch(package["sha256"])):
        raise DeclarationError(f"{what} package sha256 must be 64 lowercase hex characters")
    if "binary" in package and (not isinstance(package["binary"], str) or not COMMAND_NAME.fullmatch(package["binary"])):
        raise DeclarationError(f"{what} package: binary is the name of the executable it installs")


def referenced_variable(value, header=None):
    """The variable a declared value references, or None when it is not a reference both providers expand."""
    if not isinstance(value, str):
        return None
    match = REFERENCE.fullmatch(value)
    if not match and header is not None and header.lower() == AUTHORIZATION_HEADER:
        match = BEARER_REFERENCE.fullmatch(value)
    return match.group("name") if match else None


def validate_environment(values, what):
    require_object(values, what)
    for name, value in values.items():
        if not ENVIRONMENT_NAME.fullmatch(name):
            raise DeclarationError(f"{what} has an invalid variable name '{name}'")
        if referenced_variable(value) != name:
            raise DeclarationError(f"{what} {name} must be the reference ${{{name}}}: the variable passes under its own "
                                   "name, never as a value")


def validate_headers(values, what):
    require_object(values, what)
    for name, value in values.items():
        if not HEADER_NAME.fullmatch(name):
            raise DeclarationError(f"{what} has an invalid header name '{name}'")
        if referenced_variable(value, header=name) is None:
            raise DeclarationError(f"{what} {name} must be a reference such as ${{ACME_TOKEN}} (or Bearer ${{ACME_TOKEN}} "
                                   "for Authorization), never a value")


def validate_mcp_server(name, server, what):
    validate_name(name, what)
    what = f"mcpServer '{name}'"
    require_object(server, what)
    if ("command" in server) == ("url" in server):
        raise DeclarationError(f"{what} declares either a command or a url")
    if "command" in server:
        require_keys(server, MCP_COMMAND_KEYS, what)
        if not isinstance(server["command"], str) or not COMMAND_NAME.fullmatch(server["command"]):
            raise DeclarationError(f"{what} command is the name of an executable, without a path or arguments")
        arguments = server.get("args", [])
        require_list(arguments, f"{what} args")
        if any(not isinstance(argument, str) for argument in arguments):
            raise DeclarationError(f"{what} args must be strings")
        validate_environment(server.get("env", {}), f"{what} env")
        return
    require_keys(server, MCP_URL_KEYS, what)
    parsed = urllib.parse.urlsplit(server["url"]) if isinstance(server["url"], str) else None
    if not parsed or parsed.scheme != ARTIFACT_URL_SCHEME or not parsed.netloc or parsed.username or parsed.password:
        raise DeclarationError(f"{what} needs an https url without credentials")
    validate_headers(server.get("headers", {}), f"{what} headers")


def validate_script(script, what, pack_root, is_contained):
    require_object(script, what)
    require_keys(script, SCRIPT_KEYS, what)
    if script.get("event") not in SCRIPT_EVENTS:
        raise DeclarationError(f"{what} needs an event: one of {', '.join(SCRIPT_EVENTS)}")
    if script.get("interpreter") not in SCRIPT_INTERPRETERS:
        raise DeclarationError(f"{what} needs an interpreter: one of {', '.join(SCRIPT_INTERPRETERS)}")
    timeout = script.get("timeoutSeconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= MAX_SCRIPT_TIMEOUT_SECONDS:
        raise DeclarationError(f"{what} needs timeoutSeconds between 1 and {MAX_SCRIPT_TIMEOUT_SECONDS}")
    path = script.get("path")
    if not isinstance(path, str) or not is_contained(path):
        raise DeclarationError(f"{what} path must be a file inside the pack")
    absolute = os.path.join(pack_root, *path.split("/"))
    current = pack_root
    for part in path.split("/"):
        current = os.path.join(current, part)
        if is_link(current):
            raise DeclarationError(f"{what} path {path} goes through a symlink or a junction, which packs cannot use")
    if not os.path.isfile(absolute):
        raise DeclarationError(f"{what} path {path} is missing from the pack")
    real_pack = os.path.normcase(os.path.realpath(pack_root))
    real_script = os.path.normcase(os.path.realpath(absolute))
    try:
        inside = os.path.commonpath([real_pack, real_script]) == real_pack
    except ValueError:
        inside = False
    if not inside:
        raise DeclarationError(f"{what} path {path} resolves outside the pack")


def validate_declarations(entry, pack_root, is_contained):
    """The clis, mcpServers and scripts of one pack profile; raises DeclarationError."""
    clis = entry.get("clis", [])
    require_list(clis, "clis")
    names = []
    for index, cli in enumerate(clis):
        validate_cli(cli, f"cli {index + 1}")
        names.append(cli["name"])
    if len(names) != len(set(names)):
        raise DeclarationError("clis declares the same name twice")
    servers = entry.get("mcpServers", {})
    require_object(servers, "mcpServers")
    for name, server in sorted(servers.items()):
        validate_mcp_server(name, server, f"mcpServer '{name}'")
    scripts = entry.get("scripts", [])
    require_list(scripts, "scripts")
    for index, script in enumerate(scripts):
        validate_script(script, f"script {index + 1}", pack_root, is_contained)


def declared_tools(catalog, resolved, source_of_profile, is_pack_profile):
    """Every tool the selected pack profiles declare, in a stable order."""
    tools = []
    for profile in resolved:
        if not is_pack_profile(profile):
            continue
        entry = catalog["profiles"].get(profile, {})
        source_name = source_of_profile(profile)
        common = {"source": source_name, "profile": profile}
        for cli in entry.get("clis", []):
            package = cli.get("package")
            # The whole declaration: an apply installs from it.
            tools.append(dict(common, type=TOOL_CLI, name=cli["name"], version=cli["version"],
                              package=package["manager"] if package else None,
                              sha256=bool(package.get("sha256")) if package else True, cli=cli))
        for name, server in sorted(entry.get("mcpServers", {}).items()):
            # The whole declaration: an apply registers it as it is, references and all.
            tools.append(dict(common, type=TOOL_MCP_SERVER, name=name, command=server.get("command"),
                              url=server.get("url"), server=server))
        for script in entry.get("scripts", []):
            tools.append(dict(common, type=TOOL_SCRIPT, name=f"{source_name}/{script['path']}", event=script["event"],
                              interpreter=script["interpreter"], path=script["path"]))
    return tools


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

def normalized_origin(origin):
    """Comparable form of a source origin: case-insensitive scheme and host, without a trailing .git or /."""
    text = origin.strip()
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme and parsed.netloc:
        text = urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", ""))
    text = text.rstrip("/")
    return text[:-len(".git")] if text.endswith(".git") else text


def source_is_trusted(source, policy, project_approved):
    """A Git source is trusted by its origin; a path source lives in the repository, so its approval."""
    if source.get("type") == SOURCE_TYPE_PATH:
        return project_approved
    trusted = {normalized_origin(origin) for origin in policy[TRUSTED_SOURCES_KEY]}
    return bool(source.get("origin")) and normalized_origin(source["origin"]) in trusted


def matches(patterns, value):
    return next((pattern for pattern in patterns if value and fnmatch.fnmatchcase(value, pattern)), None)


def script_text(tool):
    """The text of a script, to match a rule with contains; unreadable reads as empty."""
    if not tool.get("file"):
        return ""
    try:
        with open(tool["file"], encoding="utf-8", errors="replace") as script_file:
            return script_file.read()
    except OSError:
        return ""


def rule_matches(rule, tool):
    match = rule.get("match", {})
    if "type" in match and match["type"] != tool["type"]:
        return False
    for field, value in (("source", tool["source"]), ("profile", tool["profile"]), ("pattern", tool["name"])):
        if field in match and not fnmatch.fnmatchcase(value, match[field]):
            return False
    if "contains" in match:
        return tool["type"] == TOOL_SCRIPT and match["contains"] in script_text(tool)
    return True


def describe_rule(rule):
    match = rule.get("match", {})
    selector = ", ".join(f"{field} {value}" for field, value in sorted(match.items())) or "every tool"
    return f"{rule['action']} {selector}"


def deny_reason(tool, policy):
    if tool["type"] == TOOL_SCRIPT:
        pattern = matches(policy[DENY_SCRIPTS_KEY], tool["name"])
        return f"{DENY_SCRIPTS_KEY} matches {pattern}" if pattern else None
    command = tool["name"] if tool["type"] == TOOL_CLI else tool.get("command")
    pattern = matches(policy[DENY_COMMANDS_KEY], command)
    return f"{DENY_COMMANDS_KEY} matches {pattern}" if pattern else None


def allow_reason(tool, policy):
    """Why an allow list leaves this tool out, or None."""
    if tool["type"] == TOOL_CLI:
        checks = ((ALLOW_CLIS_KEY, tool["name"]),)
    elif tool["type"] == TOOL_MCP_SERVER:
        checks = ((ALLOW_MCP_SERVERS_KEY, tool["name"]),) + (((ALLOW_COMMANDS_KEY, tool["command"]),) if tool.get("command") else ())
    else:
        checks = ((ALLOW_SCRIPTS_KEY, tool["name"]),)
    for key, value in checks:
        if policy[key] and not matches(policy[key], value):
            return f"{key} does not include {value}"
    return None


def evaluate(tool, policy, source, project_approved, signature_verified=False):
    """(decision, reason) of one declared tool under the effective policy."""
    if not policy[EXECUTION_ENABLED_KEY]:
        return DECISION_BLOCKED, f"{EXECUTION_ENABLED_KEY} is false"
    if tool["type"] == TOOL_SCRIPT and tool["event"] not in policy[EXECUTION_EVENTS_KEY]:
        return DECISION_BLOCKED, f"{EXECUTION_EVENTS_KEY} does not include {tool['event']}"
    if policy[CHECK_TRUSTED_SOURCE_KEY] and not source_is_trusted(source, policy, project_approved):
        if source.get("type") == SOURCE_TYPE_PATH:
            return DECISION_BLOCKED, ("the source lives in this repository, which this machine has not approved; "
                                      "approve it with agent-ready trust add --project")
        return DECISION_BLOCKED, (f"the source {tool['source']} is not trusted on this machine; "
                                  f"trust it with agent-ready trust add {tool['source']}")
    if policy[CHECK_SIGNATURE_KEY] and not signature_verified:
        return DECISION_BLOCKED, f"{CHECK_SIGNATURE_KEY}: the signature of {tool['source']} is not verified"
    if tool["type"] == TOOL_CLI and policy[CHECK_ARTIFACT_SHA256_KEY] and not tool["sha256"]:
        return DECISION_BLOCKED, (f"{CHECK_ARTIFACT_SHA256_KEY}: the {tool['package']} package of {tool['name']} "
                                  "declares no sha256")
    denied = deny_reason(tool, policy)
    if denied:
        return DECISION_BLOCKED, denied
    matching = [rule for rule in policy[RULES_KEY] if rule_matches(rule, tool)]
    deny_rule = next((rule for rule in matching if rule["action"] == RULE_DENY), None)
    if deny_rule:
        return DECISION_BLOCKED, f"{RULES_KEY}: {describe_rule(deny_rule)}"
    if any(rule["action"] == RULE_ALLOW for rule in matching):
        return DECISION_ALLOWED, None
    left_out = allow_reason(tool, policy)
    if left_out:
        return DECISION_BLOCKED, left_out
    return DECISION_ALLOWED, None


def report(tools, catalog, configuration):
    """The policy with the layer of each value and the verdict of every declared tool, or None without tools."""
    if not tools:
        return None
    policy = {key: configuration.value(key) for key in POLICY_KEYS}
    evaluated = []
    for tool in tools:
        source = catalog.get("sources", {}).get(tool["source"], {})
        checked = dict(tool)
        if tool["type"] == TOOL_SCRIPT and source.get("root"):
            # Only to read the text a rule may match; the report keeps the path inside the pack.
            checked["file"] = os.path.join(source["root"], *tool["path"].split("/"))
        decision, reason = evaluate(checked, policy, source, configuration.project_approved)
        evaluated.append(dict(tool, decision=decision, reason=reason))
    return {
        # What an apply does with an allowed tool today: scripts come in a later version.
        "applies": list(APPLIED_TOOL_TYPES),
        "policy": {key: {"value": policy[key], "origin": configuration.origin(key)} for key in POLICY_KEYS},
        "tools": evaluated,
    }


def describe_tool(tool):
    if tool["type"] == TOOL_CLI:
        origin = f"{tool['package']} package" if tool.get("package") else "artifacts"
        return f"cli {tool['name']} {tool['version']} ({origin})"
    if tool["type"] == TOOL_MCP_SERVER:
        return f"mcpServer {tool['name']} ({tool['command'] or tool['url']})"
    return f"script {tool['name']} on {tool['event']} ({tool['interpreter']})"
