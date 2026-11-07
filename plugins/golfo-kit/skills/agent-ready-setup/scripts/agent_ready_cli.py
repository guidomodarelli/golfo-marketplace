"""Command line of agent-ready-setup: one subcommand per flow, over the engine of this installation.

It parses, resolves what is missing and delegates: ``bootstrap.sh`` projects and plans,
``agent-ready-state.py`` checks and reports, and ``agent_ready_config`` reads and writes the
configuration layers. It never reimplements their logic. Data goes to stdout; progress,
warnings and errors go to stderr. No subcommand of this module asks anything, so every one
runs the same with and without a terminal.
"""

import argparse
import json
import os
import subprocess
import sys

from agent_ready_common import StateError, bash_executable, plugin_version, serialize_json, write_text_atomically
from agent_ready_packs import FULL_COMMIT, SOURCE_TYPE_GIT, parse_profile_sources
from agent_ready_config import (
    LAYER_PROJECT,
    LAYER_USER,
    PROJECT_CONFIG_RELATIVE_PATH,
    ConfigurationError,
    describe_layer,
    format_value,
    load_schema,
    parse_text_value,
    read_layer_file,
    resolve_configuration,
    user_config_path,
    validate_layer,
)
from agent_ready_options import SOURCES_ENABLED_KEY, SOURCES_PACKS_KEY

CLI_NAME = "agent-ready"
SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIRECTORY)
BOOTSTRAP_SCRIPT = os.path.join(SCRIPT_DIRECTORY, "bootstrap.sh")
STATE_SCRIPT = os.path.join(SCRIPT_DIRECTORY, "agent-ready-state.py")
PROVIDER_RESOLVER_SCRIPT = os.path.join(SCRIPT_DIRECTORY, "resolve-provider.sh")
MERGE_INSTRUCTIONS_RELATIVE_PATH = "scripts/merge-instructions.sh"
RESOLVED_SOURCE_PREFIX = "Resolved agent-ready-setup source: "
RESOLVED_STACK_PREFIX = "Stack: "
PROVIDER_VARIABLE = "AGENT_READY_SETUP_ACTIVE_PROVIDER"
SUPPORTED_PROVIDERS = ("claude", "codex")
UPDATE_MODES = ("auto", "pinned")
# Hermes exports these to stop Git Bash from translating paths, but the scripts hand POSIX
# paths to native Windows Python, which needs that translation.
PATH_CONVERSION_VARIABLES = ("MSYS_NO_PATHCONV", "MSYS2_ARG_CONV_EXCL")
WRITABLE_LAYERS = (LAYER_PROJECT, LAYER_USER)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_OUTDATED = 4
EXIT_SOURCE_UNAVAILABLE = 5
EXIT_CANCELLED = 130

EXIT_STATUS_HELP = f"""exit status:
  {EXIT_OK}    success
  {EXIT_FAILED}    the operation failed
  {EXIT_USAGE}    wrong usage or invalid configuration
  {EXIT_OUTDATED}    outdated (check)
  {EXIT_SOURCE_UNAVAILABLE}    a profile source is not available
  {EXIT_CANCELLED}  cancelled"""


class UsageError(Exception):
    """Wrong usage the parser cannot see, such as an unknown configuration key; exits 2."""


def fail(message):
    """One line on stderr naming the command."""
    sys.stderr.write(f"{CLI_NAME}: {message}\n")


def find_repository_root(start):
    """Root of the Git repository that holds ``start``, found without running Git."""
    current = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise UsageError(f"{os.path.abspath(start)} is not inside a Git repository; run it from one or pass --project")
        current = parent


def bash_environment():
    """Environment for the Bash scripts, with the path translation that native Python needs."""
    return {key: value for key, value in os.environ.items() if key not in PATH_CONVERSION_VARIABLES}


def run_bash(command, cwd, **options):
    """Run a Bash command of the engine and return its exit status."""
    return subprocess.call(command, cwd=cwd, env=bash_environment(), **options)


def resolve_provider(requested):
    """Provider of this run: the flag, then the environment, then the installation path."""
    if requested:
        return requested
    from_environment = os.environ.get(PROVIDER_VARIABLE)
    if from_environment in SUPPORTED_PROVIDERS:
        return from_environment
    completed = subprocess.run(
        [bash_executable(), PROVIDER_RESOLVER_SCRIPT, "--skill-dir", SKILL_ROOT],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=bash_environment(),
    )
    provider = completed.stdout.strip()
    if completed.returncode != 0 or provider not in SUPPORTED_PROVIDERS:
        detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "no provider could be inferred"
        raise UsageError(f"{detail}; pass --provider {'|'.join(SUPPORTED_PROVIDERS)}")
    return provider


