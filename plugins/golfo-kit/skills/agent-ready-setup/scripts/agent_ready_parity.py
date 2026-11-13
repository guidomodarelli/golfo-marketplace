"""Three read-only checks across what the selection hands each provider and what the repository has:

* provider parity: what Claude Code and Codex see, and the hooks that reach one and not the other;
* environment variables: the same variable asked by two sources, or one the project already lists in
  its example environment file;
* CI: a job of the repository that already runs the Agent Ready check the managed CI adds.
"""

import glob
import os
import re

import agent_ready_pack_tools as pack_tools
import agent_ready_settings_conflicts as settings_conflicts

PROVIDER_CLAUDE = "claude"
PROVIDER_CODEX = "codex"
# Hook events of the golfo-kit templates that only one provider has, on purpose, and why.
PROVIDER_SPECIFIC_HOOK_EVENTS = {
    (PROVIDER_CLAUDE, "UserPromptSubmit"): "relinks the hard-link views of .claude, which Codex does not read",
}
EXAMPLE_ENVIRONMENT_FILES = (".env.example", ".env.sample", ".env.template", ".env.dist")
ENVIRONMENT_LINE = re.compile(r"^\s*(?:export\s+)?(?P<name>[A-Z][A-Z0-9_]*)\s*=")
# What a CI job runs when it already does the Agent Ready check.
AGENT_READY_CHECK_PATTERN = re.compile(
    r"agent-ready-check\.sh|agent-ready(?:\.py)?\s+check\b|agent-ready-state\.py\s+check\b|bootstrap\.sh\b.*--check\b")
REPOSITORY_CI_FILES = (".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml", "Jenkinsfile",
                       ".circleci/config.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml")
RULES_PREFIX = ".agents/rules/"
SKILLS_PREFIX = ".agents/skills/"
AGENTS_PREFIX = ".agents/agents/"
COMMANDS_PREFIX = ".agents/commands/"


def provider_views(rule_count, scoped_rule_count, entries):
    """What each provider sees of the selection: rules, skills, subagents and commands.

    ``rule_count`` counts the rules after the apply, ``scoped_rule_count`` those with paths:, and
    ``entries`` are the plan entries. Claude Code reads
    the rules as .claude/rules and loads those with paths: only for matching files; Codex lists every
    rule in AGENTS.md. Subagents and commands reach Codex as skills of the same name.
    """
    written = [entry["destination"] for entry in entries if entry.get("sha256")]
    skills = {path.split("/")[2] for path in written if path.startswith(SKILLS_PREFIX) and path.endswith("/SKILL.md")}
    agents = {os.path.basename(path)[:-3] for path in written if path.startswith(AGENTS_PREFIX) and path.endswith(".md")}
    commands = {os.path.basename(path)[:-3] for path in written if path.startswith(COMMANDS_PREFIX) and path.endswith(".md")}
    return {
        PROVIDER_CLAUDE: {"rules": rule_count, "rulesForPathsOnly": scoped_rule_count, "skills": len(skills - agents - commands),
                          "subagents": len(agents), "commands": len(commands)},
        PROVIDER_CODEX: {"rules": rule_count, "rulesForPathsOnly": 0, "skills": len(skills | agents | commands)},
    }


def hook_differences(project_root, skill_dir):
    """Hooks one provider runs and the other does not: the golfo-kit templates (except the events
    declared provider-specific) and the project's own hooks, compared by command."""
    layers = settings_conflicts.layers(project_root, skill_dir)
    differences = []
    for layer_name in (settings_conflicts.LAYER_GOLFO, settings_conflicts.LAYER_PROJECT):
        commands = {provider: {} for provider in (PROVIDER_CLAUDE, PROVIDER_CODEX)}
        for layer in layers:
            if layer["layer"] == layer_name and layer["provider"] in commands:
                for event, _, command in settings_conflicts.hook_entries(layer["data"]):
                    commands[layer["provider"]].setdefault(command, (event, layer["file"]))
        for provider, other in ((PROVIDER_CLAUDE, PROVIDER_CODEX), (PROVIDER_CODEX, PROVIDER_CLAUDE)):
            for command, (event, file) in sorted(commands[provider].items()):
                if command in commands[other] or provider_neutral(command) in map(provider_neutral, commands[other]):
                    continue
                if (provider, event) in PROVIDER_SPECIFIC_HOOK_EVENTS:
                    continue
                differences.append({"provider": provider, "missing": other, "event": event, "command": command,
                                    "file": file})
    return differences


