"""Command line of agent-ready-setup: one subcommand per flow, over the engine of this installation.

It parses, resolves what is missing and delegates: ``bootstrap.sh`` projects and plans,
``agent-ready-state.py`` checks and reports, and ``agent_ready_config`` reads and writes the
configuration layers. It never reimplements their logic. Data goes to stdout; progress,
warnings and errors go to stderr. Only ``init`` (in ``agent_ready_cli_selection``) and ``remove``
(in ``agent_ready_cli_lifecycle``) ask, and only with a terminal; every other subcommand runs the
same with and without one.
"""

import argparse
import json
import subprocess
import sys

from agent_ready_cli_common import (
    CLI_NAME,
    EXIT_CANCELLED,
    EXIT_FAILED,
    EXIT_OK,
    EXIT_STATUS_HELP,
    EXIT_USAGE,
    PROVIDER_VARIABLE,
    SKILL_ROOT,
    STATE_SCRIPT,
    SUPPORTED_PROVIDERS,
    UPDATE_MODES,
    WRITABLE_LAYERS,
    UsageError,
    apply_selection,
    bootstrap_command,
    declared_sources,
    fail,
    find_repository_root,
    follows_a_ref,
    resolve_provider,
    run_bash,
    selection_arguments,
    update_source_arguments,
    version_text,
    write_layer,
)
from agent_ready_common import StateError, serialize_json
from agent_ready_config import LAYER_PROJECT, ConfigurationError, format_value, load_schema, parse_text_value
from agent_ready_options import SOURCES_ENABLED_KEY
from agent_ready_cli_lifecycle import register as register_lifecycle_commands
from agent_ready_cli_selection import register as register_selection_commands
from agent_ready_prompts import Cancelled

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
    register_selection_commands(subparsers, new_subparser)
    register_lifecycle_commands(subparsers, new_subparser)
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
        if getattr(arguments, "needs_repository", True):
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
    except (KeyboardInterrupt, Cancelled):
        fail("cancelled: nothing was changed")
        return EXIT_CANCELLED
