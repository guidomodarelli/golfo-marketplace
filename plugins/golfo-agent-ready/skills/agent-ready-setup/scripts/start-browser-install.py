#!/usr/bin/env python3
"""Start the full browser tools installation in the background without blocking the session.

SessionStart sync runs it when no usable installation exists. The detached
setup-browser-tools.py run installs packages, downloads Chromium and registers the
project, so the tools become available in the next session. Attempts are limited
to one per retry interval, so offline machines do not retry on every session.
"""

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import time

# Shared logic loads from this script's own directory so every script stays on one version.
BROWSER_SETUP_PATH = Path(__file__).resolve().with_name("setup-browser-tools.py")
RUN_DETACHED_PATH = Path(__file__).resolve().with_name("run-detached.py")
CACHE_DIRECTORY_NAME = "agent-ready-setup"
ATTEMPT_STAMP_NAME = "browser-install-attempt.stamp"
INSTALL_LOG_NAME = "browser-install.log"
# Serializes the stamp check and the launch, so concurrent sessions start a single install.
LAUNCH_LOCK_NAME = "browser-install-launch.lock"
RETRY_INTERVAL_SECONDS = 24 * 60 * 60


def load_module(name, path):
    """Load a sibling script as a module; hyphenated file names are not importable directly."""
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def load_browser_setup():
    """Load the shared browser setup module."""
    return load_module("browser_setup", BROWSER_SETUP_PATH)


def cache_directory():
    """Keep attempt state and logs outside the project, per user."""
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / CACHE_DIRECTORY_NAME


def attempted_recently(stamp):
    """Report whether a previous attempt started within the retry interval."""
    return stamp.is_file() and time.time() - stamp.stat().st_mtime < RETRY_INTERVAL_SECONDS


def start_install(browser_setup, project):
    """Launch the detached installation unless it is unnecessary, running, or recently attempted."""
    if browser_setup.read_installation() is not None and browser_setup.is_toml_editor_available():
        return "Browser install skipped: tools are already installed."
    stamp = cache_directory() / ATTEMPT_STAMP_NAME
    log_path = cache_directory() / INSTALL_LOG_NAME
    browser_setup.ensure_safe_path(stamp)
    browser_setup.ensure_safe_path(log_path)
    try:
        with browser_setup.exclusive_lock(cache_directory() / LAUNCH_LOCK_NAME, "busy"):
            return launch_unless_attempted(browser_setup, project, stamp, log_path)
    except RuntimeError:
        return "Browser install skipped: another session is starting the browser setup."


def launch_unless_attempted(browser_setup, project, stamp, log_path):
    """Check, stamp and launch the attempt; the caller holds the launch lock."""
    if attempted_recently(stamp):
        return (f"Browser install skipped: last attempt started less than 24 hours ago and retries automatically "
                f"after that; see {log_path}.")
    try:
        with browser_setup.exclusive_lock(browser_setup.tools_root() / browser_setup.INSTALL_LOCK_NAME, "busy"):
            pass
    except RuntimeError:
        return "Browser install skipped: another browser setup is already running."
    if not shutil.which("node") or not shutil.which("npm"):
        return "Browser install skipped: requires Node.js 24+ and npm; the next session installs the browser tools once they exist."
    # Stamp only real launches, so installing Node.js unblocks the very next session.
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.touch()
    load_module("run_detached", RUN_DETACHED_PATH).run_detached(
        [sys.executable, str(BROWSER_SETUP_PATH), "--project", str(project)], log_path)
    return (f"Browser tools are installing in the background (log: {log_path}); "
            "they will be available in the next session.")


def main():
    """Start the background installation for the given project."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    browser_setup = load_browser_setup()
    try:
        message = start_install(browser_setup, arguments.project.absolute())
    except OSError as error:
        print(f"Browser install could not start: {error}", file=sys.stderr)
        return 1
    print(message, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
