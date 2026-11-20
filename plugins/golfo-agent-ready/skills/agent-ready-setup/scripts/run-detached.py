#!/usr/bin/env python3
"""Run a command detached from the calling session, with a private log.

Internal helper for the SessionStart sync: the provider may end the hook's process
group when the hook returns, so background work runs in its own session. Bash has no
portable way to start a new session on macOS.

Usage: run-detached.py --log <file> -- <command> [arguments...]
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys

PRIVATE_FILE_MODE = 0o600


def run_detached(command, log_path):
    """Start command in a new session, writing its output to a private log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.is_symlink():
        raise OSError(f"refusing to write the background log through a symlink: {log_path}")
    log_descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE_MODE)
    with os.fdopen(log_descriptor, "w") as log_file:
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT,
                         start_new_session=True)


def main():
    """Parse the log path and command, then start the command detached."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    command = arguments.command[1:] if arguments.command[:1] == ["--"] else arguments.command
    if not command:
        parser.error("a command is required after --")
    try:
        run_detached(command, arguments.log)
    except OSError as error:
        print(f"Background task could not start: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
