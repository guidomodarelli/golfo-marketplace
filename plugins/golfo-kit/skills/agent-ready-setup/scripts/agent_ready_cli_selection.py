"""Subcommands of agent-ready that choose what a repository uses: profiles, sources and init.

They edit the project layer (``.agents/agent-ready.json``) through the configuration engine,
validate every name against the effective catalog before writing, and leave the projection
to ``apply``. ``init`` is the only one that asks: with a terminal it asks what is missing,
and without one it needs its flags. Data goes to stdout; questions and progress to stderr.
"""

import os
import subprocess
import sys

from agent_ready_cli_common import (
    CLI_NAME,
    EXIT_OK,
    EXIT_SOURCE_UNAVAILABLE,
    SKILL_ROOT,
    STATE_SCRIPT,
    UPDATE_MODES,
    UsageError,
    apply_selection,
    engine,
    fail,
    resolve_provider,
    write_layer,
    write_project_selection,
)
from agent_ready_common import ProfileError, StateError, serialize_json, write_text_atomically
from agent_ready_config import LAYER_PROJECT, PROJECT_CONFIG_RELATIVE_PATH
from agent_ready_options import (
    DETECTION_ENABLED_KEY,
    PROFILES_KEY,
    SOURCES_ENABLED_KEY,
    UPDATES_MODE_KEY,
)
from agent_ready_packs import NAMESPACE_SEPARATOR, parse_profile_sources
from agent_ready_prompts import ask_confirmation, ask_text, can_prompt, equivalent_command

GOLFO_SOURCE_LABEL = "golfo-kit"


def selected_profiles(project_root):
    """Profiles the manifest selects, or an empty list when it selects none."""
    return engine().configuration_of(project_root).value(PROFILES_KEY) or []


def validate_selection(catalog, names):
    """Why a selection cannot be applied, or None: the engine's own resolution decides."""
    if not names:
        return "select at least one profile"
    try:
        engine().resolve_profiles(catalog, names)
    except ProfileError as profile_error:
        return str(profile_error)
    return None


def profile_names(text):
    """Comma separated profiles, in order and without repeats."""
    return engine().split_profile_names(text)


# ---------------------------------------------------------------------------
# profiles list|add|remove
# ---------------------------------------------------------------------------

def command_profiles_list(arguments):
    """Every profile the repository can select, with its kind, source and whether it is selected."""
    catalog = engine().load_effective_catalog(arguments.project_root, SKILL_ROOT)
    selected = set(selected_profiles(arguments.project_root))
    rows = []
    for name, profile in sorted(catalog["profiles"].items()):
        source = name.split(NAMESPACE_SEPARATOR, 1)[0] if NAMESPACE_SEPARATOR in name else GOLFO_SOURCE_LABEL
        rows.append({"name": name, "kind": profile.get("kind"), "source": source,
                     "selected": name in selected, "description": profile.get("description", "")})
    if arguments.json:
        sys.stdout.write(serialize_json(rows))
        return EXIT_OK
    width = max(len(row["name"]) for row in rows)
    for row in rows:
        marker = "*" if row["selected"] else " "
        sys.stdout.write(f"{marker} {row['name']:<{width}}  {row['kind']:<10}  {row['source']:<10}  {row['description']}\n")
    unavailable = [name for name, source in catalog.get("sources", {}).items() if source["state"] != "available"]
    if unavailable:
        sys.stderr.write(f"Not in the cache yet, so their profiles are missing: {', '.join(unavailable)}. "
                         f"Run {CLI_NAME} sources list for the reason.\n")
    return EXIT_OK


def change_selection(arguments, compute):
    """Validate the new selection against the catalog and write it; the projection is apply's job."""
    current = selected_profiles(arguments.project_root)
    if not current:
        raise UsageError(f"this repository has no selection yet; start it with {CLI_NAME} init")
    catalog = engine().load_effective_catalog(arguments.project_root, SKILL_ROOT)
    selection = compute(current)
    error = validate_selection(catalog, selection)
    if error:
        raise UsageError(error)
    path = write_project_selection(arguments.project_root, selection)
    sys.stderr.write(f"Profiles in {path}: {', '.join(selection)}. Run {CLI_NAME} apply to project them "
                     f"({CLI_NAME} apply --dry-run shows what would change).\n")
    return EXIT_OK