def bootstrap_command(provider, *extra):
    """Command line of bootstrap.sh for this installation."""
    return [bash_executable(), BOOTSTRAP_SCRIPT, "--skill-dir", SKILL_ROOT, "--provider", provider, *extra]


def selection_arguments(arguments):
    """--profiles or --stack, when the run chose the profiles explicitly."""
    if getattr(arguments, "profiles", None):
        return ["--profiles", arguments.profiles]
    if getattr(arguments, "stack", None):
        return ["--stack", arguments.stack]
    return []


def update_source_arguments(names):
    """One --update-source per source to adopt."""
    return [argument for name in names for argument in ("--update-source", name)]


def run_streaming(command, cwd):
    """Run a command whose stdout is our stdout; its stderr is copied to ours and returned."""
    process = subprocess.Popen(command, cwd=cwd, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                               env=bash_environment())
    captured = []
    for line in process.stderr:
        sys.stderr.write(line)
        captured.append(line.rstrip("\r\n"))
    return process.wait(), captured


def last_value(lines, prefix):
    """Value of the last line that starts with ``prefix``, or None."""
    values = [line[len(prefix):].strip() for line in lines if line.startswith(prefix)]
    return values[-1] if values else None


def declared_sources(project_root):
    """Profile sources in force, as the engine resolves them: none while sources are off."""
    configuration = resolve_configuration(project_root)
    if not configuration.value(SOURCES_ENABLED_KEY):
        return None
    path = os.path.join(project_root, PROJECT_CONFIG_RELATIVE_PATH)
    return parse_profile_sources(configuration.value(SOURCES_PACKS_KEY), path)


def follows_a_ref(declaration):
    """True for a Git source that names a branch or a tag; a full commit or a path has nothing to update."""
    return declaration["type"] == SOURCE_TYPE_GIT and not FULL_COMMIT.fullmatch(declaration["requestedRef"])


# ---------------------------------------------------------------------------
# Subcommands that delegate to the engine
# ---------------------------------------------------------------------------

def command_plan(arguments):
    """Read-only plan of what an apply would change."""
    extra = ["--plan", *selection_arguments(arguments)]
    extra += ["--offline"] if arguments.offline else []
    extra += ["--json"] if arguments.json else []
    return run_bash(bootstrap_command(resolve_provider(arguments.provider), *extra), arguments.project_root)


def command_status(arguments):
    """Read-only status of the checkout against the lockfile and the sources."""
    extra = ["--status"] + (["--offline"] if arguments.offline else []) + (["--json"] if arguments.json else [])
    return run_bash(bootstrap_command(resolve_provider(arguments.provider), *extra), arguments.project_root)


def command_check(arguments):
    """The CI check: same exit statuses and JSON as agent-ready-state.py check."""
    command = [sys.executable, STATE_SCRIPT, "check", "--project", arguments.project_root, "--skill-dir", SKILL_ROOT]
    command += ["--offline"] if arguments.offline else []
    command += ["--format", "json"] if arguments.json or arguments.format == "json" else []
    return subprocess.call(command, cwd=arguments.project_root)


def apply_selection(arguments, provider, extra):
    """Project the assets, then align AGENTS.md with merge-instructions.sh from the resolved source."""
    status, lines = run_streaming(bootstrap_command(provider, *extra), arguments.project_root)
    if status != EXIT_OK:
        return status
    resolved_source = last_value(lines, RESOLVED_SOURCE_PREFIX)
    stack = last_value(lines, RESOLVED_STACK_PREFIX)
    if not resolved_source or not stack:
        fail("bootstrap.sh did not report its resolved source and stack; merge-instructions.sh was not run")
        return EXIT_FAILED
    merge_command = [bash_executable(), f"{resolved_source}/{MERGE_INSTRUCTIONS_RELATIVE_PATH}",
                     "--provider", provider, "--stack", stack, "--skill-dir", resolved_source]
    merge_status = run_bash(merge_command, arguments.project_root, stdout=sys.stderr)
    if merge_status != EXIT_OK:
        fail(f"merge-instructions.sh failed with exit status {merge_status}; the assets were applied, AGENTS.md was not aligned")
        return EXIT_FAILED
    return EXIT_OK


