"""agent-ready trust: the sources whose tools may run on this machine, and the repositories whose
manifest may loosen security.

Both approvals live in the user configuration of this machine (security.trustedSources and
security.trustedProjects), never in the repository, so a pull request cannot approve itself.
Trusting a source does not run anything by itself: its tools still go through the rest of the
security policy (agent_ready_pack_tools.py).
"""

import subprocess
import sys

import agent_ready_pack_tools as pack_tools
from agent_ready_cli_common import (
    CLI_NAME,
    EXIT_OK,
    STATE_SCRIPT,
    UsageError,
    declared_sources,
    engine,
    write_layer,
)
from agent_ready_common import StateError, serialize_json
from agent_ready_config import LAYER_USER

TRUSTED_SOURCES_FIELD = "trustedSources"
SECURITY_FIELD = "security"


def declaration_of(project_root, name):
    """The declaration of a source of the manifest, or a usage error that lists them."""
    declarations = declared_sources(project_root) or []
    for declaration in declarations:
        if declaration["name"] == name:
            return declaration
    known = ", ".join(declaration["name"] for declaration in declarations) or "none"
    raise UsageError(f"unknown profile source '{name}'; the manifest declares: {known}")


def trusted_origin(declaration):
    """The origin a source is trusted by; a path source lives in the repository, so the repository is approved instead."""
    if declaration["type"] == pack_tools.SOURCE_TYPE_PATH:
        raise UsageError(f"'{declaration['name']}' is a path source inside this repository; approve the repository "
                         f"with {CLI_NAME} trust add --project .")
    return declaration["origin"]


def change_trusted_sources(arguments, origins, adding):
    """Add or remove origins in security.trustedSources of the user layer; returns (path, changed)."""
    arguments.layer = LAYER_USER
    wanted = {pack_tools.normalized_origin(origin) for origin in origins}

    def change(schema, document):
        security = document.setdefault(SECURITY_FIELD, {})
        current = security.get(TRUSTED_SOURCES_FIELD, [])
        known = {pack_tools.normalized_origin(origin) for origin in current}
        if adding:
            updated = current + [origin for origin in origins if pack_tools.normalized_origin(origin) not in known]
        else:
            updated = [origin for origin in current if pack_tools.normalized_origin(origin) not in wanted]
        if updated:
            security[TRUSTED_SOURCES_FIELD] = updated
        else:
            security.pop(TRUSTED_SOURCES_FIELD, None)
        if not security:
            document.pop(SECURITY_FIELD)
        return updated != current

    return write_layer(arguments, change)


def trust_sources(arguments, names, adding):
    """Trust or stop trusting the named sources on this machine."""
    origins = [trusted_origin(declaration_of(arguments.project_root, name)) for name in names]
    path, changed = change_trusted_sources(arguments, origins, adding)
    for name, origin in zip(names, origins):
        if adding:
            sys.stderr.write(f"Trusted on this machine: {name} ({origin}). Its tools still go through the security "
                             f"policy; {CLI_NAME} plan shows what it allows ({path}).\n")
        else:
            sys.stderr.write(f"No longer trusted on this machine: {name} ({origin}) ({path}).\n")
    if not changed:
        sys.stderr.write("Nothing changed: it already was that way.\n")


def approve_repository(arguments, revoke):
    """The approval of this repository, through agent-ready-state.py trust, the same as the hooks read."""
    command = [sys.executable, STATE_SCRIPT, "trust", "--project", arguments.project_root] + (["--revoke"] if revoke else [])
    completed = subprocess.run(command, cwd=arguments.project_root, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    sys.stderr.write(completed.stdout + completed.stderr)
    if completed.returncode != 0:
        raise StateError(f"could not change the approval of {arguments.project_root}")


def command_trust_add(arguments):
    """Trust sources on this machine, or, without sources, approve this repository."""
    if arguments.sources:
        trust_sources(arguments, arguments.sources, adding=True)
    else:
        approve_repository(arguments, revoke=False)
    return EXIT_OK


def command_trust_remove(arguments):
    """Stop trusting sources on this machine, or, without sources, revoke the approval of this repository."""
    if arguments.sources:
        trust_sources(arguments, arguments.sources, adding=False)
    else:
        approve_repository(arguments, revoke=True)
    return EXIT_OK


def command_trust_list(arguments):
    """Whether this repository is approved and which of its sources this machine trusts."""
    configuration = engine().configuration_of(arguments.project_root)
    policy = {pack_tools.TRUSTED_SOURCES_KEY: configuration.value(pack_tools.TRUSTED_SOURCES_KEY)}
    sources = [{"name": declaration["name"], "type": declaration["type"], "origin": declaration["origin"],
                "trusted": pack_tools.source_is_trusted(declaration, policy, configuration.project_approved)}
               for declaration in declared_sources(arguments.project_root) or []]
    report = {
        "repository": {"root": arguments.project_root, "approved": configuration.project_approved},
        "sources": sources,
        "trustedSources": {"value": policy[pack_tools.TRUSTED_SOURCES_KEY],
                           "origin": configuration.origin(pack_tools.TRUSTED_SOURCES_KEY)},
    }
    if arguments.json:
        sys.stdout.write(serialize_json(report))
        return EXIT_OK
    state = "approved" if configuration.project_approved else "not approved"
    sys.stdout.write(f"This repository: {state} on this machine ({arguments.project_root})\n")
    if not sources:
        sys.stdout.write("The manifest declares no profile source.\n")
    for source in sources:
        label = "trusted" if source["trusted"] else "not trusted"
        sys.stdout.write(f"{source['name']}  {label:<11}  {source['type']}  {source['origin']}\n")
    return EXIT_OK


def register(subparsers, new_subparser):
    """Add trust list|add|remove to the CLI parser."""
    trust = new_subparser(subparsers, "trust", "Trust a source or approve this repository, on this machine only.",
                          "  agent-ready trust list\n  agent-ready trust add acme\n  agent-ready trust add --project .",
                          None, with_project=False)
    actions = trust.add_subparsers(dest="trust_action", metavar="<action>", required=True)
    listing = new_subparser(actions, "list", "Whether this repository is approved and which sources this machine trusts.",
                            "  agent-ready trust list\n  agent-ready trust list --json", command_trust_list)
    listing.add_argument("--json", action="store_true", help="print it as JSON on stdout")
    for name, summary, handler in (
        ("add", "Trust sources on this machine; without sources, approve the repository of --project.", command_trust_add),
        ("remove", "Stop trusting sources; without sources, revoke the approval of the repository.", command_trust_remove),
    ):
        action = new_subparser(actions, name, summary,
                               f"  agent-ready trust {name} acme\n  agent-ready trust {name} --project .", handler)
        action.add_argument("sources", nargs="*", metavar="source",
                            help="profile sources of the manifest (default: the repository itself)")