def command_profiles_add(arguments):
    """Add profiles to the selection of the manifest."""
    return change_selection(arguments, lambda current: current + [name for name in arguments.names if name not in current])


def command_profiles_remove(arguments):
    """Remove profiles from the selection of the manifest."""
    current = selected_profiles(arguments.project_root)
    missing = [name for name in arguments.names if name not in current]
    if missing:
        raise UsageError(f"not selected: {', '.join(missing)}; the selection is {', '.join(current) or 'empty'}")
    return change_selection(arguments, lambda selection: [name for name in selection if name not in arguments.names])


# ---------------------------------------------------------------------------
# sources list|add|remove
# ---------------------------------------------------------------------------

def command_sources_list(arguments):
    """Declared profile sources and whether this machine has them."""
    configuration = engine().configuration_of(arguments.project_root)
    catalog = engine().load_effective_catalog(arguments.project_root, SKILL_ROOT)
    rows = []
    for name, source in sorted(catalog.get("sources", {}).items()):
        rows.append({"name": name, "type": source["type"], "origin": source["origin"],
                     "requestedRef": source.get("requestedRef"), "updates": source.get("updates"),
                     "state": source["state"], "reason": source.get("reason"),
                     "profiles": source.get("availableProfiles", [])})
    if arguments.json:
        sys.stdout.write(serialize_json({"enabled": configuration.value(SOURCES_ENABLED_KEY), "sources": rows}))
        return EXIT_OK
    if not configuration.value(SOURCES_ENABLED_KEY):
        sys.stderr.write(f"Profile sources are off ({SOURCES_ENABLED_KEY}: {configuration.origin(SOURCES_ENABLED_KEY)}).\n")
    for row in rows:
        revision = f"@{row['requestedRef']}" if row["requestedRef"] else ""
        detail = f"{len(row['profiles'])} profile(s)" if row["state"] == "available" else row["reason"]
        sys.stdout.write(f"{row['name']}  {row['type']}  {row['origin']}{revision}  {row['updates']}  {row['state']}: {detail}\n")
    return EXIT_OK


def command_sources_add(arguments):
    """Declare a profile source in the manifest and bring it into the user cache."""
    entry = {"name": arguments.name, "source": arguments.source}
    if arguments.ref:
        entry["ref"] = arguments.ref
    if arguments.updates:
        entry["updates"] = arguments.updates
    arguments.layer = LAYER_PROJECT

    def change(schema, document):
        packs = document.setdefault("sources", {}).setdefault("packs", [])
        if any(existing.get("name") == arguments.name for existing in packs):
            raise UsageError(f"the manifest already declares the source '{arguments.name}'; remove it first")
        packs.append(entry)
        try:
            parse_profile_sources(packs, "the manifest")
        except StateError as invalid_source:
            raise UsageError(str(invalid_source)) from invalid_source
        return True

    manifest_path = os.path.join(arguments.project_root, PROJECT_CONFIG_RELATIVE_PATH)
    previous = open(manifest_path, encoding="utf-8").read() if os.path.isfile(manifest_path) else None
    path, _ = write_layer(arguments, change)
    if not arguments.offline:
        # The same strict download an apply runs: a missing path or an unreachable repository fails here.
        command = [sys.executable, STATE_SCRIPT, "fetch-sources", "--project", arguments.project_root, "--skill-dir", SKILL_ROOT]
        if subprocess.call(command, cwd=arguments.project_root, stdout=sys.stderr) != EXIT_OK:
            if previous is None:
                os.unlink(manifest_path)
            else:
                write_text_atomically(manifest_path, previous)
            fail(f"could not bring the source '{arguments.name}' into the cache; the manifest was left as it was")
            return EXIT_SOURCE_UNAVAILABLE
    sys.stderr.write(f"Source '{arguments.name}' declared in {path}. Its profiles are selected with "
                     f"{CLI_NAME} profiles add {arguments.name}/<profile>.\n")
    return EXIT_OK