def command_apply(arguments):
    """Apply the selection: projection, lockfile, manifest and the managed block of AGENTS.md."""
    provider = resolve_provider(arguments.provider)
    selection = selection_arguments(arguments)
    if arguments.dry_run:
        return run_bash(bootstrap_command(provider, "--plan", *selection), arguments.project_root)
    extra = selection + (["--updates", arguments.updates] if arguments.updates else [])
    return apply_selection(arguments, provider, extra)


def command_update(arguments):
    """Adopt the latest revision of some sources, or of every declared one, and of golfo-kit."""
    sources = declared_sources(arguments.project_root)
    if sources is None and arguments.sources:
        raise UsageError(f"profile sources are off ({SOURCES_ENABLED_KEY}: false), so there is no source to update")
    declarations = {declaration["name"]: declaration for declaration in sources or []}
    unknown = [name for name in arguments.sources if name not in declarations]
    if unknown:
        known = ", ".join(sorted(declarations)) or "none"
        raise UsageError(f"unknown profile source {', '.join(unknown)}; the manifest declares: {known}")
    names = arguments.sources or [name for name, declaration in sorted(declarations.items()) if follows_a_ref(declaration)]
    provider = resolve_provider(arguments.provider)
    extra = update_source_arguments(names)
    if arguments.dry_run:
        return run_bash(bootstrap_command(provider, "--plan", *extra), arguments.project_root)
    return apply_selection(arguments, provider, extra)


# ---------------------------------------------------------------------------
# config get|set|unset|explain
# ---------------------------------------------------------------------------

def effective_configuration(arguments):
    """The effective configuration as agent-ready-state.py config --format json prints it."""
    command = [sys.executable, STATE_SCRIPT, "config", "--project", arguments.project_root, "--format", "json"]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        raise ConfigurationError(completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "invalid configuration")
    return json.loads(completed.stdout)


def leaf_of(key):
    """Schema node of an option, or a usage error that lists the options."""
    schema = load_schema()
    if key not in schema.leaves:
        raise UsageError(f"unknown configuration key '{key}'; valid keys: {', '.join(sorted(schema.leaves))}")
    return schema, schema.leaves[key]


def value_at(document, key):
    """Value of a dotted key inside a nested document."""
    for part in key.split("."):
        document = document[part]
    return document


def command_config_get(arguments):
    """Print the effective value of one option."""
    leaf_of(arguments.key)
    report = effective_configuration(arguments)
    value = value_at(report["values"], arguments.key) if arguments.key in report["origins"] else None
    sys.stdout.write((json.dumps(value) if arguments.json else format_value(value)) + "\n")
    return EXIT_OK


def explain_key(report, key):
    """Value, origin and ignored attempts of one option."""
    value = value_at(report["values"], key) if key in report["origins"] else None
    return {
        "key": key,
        "value": value,
        "origin": report["origins"].get(key, "unset"),
        "ignored": [item for item in report["ignored"] if item["key"] == key],
    }


def command_config_explain(arguments):
    """Effective value and the layer it comes from, for one option or all of them."""
    if arguments.key:
        leaf_of(arguments.key)
        explanation = explain_key(effective_configuration(arguments), arguments.key)
        if arguments.json:
            sys.stdout.write(serialize_json(explanation))
            return EXIT_OK
        value = format_value(explanation["value"]) or "-"
        sys.stdout.write(f"{arguments.key}  {value}  ({explanation['origin']})\n")
        for item in explanation["ignored"]:
            sys.stdout.write(f"  ignored from the {item['layer']} layer: {format_value(item['value'])} ({item['reason']})\n")
        return EXIT_OK
    command = [sys.executable, STATE_SCRIPT, "config", "--project", arguments.project_root]
    command += ["--format", "json"] if arguments.json else []
    return subprocess.call(command)


def layer_path(arguments):
    """File of the writable layer the command targets."""
    if arguments.layer == LAYER_USER:
        return user_config_path(os.environ)
    return os.path.join(arguments.project_root, PROJECT_CONFIG_RELATIVE_PATH)