def provider_neutral(command):
    """A hook command without the --provider it passes, so the same hook of each provider compares equal."""
    return re.sub(r"\s--provider\s+\S+", "", command)


def environment_variables(declarations, project_root):
    """Variables the pack tools ask for that collide: asked by two sources, or listed by the project."""
    asked = {}
    for tool in declarations:
        if tool.get("type") != pack_tools.TOOL_MCP_SERVER:
            continue
        server = tool.get("server") or {}
        names = [pack_tools.referenced_variable(value) for value in (server.get("env") or {}).values()]
        names += [pack_tools.referenced_variable(value, header) for header, value in (server.get("headers") or {}).items()]
        for name in filter(None, names):
            asked.setdefault(name, {}).setdefault(tool["source"], set()).add(tool["profile"])
    listed = project_environment(project_root)
    findings = []
    for name, sources in sorted(asked.items()):
        profiles = sorted({profile for names in sources.values() for profile in names})
        if len(sources) > 1:
            findings.append({"name": name, "profiles": profiles, "sources": sorted(sources)})
        if name in listed:
            findings.append({"name": name, "profiles": profiles, "file": listed[name]})
    return findings


def project_environment(project_root):
    """{name: file} of the variables the project lists in its example environment files."""
    listed = {}
    for name in EXAMPLE_ENVIRONMENT_FILES:
        path = os.path.join(project_root, name)
        if not os.path.isfile(path) or os.path.islink(path):
            continue
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as environment_file:
                for line in environment_file:
                    match = ENVIRONMENT_LINE.match(line)
                    if match:
                        listed.setdefault(match.group("name"), name)
        except OSError:
            continue
    return listed


def duplicated_ci_jobs(project_root, entries, block_destinations):
    """The repository's own CI files that already run the Agent Ready check the managed CI adds.

    ``entries`` are the plan entries and ``block_destinations`` the files where the selection places
    a managed block (.gitlab-ci.yml); the text inside the managed block is the engine's, not the
    repository's.
    """
    managed = {entry["destination"] for entry in entries if entry.get("sha256")}
    # The managed entry points of the CI: the helper script under .agents/ci only runs through them.
    managed_ci = sorted(path for path in managed | set(block_destinations)
                        if path.startswith(".github/workflows/") or path == ".gitlab-ci.yml")
    if not managed_ci:
        return []
    findings = []
    for pattern in REPOSITORY_CI_FILES:
        for path in sorted(glob.glob(os.path.join(glob.escape(project_root), *pattern.split("/")))):
            relative = os.path.relpath(path, project_root).replace(os.sep, "/")
            if relative in managed or os.path.islink(path) or not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as ci_file:
                    text = ci_file.read()
            except OSError:
                continue
            if relative in block_destinations:
                text = without_managed_blocks(text)
            if AGENT_READY_CHECK_PATTERN.search(text):
                findings.append({"file": relative, "managed": managed_ci})
    return findings


def without_managed_blocks(text):
    """A shared file without the lines between agent-ready markers."""
    kept, inside = [], False
    for line in text.splitlines():
        if "BEGIN AGENT-READY MANAGED" in line:
            inside = True
            continue
        if "END AGENT-READY MANAGED" in line:
            inside = False
            continue
        if not inside:
            kept.append(line)
    return "\n".join(kept)