def required_closure(catalog, name):
    """A profile and every profile it requires, transitively, as far as the catalog knows them."""
    closure, pending = [], [name]
    while pending:
        current = pending.pop()
        if current in closure:
            continue
        closure.append(current)
        pending.extend(catalog["profiles"].get(current, {}).get("requires", []))
    return closure


def command_sources_remove(arguments):
    """Remove a profile source from the manifest, unless selected profiles still come from it."""
    prefix = f"{arguments.name}{NAMESPACE_SEPARATOR}"
    selection = selected_profiles(arguments.project_root)
    catalog = engine().load_effective_catalog(arguments.project_root, SKILL_ROOT)
    # A profile counts when it comes from the source or requires one that does, through any pack.
    closures = {name: required_closure(catalog, name) for name in selection}
    using = sorted({member for closure in closures.values() for member in closure if member.startswith(prefix)})
    culprits = [name for name, closure in closures.items() if any(member.startswith(prefix) for member in closure)]
    if using:
        raise UsageError(f"the selection still uses {', '.join(using)}; remove what brings them in first with "
                         f"{CLI_NAME} profiles remove {' '.join(culprits)}")
    arguments.layer = LAYER_PROJECT

    def change(schema, document):
        packs = document.get("sources", {}).get("packs", [])
        remaining = [entry for entry in packs if entry.get("name") != arguments.name]
        if len(remaining) == len(packs):
            raise UsageError(f"the manifest does not declare the source '{arguments.name}'")
        document["sources"]["packs"] = remaining
        if not remaining:
            del document["sources"]["packs"]
            if not document["sources"]:
                del document["sources"]
        return True

    path, _ = write_layer(arguments, change)
    sys.stderr.write(f"Source '{arguments.name}' removed from {path}.\n")
    return EXIT_OK


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def detected_defaults(catalog, project_root):
    """Profiles the detection proposes, and the capabilities it suggests on top."""
    if not engine().configuration_of(project_root).value(DETECTION_ENABLED_KEY):
        return [], []
    detection = engine().detect_profiles(catalog["profiles"], project_root)
    try:
        stack = engine().stack_from_initial_detection(catalog, detection)
    except ProfileError:
        return [], []
    defaults = engine().profiles_for_stack(catalog, stack)
    suggestions = [item["profile"] for item in engine().capability_suggestions(catalog, detection, defaults)]
    return defaults, suggestions