def write_layer(arguments, change):
    """Read the layer, apply ``change`` to it, validate the result and write it atomically."""
    path = layer_path(arguments)
    schema = load_schema()
    label = describe_layer(arguments.layer, path)
    document = read_layer_file(path, arguments.layer) or {}
    validate_layer(schema, document, arguments.layer, label)
    changed = change(schema, document)
    validate_layer(schema, document, arguments.layer, label)
    if changed:
        write_text_atomically(path, serialize_json(document))
    return path, changed


def command_config_set(arguments):
    """Write one option into the project or the user layer, validated before writing."""
    _, node = leaf_of(arguments.key)
    value = parse_text_value(arguments.value, node)

    def change(schema, document):
        parts = arguments.key.split(".")
        target = document
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        previous = target.get(parts[-1], object())
        target[parts[-1]] = value
        return previous != value

    path, changed = write_layer(arguments, change)
    state = "set" if changed else "already set"
    sys.stderr.write(f"{arguments.key}={format_value(value)} {state} in the {arguments.layer} layer ({path}).\n")
    return report_effective(arguments)


def command_config_unset(arguments):
    """Remove one option from the project or the user layer; the lower layers decide again."""
    leaf_of(arguments.key)

    def change(schema, document):
        parts = arguments.key.split(".")
        chain = [document]
        for part in parts[:-1]:
            child = chain[-1].get(part)
            if not isinstance(child, dict):
                return False
            chain.append(child)
        if parts[-1] not in chain[-1]:
            return False
        del chain[-1][parts[-1]]
        for depth in range(len(parts) - 1, 0, -1):
            if not chain[depth]:
                del chain[depth - 1][parts[depth - 1]]
        return True

    path, changed = write_layer(arguments, change)
    state = "removed from" if changed else "was not set in"
    sys.stderr.write(f"{arguments.key} {state} the {arguments.layer} layer ({path}).\n")
    return report_effective(arguments)


def report_effective(arguments):
    """After a write, say on stderr what is in force now and whether something ignores it."""
    explanation = explain_key(effective_configuration(arguments), arguments.key)
    sys.stderr.write(f"Effective now: {arguments.key}={format_value(explanation['value']) or '-'} ({explanation['origin']})\n")
    for item in explanation["ignored"]:
        sys.stderr.write(f"  ! ignored from the {item['layer']} layer: {format_value(item['value'])} ({item['reason']})\n")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def version_text():
    """golfo-kit version of this installation."""
    return f"{CLI_NAME} {plugin_version(SKILL_ROOT) or 'unknown version'}"


