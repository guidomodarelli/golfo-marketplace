"""agent-ready tool run: start a CLI that a profile installed in the cache, for the MCP server that runs it.

A profile declares an MCP server with ``cli`` (agent_ready_pack_tools.py), and the apply registers it as
``agent-ready tool run <cli> -- <args>``. The registration lives in the repository and is the same on
every machine; this command finds the install that this repository uses on this machine
(agent_ready_pack_clis.installed_executable) and, when there is none, the CLI on the PATH. It passes
on the standard streams untouched, since an MCP server speaks over them, and exits with the status
of the CLI.
"""

import argparse
import shutil
import subprocess

import agent_ready_pack_clis as pack_clis
from agent_ready_cli_common import EXIT_FAILED, fail
from agent_ready_pack_tools import LAUNCHER_SEPARATOR

TOOL_COMMAND = "tool"


def resolve_executable(project_root, name):
    """The installed CLI of this repository, else the one on the PATH, or None."""
    return pack_clis.installed_executable(project_root, name) or shutil.which(name)


def command_tool_run(arguments):
    executable = resolve_executable(arguments.project_root, arguments.cli)
    if not executable:
        fail(f"{arguments.cli} is not installed for this repository and is not on the PATH: run agent-ready apply in "
             f"{arguments.project_root}, or check agent-ready status for why the policy blocks it")
        return EXIT_FAILED
    passed = list(arguments.arguments)
    if passed[:1] == [LAUNCHER_SEPARATOR]:
        passed = passed[1:]
    try:
        return subprocess.call([executable, *passed])
    except OSError as start_error:
        fail(f"could not start {arguments.cli} ({executable}): {start_error}")
        return EXIT_FAILED


def register(subparsers, new_subparser):
    """Add tool run to the CLI parser."""
    tool = new_subparser(subparsers, TOOL_COMMAND, "Run a CLI that a profile installed for this repository.",
                         "  agent-ready tool run engram -- mcp", None, with_project=False)
    actions = tool.add_subparsers(dest="tool_action", metavar="<action>", required=True)
    run = new_subparser(actions, "run", "Run a CLI of the profiles, from the cache of this machine or the PATH, "
                                        "with the standard streams of this process.",
                        "  agent-ready tool run engram -- mcp\n  agent-ready tool run engram --project ~/acme -- mcp",
                        command_tool_run)
    run.add_argument("cli", help="name of the CLI, as the profile declares it")
    run.add_argument("arguments", nargs=argparse.REMAINDER, help="arguments for the CLI, after --")
