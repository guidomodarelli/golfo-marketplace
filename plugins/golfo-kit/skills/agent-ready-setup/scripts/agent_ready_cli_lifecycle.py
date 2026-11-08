"""Subcommands around the life of an installation: ``doctor`` checks this machine, ``remove`` undoes the setup.

``doctor`` only reads: it runs the same with and without a terminal. ``remove`` asks for a
confirmation only with a terminal; without one it needs ``--yes``, and ``--dry-run`` shows
the plan without touching anything.
"""

import os
import re
import shlex
import shutil
import subprocess
import sys

from agent_ready_cli_common import (
    CLI_NAME,
    EXIT_CANCELLED,
    EXIT_FAILED,
    EXIT_OK,
    SKILL_ROOT,
    SUPPORTED_PROVIDERS,
    UsageError,
    declared_sources,
    engine,
    find_repository_root,
)
from agent_ready_common import StateError, bash_executable, plugin_version, read_json_file, serialize_json
from agent_ready_config import ConfigurationError, resolve_configuration
from agent_ready_options import PROVIDERS_KEY
from agent_ready_packs import SOURCE_TYPE_GIT, SOURCE_TYPE_PATH
from agent_ready_prompts import ask_confirmation, can_prompt, equivalent_command

# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

CHECK_OK = "ok"
CHECK_MISSING = "missing"
CHECK_WARNING = "warning"
CHECK_SKIPPED = "skipped"
CHECK_SYMBOLS = {CHECK_OK: "✓", CHECK_MISSING: "✗", CHECK_WARNING: "!", CHECK_SKIPPED: "-"}
CHECK_COLORS = {CHECK_OK: "ok", CHECK_MISSING: "error", CHECK_WARNING: "warning", CHECK_SKIPPED: "muted"}
# The lockfile declares the same minimum; the hooks run python3 from PATH.
MINIMUM_PYTHON = (3, 8)
PROBE_TIMEOUT_SECONDS = 30
PYTHON_VERSION_PATTERN = re.compile(r"Python (\d+)\.(\d+)")
HOOK_SCRIPTS_DIRECTORY = ".agents/hooks/"
# Where each provider reads the hooks that an apply merges.
PROVIDER_HOOK_FILES = {"claude": ".claude/settings.json", "codex": ".codex/hooks.json"}


def check(name, status, detail, fix=None):
    """One line of the doctor report."""
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def run_probe(command, cwd=None):
    """(exit status, output lines) of a read-only command; never asks for credentials."""
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace",
                                   timeout=PROBE_TIMEOUT_SECONDS, env=environment, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, [f"no answer after {PROBE_TIMEOUT_SECONDS} s"]
    except OSError as caught_error:
        return None, [str(caught_error)]
    return completed.returncode, (completed.stdout.strip() or completed.stderr.strip()).splitlines() or [""]


def run_in_hook_shell(script):
    """Run a command line the way the session hooks do: through Bash, with its own PATH lookup.

    Native Windows lookups only find files with a PATHEXT extension, while Bash also finds
    the extensionless scripts and shims that the hooks end up running.
    """
    if not shutil.which("bash"):
        return None, ["bash is not on PATH"]
    return run_probe([bash_executable(), "-c", script])


def check_git(project):
    """Git on PATH, and the project inside a worktree: the projection and the lockfile need both."""
    if not shutil.which("git"):
        return check("git", CHECK_MISSING, "Git is not on PATH", "install Git and open a new terminal")
    status, output = run_probe(["git", "-C", project, "rev-parse", "--show-toplevel"])
    if status != 0:
        return check("git", CHECK_MISSING, f"{project} is not inside a Git worktree",
                     "run it from a repository, or pass --project <path>")
    return check("git", CHECK_OK, f"worktree {output[0]}")


def check_bash():
    """Bash runs the projection and the hooks."""
    if not shutil.which("bash"):
        return check("bash", CHECK_MISSING, "Bash is not on PATH", "install Bash (on Windows, Git for Windows brings it)")
    status, output = run_probe([bash_executable(), "--version"])
    if status != 0:
        return check("bash", CHECK_MISSING, f"bash does not run: {output[-1]}", "reinstall Bash and open a new terminal")
    return check("bash", CHECK_OK, output[0])


