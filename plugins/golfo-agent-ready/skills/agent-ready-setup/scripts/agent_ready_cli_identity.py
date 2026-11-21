"""agent-ready identity show|set|link: who uses this machine for the learning and the sync (#169).

The identity is of the user of the operating system (agent_ready_identity.py): it needs no repository.
Inside one, show also prints the collaboration preset that applies to it.
"""

import subprocess
import sys

import agent_ready_identity as identity
from agent_ready_cli_common import EXIT_OK, engine
from agent_ready_common import serialize_json
from agent_ready_lockfile import read_lock

IDENTITY_COMMAND = "identity"


def repository_root(project):
    """The root of the Git repository at ``project``, or None outside one."""
    result = subprocess.run(["git", "-C", project, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                            check=False)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def preset_of(project_root):
    """The configured and effective collaboration preset of the repository, or None outside one."""
    if project_root is None:
        return None
    configured = engine().configuration_of(project_root).value(identity.COLLABORATION_PRESET_KEY)
    lock = read_lock(project_root) or {}
    return {"configured": configured, "effective": identity.collaboration_preset(configured, lock.get("profileOrder"))}


def print_identity(current, preset, as_json):
    if as_json:
        sys.stdout.write(serialize_json(dict(current, collaboration=preset)))
        return
    origin = ("set on this machine" if current["source"] == identity.SOURCE_FILE
              else "the default of this user of the system; set it with agent-ready identity set")
    sys.stdout.write(f"Identity: {current['id']} ({current['name']}), {origin}.\n")
    sys.stdout.write(f"  File: {identity.identity_path()}\n")
    if preset:
        how = "" if preset["configured"] != identity.PRESET_AUTO else ", chosen by the selection"
        sys.stdout.write(f"Collaboration: {preset['effective']}{how}.\n")


def command_identity_show(arguments):
    print_identity(identity.read_identity(), preset_of(repository_root(arguments.project)), arguments.json)
    return EXIT_OK


def command_identity_set(arguments):
    current = identity.write_identity(arguments.id, arguments.name)
    print_identity(current, None, arguments.json)
    return EXIT_OK


def command_identity_link(arguments):
    """Give this machine the id of the same person on another one; the name stays."""
    current = identity.write_identity(arguments.id, None)
    print_identity(current, None, arguments.json)
    return EXIT_OK


def register(subparsers, new_subparser):
    """Add identity show|set|link to the CLI parser."""
    command = new_subparser(subparsers, IDENTITY_COMMAND,
                            "Who uses this machine, for what is learned and synchronized.",
                            "  agent-ready identity show\n  agent-ready identity set --name \"Ana Pérez\" --id ana\n"
                            "  agent-ready identity link ana", None, with_project=False)
    actions = command.add_subparsers(dest="identity_action", metavar="<action>", required=True)
    show = new_subparser(actions, "show", "Print the identity of this user of the system and the collaboration "
                                          "preset of the repository.",
                         "  agent-ready identity show\n  agent-ready identity show --json", command_identity_show)
    set_action = new_subparser(actions, "set", "Store the id and the name of this user of the system.",
                               "  agent-ready identity set --name \"Ana Pérez\"\n  agent-ready identity set --id ana",
                               command_identity_set, with_project=False)
    set_action.add_argument("--id", help="lowercase id, the same on every machine of the person")
    set_action.add_argument("--name", help="name shown to the others")
    link = new_subparser(actions, "link", "Use on this machine the id that the same person has on another one.",
                         "  agent-ready identity link ana", command_identity_link, with_project=False)
    link.add_argument("id", help="the id that agent-ready identity show prints on the other machine")
    for action in (show, set_action, link):
        action.add_argument("--json", action="store_true", help="print the identity as JSON")
        action.set_defaults(needs_repository=False)