def command_init(arguments):
    """First setup of a repository: choose the profiles, write the manifest and apply."""
    if selected_profiles(arguments.project_root):
        raise UsageError(f"this repository is already set up; change it with {CLI_NAME} profiles add|remove "
                         f"and {CLI_NAME} apply")
    provider = resolve_provider(arguments.provider)
    catalog = engine().load_effective_catalog(arguments.project_root, SKILL_ROOT)
    if arguments.stack:
        try:
            arguments.profiles = ",".join(engine().profiles_for_stack(catalog, arguments.stack))
        except ProfileError as profile_error:
            raise UsageError(str(profile_error)) from profile_error
    if arguments.profiles:
        error = validate_selection(catalog, profile_names(arguments.profiles))
        if error:
            raise UsageError(f"--profiles: {error}")

    missing = []
    if not arguments.profiles:
        missing.append("--profiles <a,b> (or --stack <s>)")
    if not arguments.yes:
        missing.append("--yes")
    asked = False
    if missing and not can_prompt(arguments.no_input):
        raise UsageError(f"missing {' and '.join(missing)}; there is no terminal to ask")

    defaults, suggestions = detected_defaults(catalog, arguments.project_root)
    updates = arguments.updates
    full_wizard = not arguments.profiles and not arguments.updates
    if not arguments.profiles:
        if suggestions:
            sys.stderr.write(f"Detected capabilities you may add: {', '.join(suggestions)}\n")
        stacks = ", ".join(engine().stack_names_of(catalog))
        sys.stderr.write(f"Stacks: {stacks}. Capabilities and packs: {CLI_NAME} profiles list\n")
        arguments.profiles = ask_text(
            "Profiles (comma separated)", ",".join(defaults),
            lambda answer: validate_selection(catalog, profile_names(answer)),
        )
        asked = True
    if full_wizard:
        current_mode = engine().configuration_of(arguments.project_root).value(UPDATES_MODE_KEY)
        updates = ask_text(f"Updates ({'|'.join(UPDATE_MODES)})", current_mode,
                           lambda answer: None if answer in UPDATE_MODES else f"answer one of {', '.join(UPDATE_MODES)}")
        asked = True
    profiles = ",".join(profile_names(arguments.profiles))
    if not arguments.yes:
        if not ask_confirmation(f"Apply {profiles} now? Managed assets are overwritten with the templates", True):
            sys.stderr.write("Nothing was changed.\n")
            return EXIT_OK
        asked = True
    if asked:
        command = [CLI_NAME, "init", "--profiles", profiles] + (["--updates", updates] if updates else [])
        command += (["--project", arguments.project] if arguments.project != "." else []) + ["--provider", provider, "--yes"]
        sys.stderr.write(f"Equivalent command: {equivalent_command(command)}\n")
    extra = ["--profiles", profiles] + (["--updates", updates] if updates else [])
    return apply_selection(arguments, provider, extra)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def register(subparsers, new_subparser):
    """Add profiles, sources and init to the parser of the CLI."""
    profiles = new_subparser(subparsers, "profiles", "List and change the profiles the repository selects.",
                             "  agent-ready profiles list\n  agent-ready profiles add business-flows", None, with_project=False)
    profile_actions = profiles.add_subparsers(dest="profiles_command", metavar="<action>", required=True)
    listing = new_subparser(profile_actions, "list", "Every profile available, with * on the selected ones.",
                            "  agent-ready profiles list --json", command_profiles_list)
    listing.add_argument("--json", action="store_true", help="print the list as JSON on stdout")
    for name, summary, handler in (("add", "Add profiles to the selection of the manifest.", command_profiles_add),
                                   ("remove", "Remove profiles from the selection of the manifest.", command_profiles_remove)):
        action = new_subparser(profile_actions, name, summary, f"  agent-ready profiles {name} business-flows", handler)
        action.add_argument("names", nargs="+", metavar="profile", help="profile names, e.g. browser or acme/kafka-interno")

    sources = new_subparser(subparsers, "sources", "List and change the profile sources (packs) of the repository.",
                            "  agent-ready sources list\n"
                            "  agent-ready sources add acme git+https://github.com/acme/agent-profiles --ref main",
                            None, with_project=False)
    source_actions = sources.add_subparsers(dest="sources_command", metavar="<action>", required=True)
    source_listing = new_subparser(source_actions, "list", "Declared sources and whether this machine has them.",
                                   "  agent-ready sources list --json", command_sources_list)
    source_listing.add_argument("--json", action="store_true", help="print the list as JSON on stdout")
    add = new_subparser(source_actions, "add", "Declare a source in the manifest and bring it into the user cache.",
                        "  agent-ready sources add local path:./agent-packs/local", command_sources_add)
    add.add_argument("name", help="namespace of its profiles, in kebab-case")
    add.add_argument("source", help="git+https://..., git+ssh://... or path:<relative path>")
    add.add_argument("--ref", help="branch or tag to follow, when the URL has no #<revision>")
    add.add_argument("--updates", choices=UPDATE_MODES, help="update mode of this source (default: updates.mode)")
    add.add_argument("--offline", action="store_true", help="only declare it; download it on the next apply")
    remove = new_subparser(source_actions, "remove", "Remove a source from the manifest.",
                           "  agent-ready sources remove acme", command_sources_remove)
    remove.add_argument("name", help="the source to remove")

    init = new_subparser(subparsers, "init", "First setup of a repository: choose the profiles, write the manifest and apply.",
                         "  agent-ready init\n  agent-ready init --profiles node,browser --yes", command_init, needs_provider=True)
    group = init.add_mutually_exclusive_group()
    group.add_argument("--profiles", help="comma separated profiles (asked with a terminal; default: the detected stack)")
    group.add_argument("--stack", help="a stack and its default profiles, e.g. frontend")
    init.add_argument("--updates", choices=UPDATE_MODES, help=f"write {UPDATES_MODE_KEY} into the manifest (default: auto)")
    init.add_argument("-y", "--yes", action="store_true", help="apply without asking for confirmation")
    init.add_argument("--no-input", action="store_true", help="never ask; fail with exit 2 naming the missing flags")