def check_python():
    """This interpreter, and the python3 that the hooks of every session run."""
    running = ".".join(str(part) for part in sys.version_info[:3])
    minimum = ".".join(str(part) for part in MINIMUM_PYTHON)
    if sys.version_info[:2] < MINIMUM_PYTHON:
        return check("python", CHECK_MISSING, f"Python {running} is older than {minimum}", f"install Python {minimum} or newer")
    status, output = run_in_hook_shell("python3 --version")
    if status != 0:
        return check("python", CHECK_MISSING, "python3 is not on PATH, and the session hooks run it",
                     f"install Python {minimum} or newer and make python3 reachable from PATH")
    # The hooks run this python3, which can be older than the interpreter running doctor.
    version = PYTHON_VERSION_PATTERN.search(" ".join(output))
    if not version or (int(version.group(1)), int(version.group(2))) < MINIMUM_PYTHON:
        return check("python", CHECK_MISSING, f"the python3 on PATH, which the session hooks run, reports '{output[0]}'",
                     f"install Python {minimum} or newer and put it first on PATH as python3")
    return check("python", CHECK_OK, f"{output[0]} on PATH (this run: Python {running})")


def configured_providers(configuration):
    """Providers the repository declares, or both while the configuration cannot be read."""
    return configuration.value(PROVIDERS_KEY) if configuration else list(SUPPORTED_PROVIDERS)


def check_provider_cli(providers):
    """At least one agent CLI of the declared providers: the hooks and the marketplace refresh run it."""
    found = [provider for provider in providers if run_in_hook_shell(f"command -v {provider}")[0] == 0]
    if not found:
        names = " or ".join({"claude": "Claude Code (claude)", "codex": "Codex (codex)"}[provider] for provider in providers)
        return check("provider", CHECK_MISSING, f"{' and '.join(providers)} {'is' if len(providers) == 1 else 'are'} not on PATH",
                     f"install {names} and open a new terminal")
    missing = [provider for provider in providers if provider not in found]
    detail = ", ".join(found) + " on PATH" + (f"; {', '.join(missing)} is not, which only matters to use it" if missing else "")
    return check("provider", CHECK_OK, detail)


def check_configuration(project):
    """Every configuration layer valid; returns the check and the configuration, or None."""
    try:
        configuration = resolve_configuration(project)
    except (ConfigurationError, StateError) as configuration_error:
        return check("configuration", CHECK_MISSING, str(configuration_error),
                     f"fix the file it names; {CLI_NAME} config explain shows each value and its layer"), None
    return check("configuration", CHECK_OK, "every layer is valid"), configuration


def check_sources(project, configuration, offline):
    """Each declared profile source reachable: a path that exists, a repository that answers."""
    if configuration is None:
        return [check("sources", CHECK_SKIPPED, "the configuration is not valid")]
    try:
        declarations = declared_sources(project)
    except StateError as invalid_source:
        return [check("sources", CHECK_MISSING, str(invalid_source), f"fix it with {CLI_NAME} sources remove <name>")]
    if declarations is None:
        return [check("sources", CHECK_SKIPPED, "sources.enabled is false")]
    if not declarations:
        return [check("sources", CHECK_OK, "no profile source declared")]
    checks = []
    for declaration in declarations:
        name = f"source {declaration['name']}"
        if declaration["type"] == SOURCE_TYPE_PATH:
            root = os.path.join(project, *declaration["origin"].split("/"))
            if os.path.isdir(root):
                checks.append(check(name, CHECK_OK, f"path {declaration['origin']} exists"))
            else:
                checks.append(check(name, CHECK_MISSING, f"path {declaration['origin']} does not exist",
                                    f"restore it, or {CLI_NAME} sources remove {declaration['name']}"))
            continue
        if declaration["type"] != SOURCE_TYPE_GIT or offline:
            checks.append(check(name, CHECK_SKIPPED, "--offline: the repository was not contacted"))
            continue
        status, output = run_probe(["git", "ls-remote", "--quiet", declaration["origin"]])
        if status == 0:
            checks.append(check(name, CHECK_OK, f"{declaration['origin']} answers"))
        else:
            checks.append(check(name, CHECK_MISSING, f"{declaration['origin']} does not answer: {output[-1]}",
                                f"check the URL and your access with git ls-remote {declaration['origin']}, "
                                f"or {CLI_NAME} sources remove {declaration['name']}"))
    return checks