class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Keeps the examples and the exit statuses as written."""


def new_subparser(subparsers, name, summary, examples, handler, needs_provider=False, with_project=True):
    """A subcommand with its own --help, --version, --project and, when it runs bootstrap, --provider."""
    subparser = subparsers.add_parser(
        name, help=summary, description=f"{summary}\n\nexamples:\n{examples}",
        epilog=EXIT_STATUS_HELP, formatter_class=HelpFormatter,
    )
    subparser.add_argument("--version", action="version", version=version_text())
    if with_project:
        subparser.add_argument("--project", default=".", help="repository to work on (default: the current directory)")
    if needs_provider:
        subparser.add_argument("--provider", choices=SUPPORTED_PROVIDERS,
                               help=f"provider whose marketplace is refreshed (default: ${PROVIDER_VARIABLE}, then the installation)")
    subparser.set_defaults(handler=handler)
    return subparser


def add_selection(subparser):
    """--profiles and --stack, mutually exclusive."""
    group = subparser.add_mutually_exclusive_group()
    group.add_argument("--profiles", help="comma separated profiles, e.g. node,browser (default: the manifest, then detection)")
    group.add_argument("--stack", help="a stack and its default profiles, e.g. frontend")


def build_parser():
    """Parser of every subcommand."""
    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description=("Prepare a repository for Claude Code and Codex with agent-ready-setup.\n\n"
                     "examples:\n  agent-ready plan\n  agent-ready apply --profiles node,browser\n"
                     "  agent-ready check --json"),
        epilog=EXIT_STATUS_HELP, formatter_class=HelpFormatter,
    )
    parser.add_argument("--version", action="version", version=version_text())
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    plan = new_subparser(subparsers, "plan", "Show what an apply would change, without writing to the repository.",
                         "  agent-ready plan\n  agent-ready plan --offline --json > plan.json", command_plan, needs_provider=True)
    add_selection(plan)
    plan.add_argument("--offline", action="store_true", help="use no network: compare with the cache only")
    plan.add_argument("--json", action="store_true", help="print the plan as JSON on stdout")

    status = new_subparser(subparsers, "status", "Compare the checkout with the lockfile and the sources, read-only.",
                           "  agent-ready status\n  agent-ready status --offline --json", command_status, needs_provider=True)
    status.add_argument("--offline", action="store_true", help="use no network: compare with the cache only")
    status.add_argument("--json", action="store_true", help="print the status as JSON on stdout")

    check = new_subparser(subparsers, "check", "CI check: exits 4 when outdated and 5 when a source is not available.",
                          "  agent-ready check\n  agent-ready check --json > agent-ready-check.json", command_check)
    check.add_argument("--offline", action="store_true", help="compare with the cache, without the network")
    check.add_argument("--json", action="store_true", help="print the result as JSON on stdout")
    check.add_argument("--format", choices=("text", "json"), default="text", help="same as --json with json (default: text)")

    apply_parser = new_subparser(subparsers, "apply", "Apply the selected profiles and align AGENTS.md.",
                                 "  agent-ready apply\n  agent-ready apply --profiles node,business-flows --dry-run",
                                 command_apply, needs_provider=True)
    add_selection(apply_parser)
    apply_parser.add_argument("--updates", choices=UPDATE_MODES, help="write updates.mode into the manifest (auto removes it)")
    apply_parser.add_argument("-n", "--dry-run", action="store_true", help="show the plan instead of applying")

    update = new_subparser(subparsers, "update", "Adopt the latest revision of profile sources and of golfo-kit.",
                           "  agent-ready update\n  agent-ready update acme --dry-run", command_update, needs_provider=True)
    update.add_argument("sources", nargs="*", metavar="source", help="sources to adopt (default: every declared source)")
    update.add_argument("-n", "--dry-run", action="store_true", help="show what would change instead of applying")

    config = new_subparser(subparsers, "config", "Read and write the layered configuration.",
                           "  agent-ready config explain\n  agent-ready config set ci.mode warn\n"
                           "  agent-ready config set updates.mode pinned --layer user", None, with_project=False)
    config_commands = config.add_subparsers(dest="config_command", metavar="<action>", required=True)
    explain = new_subparser(config_commands, "explain", "Effective value and the layer it comes from.",
                            "  agent-ready config explain\n  agent-ready config explain updates.mode --json", command_config_explain)
    explain.add_argument("key", nargs="?", help="one option (default: all of them)")
    explain.add_argument("--json", action="store_true", help="print it as JSON on stdout")
    get = new_subparser(config_commands, "get", "Print the effective value of one option.",
                        "  agent-ready config get ci.mode", command_config_get)
    get.add_argument("key", help="dotted option, e.g. ci.mode")
    get.add_argument("--json", action="store_true", help="print the value as JSON")
    for name, summary, handler in (
        ("set", "Write one option into a layer; it is validated before anything is written.", command_config_set),
        ("unset", "Remove one option from a layer, so the lower layers decide again.", command_config_unset),
    ):
        action = new_subparser(config_commands, name, summary, f"  agent-ready config {name} ci.mode{' warn' if name == 'set' else ''}", handler)
        action.add_argument("key", help="dotted option, e.g. ci.mode")
        if name == "set":
            action.add_argument("value", help="booleans: true|false; lists: a,b or JSON")
        action.add_argument("--layer", choices=WRITABLE_LAYERS, default=LAYER_PROJECT,
                            help="project (.agents/agent-ready.json, versioned) or user (this machine) (default: project)")
    return parser


def use_utf8_output():
    """Emit UTF-8 everywhere; Windows defaults to the locale code page."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")


def main(argv=None):
    """Entry point: exit 2 on usage errors, 130 on Ctrl+C, the delegated status otherwise."""
    use_utf8_output()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        arguments.project_root = find_repository_root(arguments.project)
        return arguments.handler(arguments)
    except UsageError as usage_error:
        fail(f"{usage_error}. Run {CLI_NAME} {arguments.command} --help")
        return EXIT_USAGE
    except ConfigurationError as configuration_error:
        fail(str(configuration_error))
        return EXIT_USAGE
    except StateError as state_error:
        fail(str(state_error))
        return EXIT_FAILED
    except KeyboardInterrupt:
        fail("cancelled")
        return EXIT_CANCELLED
