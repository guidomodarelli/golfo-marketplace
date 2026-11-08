"""Shared plumbing of the agent-ready command line: exit statuses, errors and the engine calls.

Every subcommand module imports from here, so none of them repeats how to find the
repository, run a Bash script of the engine or apply a selection.
"""

import os
import subprocess
import sys

from agent_ready_common import bash_executable, plugin_version, serialize_json, write_text_atomically
from agent_ready_config import (
    LAYER_PROJECT,
    LAYER_USER,
    PROJECT_CONFIG_RELATIVE_PATH,
    describe_layer,
    load_schema,
    read_layer_file,
    resolve_configuration,
    user_config_path,
    validate_layer,
)
from agent_ready_options import SOURCES_ENABLED_KEY, SOURCES_PACKS_KEY
from agent_ready_packs import FULL_COMMIT, SOURCE_TYPE_GIT, parse_profile_sources

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
    if getattr(arguments, "recheck", False):
        merge_command.append("--recheck")
    merge_status = run_bash(merge_command, arguments.project_root, stdout=sys.stderr)
    if merge_status != EXIT_OK:
        fail(f"merge-instructions.sh failed with exit status {merge_status}; the assets were applied, AGENTS.md was not aligned")
        return EXIT_FAILED
    return EXIT_OK


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


def version_text():
    """golfo-kit version of this installation."""
    return f"{CLI_NAME} {plugin_version(SKILL_ROOT) or 'unknown version'}"


_ENGINE = None


def engine():
    """The agent-ready-state.py module of this installation, loaded once, to reuse its functions."""
    global _ENGINE
    if _ENGINE is None:
        import importlib.util

        specification = importlib.util.spec_from_file_location("agent_ready_state", STATE_SCRIPT)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        _ENGINE = module
    return _ENGINE


def write_project_selection(project_root, profiles):
    """Write the profiles of the manifest, validated, and nothing else."""
    path = os.path.join(project_root, PROJECT_CONFIG_RELATIVE_PATH)
    schema = load_schema()
    label = describe_layer(LAYER_PROJECT, path)
    document = read_layer_file(path, LAYER_PROJECT) or {}
    document["profiles"] = list(profiles)
    validate_layer(schema, document, LAYER_PROJECT, label)
    write_text_atomically(path, serialize_json(document))
    return path