def hook_handlers(document):
    """(event, matcher, command) of every command hook: a handler only runs in its event and matcher."""
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return []
    return [(event, group.get("matcher"), handler["command"])
            for event, groups in hooks.items() if isinstance(groups, list)
            for group in groups if isinstance(group, dict) and isinstance(group.get("hooks"), list)
            for handler in group["hooks"] if isinstance(handler, dict) and isinstance(handler.get("command"), str)]


def present_hook_handlers(path):
    """The hook handlers of a provider file, or None when it cannot be read."""
    try:
        return set(hook_handlers(read_json_file(path, "provider settings")))
    except StateError:
        return None


def hook_scripts(commands):
    """The scripts under .agents/hooks/ that the hook commands run."""
    return sorted({token for command in commands for token in shlex.split(command) if token.startswith(HOOK_SCRIPTS_DIRECTORY)})


def check_hooks(project, providers):
    """The hooks an apply installs, for each declared provider; skipped before the first apply."""
    try:
        lock = engine().read_lock(project)
    except StateError as lock_error:
        return [check("hooks", CHECK_MISSING, str(lock_error), f"{CLI_NAME} apply")]
    if lock is None:
        return [check("hooks", CHECK_SKIPPED, "agent-ready-setup is not applied in this repository",
                      f"{CLI_NAME} init sets it up")]
    templates = dict(engine().settings_templates(SKILL_ROOT))
    checks = []
    for provider in providers:
        destination = PROVIDER_HOOK_FILES[provider]
        expected = hook_handlers(read_json_file(templates[destination], "agent-ready hooks template"))
        present = present_hook_handlers(os.path.join(project, destination))
        commands = [command for _, _, command in expected]
        missing_scripts = [script for script in hook_scripts(commands) if not os.path.isfile(os.path.join(project, script))]
        if present is None:
            checks.append(check(f"hooks {provider}", CHECK_MISSING, f"{destination} is not valid JSON",
                                f"fix it, then {CLI_NAME} apply"))
        elif not set(expected) <= present or missing_scripts:
            missing = [f"{event}: {command}" for event, matcher, command in expected if (event, matcher, command) not in present]
            missing += missing_scripts
            checks.append(check(f"hooks {provider}", CHECK_MISSING, f"missing: {', '.join(missing)}", f"{CLI_NAME} apply"))
        else:
            checks.append(check(f"hooks {provider}", CHECK_OK, f"{destination} runs the agent-ready hooks"))
    return checks


def doctor_checks(project, offline):
    """Every check, in the order a person fixes them."""
    configuration_check, configuration = check_configuration(project)
    providers = configured_providers(configuration)
    return [
        check_git(project),
        check_bash(),
        check_python(),
        check_provider_cli(providers),
        check("engine", CHECK_OK, f"golfo-kit {plugin_version(SKILL_ROOT) or 'with an unknown version'}"),
        configuration_check,
        *check_sources(project, configuration, offline),
        *check_hooks(project, providers),
    ]


def print_doctor_report(checks, stream):
    """One line per check, its fix below when something is missing."""
    paint = engine().paint
    width = max(len(item["name"]) for item in checks)
    for item in checks:
        symbol = paint(CHECK_SYMBOLS[item["status"]], CHECK_COLORS[item["status"]], stream)
        stream.write(f"{symbol} {item['name']:<{width}}  {item['detail']}\n")
        if item["fix"] and item["status"] in (CHECK_MISSING, CHECK_WARNING):
            stream.write(f"  {' ' * width}  fix: {item['fix']}\n")


def command_doctor(arguments):
    """Check what the engine needs on this machine and in this repository; exits 1 when something is missing."""
    try:
        # From a subdirectory, the configuration, the sources and the lockfile live at the root.
        project = find_repository_root(arguments.project)
    except UsageError:
        project = os.path.abspath(arguments.project)
    checks = doctor_checks(project, arguments.offline)
    problems = [item for item in checks if item["status"] == CHECK_MISSING]
    if arguments.json:
        sys.stdout.write(serialize_json({"ok": not problems, "checks": checks}))
    else:
        print_doctor_report(checks, sys.stdout)
        summary = "Everything agent-ready-setup needs is in place." if not problems else \
            f"{len(problems)} {'problem' if len(problems) == 1 else 'problems'}: fix them and run {CLI_NAME} doctor again."
        sys.stderr.write(summary + "\n")
    return EXIT_FAILED if problems else EXIT_OK


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

def print_removal_report(report, stream):
    """What the removal did, then what it kept and why."""
    stream.write(f"Removed {len(report['removed'])} and edited {len(report['edited'])} paths; "
                 f"kept {len(report['kept'])}.\n")
    for line in report["kept"]:
        stream.write(f"  kept {line}\n")
    for line in report["failed"]:
        stream.write(f"  failed {line}\n")


def command_remove(arguments):
    """Remove agent-ready-setup from the repository; what the project wrote stays."""
    plan = engine().plan_removal(arguments.project_root, SKILL_ROOT)
    if not plan["changes"]:
        if arguments.json:
            sys.stdout.write(serialize_json(plan))
        sys.stderr.write("agent-ready-setup is not set up in this repository: there is nothing to remove.\n")
        return EXIT_OK
    if arguments.dry_run:
        if arguments.json:
            sys.stdout.write(serialize_json(plan))
        else:
            sys.stdout.write(f"{CLI_NAME} remove would change these paths:\n")
            engine().print_removal_plan(plan, sys.stdout)
        return EXIT_OK
    asked = False
    if not arguments.yes:
        if not can_prompt(arguments.no_input):
            raise UsageError("missing --yes: removing agent-ready-setup needs a confirmation and there is no terminal to ask "
                             f"({CLI_NAME} remove --dry-run shows what it changes)")
        sys.stderr.write("This removes agent-ready-setup from the repository:\n")
        engine().print_removal_plan(plan, sys.stderr)
        if not ask_confirmation("Remove agent-ready-setup from this repository?", False):
            sys.stderr.write("Nothing was changed.\n")
            return EXIT_OK
        asked = True
    try:
        report = engine().remove_from_repository(arguments.project_root, SKILL_ROOT)
    except KeyboardInterrupt:
        # Past the confirmation, part of the repository may already be clean; the lockfile goes last.
        sys.stderr.write(f"{CLI_NAME}: cancelled halfway: some paths were already removed; "
                         f"run {CLI_NAME} remove again to finish\n")
        return EXIT_CANCELLED
    if arguments.json:
        sys.stdout.write(serialize_json(report))
    else:
        print_removal_report(report, sys.stderr)
    if asked:
        command = [CLI_NAME, "remove", "--yes"]
        if os.path.abspath(arguments.project) != os.path.abspath("."):
            command += ["--project", arguments.project]
        sys.stderr.write(f"Equivalent command: {equivalent_command(command)}\n")
    return EXIT_FAILED if report["failed"] else EXIT_OK


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def register(subparsers, new_subparser):
    """Add doctor and remove to the CLI parser."""
    doctor = new_subparser(subparsers, "doctor", "Check what agent-ready-setup needs and say how to fix what is missing.",
                           "  agent-ready doctor\n  agent-ready doctor --offline --json", command_doctor)
    doctor.add_argument("--offline", action="store_true", help="do not contact the Git profile sources")
    doctor.add_argument("--json", action="store_true", help="print the checks as JSON on stdout")
    # A machine without a repository still deserves an answer: git is one of the checks.
    doctor.set_defaults(needs_repository=False)

    remove = new_subparser(subparsers, "remove", "Remove agent-ready-setup from the repository and keep what the project wrote.",
                           "  agent-ready remove --dry-run\n  agent-ready remove --yes", command_remove)
    remove.add_argument("-n", "--dry-run", action="store_true", help="list what it would remove, edit and keep, and change nothing")
    remove.add_argument("-y", "--yes", action="store_true", help="remove without asking (required without a terminal)")
    remove.add_argument("--no-input", action="store_true", help="never ask; without --yes it fails with exit 2")
    remove.add_argument("--json", action="store_true", help="print the plan or the result as JSON on stdout")
