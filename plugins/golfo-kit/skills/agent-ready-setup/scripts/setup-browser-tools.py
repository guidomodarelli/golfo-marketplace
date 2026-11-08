#!/usr/bin/env python3
"""Install pinned browser tools and register portable project MCP servers."""

import argparse
import contextlib
import importlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

# Windows Python has no fcntl; msvcrt byte-range locks give the same fail-fast exclusive lock.
try:
    import fcntl
except ImportError:
    fcntl = None
    import msvcrt

try:
    import tomllib
except ImportError:
    print("Browser setup requires Python 3.11+; assets remain installed.", file=sys.stderr)
    sys.exit(1)

COMMAND_TIMEOUT_SECONDS = 600
SERVER_ALIASES = {
    "chrome-devtools": {"chrome-devtools", "chrome_devtools", "chrome-devtools-mcp"},
    "playwright": {"playwright", "playwright-mcp"},
    "agent-browser": {"agent-browser", "agent_browser"},
}
# Version-independent link to the active install, so registrations survive version bumps.
CURRENT_INSTALL_LINK = "current"
# Commands under this fragment were registered by this setup and may be refreshed or removed.
MANAGED_COMMAND_FRAGMENT = "/agent-ready-setup/browser-tools/"
BROWSER_METADATA_PATH = ".agents/browser-tools.json"
# Same path as agent-ready-state.py: `agent-ready remove` deletes it last.
AGENT_READY_LOCK_PATH = ".agents/agent-ready.lock.json"
# Fixed per-user install location; project registrations reach it through $HOME.
TOOLS_HOME_RELATIVE_PATH = Path(".local/share/agent-ready-setup/browser-tools")
# Generated launchers keep machine-specific paths out of project configuration.
LAUNCHER_DIRECTORY = "bin"
INSTALL_LOCK_NAME = ".install.lock"
# Records the installation behind the current launchers so session sync can register without installing.
INSTALLATION_METADATA_NAME = "installation.json"
SERVER_FIELDS = ("command", "args", "env")
REQUIRED_EXECUTABLES = ("chrome-devtools-mcp", "playwright-mcp", "agent-browser", "playwright")
# Tells the sync hook that no usable or adoptable installation exists, so a full install is needed.
NO_INSTALLATION_EXIT_CODE = 3


def user_home():
    """Return HOME when set, like the shell scripts; Windows Python otherwise uses USERPROFILE."""
    home = os.environ.get("HOME")
    return Path(home) if home else Path.home()


def tools_root():
    """Return the per-user browser-tools directory for the current HOME."""
    return user_home() / TOOLS_HOME_RELATIVE_PATH


def ensure_safe_path(path):
    """Reject symlinked destinations and parents before filesystem writes."""
    for candidate in (path, *path.parents):
        if candidate.is_symlink():
            raise RuntimeError(f"Browser setup preserved symlinked path: {candidate}")


def read_config(path, parser, protect_destination=True):
    """Read existing user configuration without exposing its contents."""
    if not path.exists():
        return "", {}
    if protect_destination:
        ensure_safe_path(path)
    original = path.read_text()
    try:
        parsed = parser(original)
    except (ValueError, TypeError) as error:
        raise RuntimeError(f"Browser setup preserved malformed configuration: {path}") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Browser setup requires object configuration: {path}")
    return original, parsed


def atomic_write(path, content, original=None):
    """Replace a regular destination after checking the original snapshot."""
    ensure_safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if original is not None:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current != original:
            raise RuntimeError(f"Browser setup preserved concurrent changes: {path}")
        if current == content:
            return
    # Explicit LF and UTF-8: Windows text mode would write CRLF in the locale encoding.
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False,
                                     encoding="utf-8", newline="\n") as staged:
        staged.write(content)
        staged_path = Path(staged.name)
    try:
        os.chmod(staged_path, path.stat().st_mode & 0o777 if path.exists() else 0o600)
        ensure_safe_path(path)
        if original is not None and (path.read_text(encoding="utf-8") if path.exists() else "") != original:
            raise RuntimeError(f"Browser setup preserved concurrent changes: {path}")
        os.replace(staged_path, path)
    finally:
        staged_path.unlink(missing_ok=True)


def run_command(arguments, operation, capture=False):
    """Run a bounded external operation without shell interpolation or raw logs."""
    print(f"Browser setup: {operation}", file=sys.stderr)
    with tempfile.NamedTemporaryFile(mode="w+", prefix="agent-ready-browser-", suffix=".log", delete=False) as diagnostic:
        log_path = Path(diagnostic.name)
        try:
            process = subprocess.Popen(
                arguments, stdout=subprocess.PIPE if capture else diagnostic,
                stderr=diagnostic, text=True, start_new_session=True,
            )
            stdout, _ = process.communicate(timeout=COMMAND_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
            raise RuntimeError(f"Browser setup {operation} timed out; diagnostic: {log_path}; rerun bootstrap to resume") from error
        except OSError as error:
            log_path.unlink(missing_ok=True)
            raise RuntimeError(f"Browser setup could not start {operation}: {error.strerror}") from error
    if process.returncode:
        raise RuntimeError(f"Browser setup {operation} failed (exit {process.returncode}); diagnostic: {log_path}; rerun bootstrap to resume")
    log_path.unlink(missing_ok=True)
    return stdout.strip() if capture else ""


def load_pinned_versions():
    """Read the pinned browser package versions shipped with this skill."""
    return json.loads(Path(__file__).with_name("browser-tools.json").read_text())


def pinned_install_prefix(install_root, versions):
    """Return the version-specific directory that holds one pinned installation."""
    prefix = install_root / "-".join(versions.values())
    ensure_safe_path(prefix)
    return prefix


def is_pinned_install_complete(prefix, versions):
    """Check that every pinned package and executable is already installed."""
    for package, version in versions.items():
        manifest = prefix / "node_modules" / package / "package.json"
        if not manifest.is_file() or json.loads(manifest.read_text()).get("version") != version:
            return False
    return all(os.access(prefix / "node_modules/.bin" / name, os.X_OK) for name in REQUIRED_EXECUTABLES)


def locate_chromium(prefix):
    """Ask the installed Playwright where its Chromium lives; never downloads it."""
    browser_query = (
        "const {createRequire}=require('node:module');"
        "const load=createRequire(process.argv[1]);"
        "process.stdout.write(load('playwright').chromium.executablePath());"
    )
    return Path(run_command([
        "node", "-e", browser_query, str(prefix / "node_modules/@playwright/mcp/package.json"),
    ], "locate Chromium", capture=True))


def install_tools(install_root, versions):
    """Reuse pinned packages and download Chromium only when absent."""
    if not shutil.which("node") or not shutil.which("npm"):
        raise RuntimeError("Browser setup requires Node.js 24+ and npm; assets remain installed")
    node_version = run_command(["node", "--version"], "check Node.js", capture=True)
    if int(node_version.lstrip("v").split(".")[0]) < 24:
        raise RuntimeError("Browser setup requires Node.js 24+; Node.js was not upgraded")
    prefix = pinned_install_prefix(install_root, versions)
    binaries = prefix / "node_modules/.bin"
    if not is_pinned_install_complete(prefix, versions):
        run_command([
            "npm", "install", "--prefix", str(prefix), "--no-save", "--no-package-lock",
            "--no-audit", "--no-fund", *[f"{package}@{version}" for package, version in versions.items()],
        ], "install pinned browser packages")
    for executable in REQUIRED_EXECUTABLES:
        if not os.access(binaries / executable, os.X_OK):
            raise RuntimeError(f"Browser setup missing installed executable: {executable}")
    browser = locate_chromium(prefix)
    if not browser.is_file() or not os.access(browser, os.X_OK):
        run_command([str(binaries / "playwright"), "install", "chromium"], "download Chromium")
    if not browser.is_file() or not os.access(browser, os.X_OK):
        raise RuntimeError("Browser setup downloaded Chromium but executable remains unavailable")
    launch_probe = (
        "const {createRequire}=require('node:module');"
        "const load=createRequire(process.argv[1]);"
        "load('playwright').chromium.launch({headless:true,executablePath:process.argv[2]})"
        ".then(browser=>browser.close()).catch(error=>{console.error(error);process.exit(1)});"
    )
    run_command(["node", "-e", launch_probe, str(prefix / "node_modules/@playwright/mcp/package.json"), str(browser)],
                "verify headless Chromium launch")
    return point_current_install(install_root, prefix) / "node_modules/.bin", browser


def point_current_install(install_root, prefix):
    """Atomically repoint the version-independent link to the verified install."""
    current = install_root / CURRENT_INSTALL_LINK
    staged = install_root / f".{CURRENT_INSTALL_LINK}-{os.getpid()}"
    staged.unlink(missing_ok=True)
    staged.symlink_to(prefix.name, target_is_directory=True)
    try:
        os.replace(staged, current)
    finally:
        staged.unlink(missing_ok=True)
    return current


class TomlEditorUnavailableError(RuntimeError):
    """The TOML editor is missing and this run may not install it."""


def is_toml_editor_available():
    """Report whether the TOML editor is importable or already in the private directory."""
    return importlib.util.find_spec("tomlkit") is not None or (tools_root() / "python/tomlkit/__init__.py").is_file()


def load_toml_editor(allow_install=True):
    """Reuse the TOML editor or install it in a private Python dependency directory."""
    try:
        return importlib.import_module("tomlkit")
    except ImportError:
        dependencies = tools_root() / "python"
        ensure_safe_path(dependencies)
        requirements = Path(__file__).with_name("requirements-browser.txt")
        if not (dependencies / "tomlkit/__init__.py").is_file():
            if not allow_install:
                raise TomlEditorUnavailableError("Browser registration needs the private TOML editor, which the browser install provides")
            dependencies.mkdir(parents=True, exist_ok=True)
            run_command([sys.executable, "-m", "pip", "install", "--target", str(dependencies),
                         "--no-deps", "--requirement", str(requirements)], "install private TOML editor")
        sys.path.insert(0, str(dependencies))
        importlib.invalidate_caches()
        return importlib.import_module("tomlkit")


def launcher_commands(binaries, browser):
    """Describe each managed server as environment plus exec arguments."""
    headless = []
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        headless = ["--headless"]
    return {
        "chrome-devtools": ({}, [str(binaries / "chrome-devtools-mcp"), "--executablePath", str(browser),
                                 "--isolated", "--no-usage-statistics", *headless]),
        "playwright": ({}, [str(binaries / "playwright-mcp"), "--executable-path", str(browser), "--isolated", *headless]),
        "agent-browser": ({"AGENT_BROWSER_EXECUTABLE_PATH": str(browser)}, [str(binaries / "agent-browser"), "mcp"]),
    }


@contextlib.contextmanager
def exclusive_lock(lock_path, busy_message):
    """Hold a non-blocking exclusive lock, failing fast when another run owns it."""
    ensure_safe_path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock_file:
        try:
            if fcntl is not None:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except (BlockingIOError, PermissionError) as error:
            raise RuntimeError(busy_message) from error
        yield


def write_launchers(binaries, browser):
    """Regenerate every launcher and the installation record; callers hold the install lock."""
    launchers = tools_root() / LAUNCHER_DIRECTORY
    ensure_safe_path(launchers)
    for name, (environment, command) in launcher_commands(binaries, browser).items():
        lines = ["#!/bin/sh", "# Generated by agent-ready-setup on every bootstrap; do not edit."]
        lines += [f"export {variable}={shlex.quote(value)}" for variable, value in environment.items()]
        lines.append(f'exec {" ".join(shlex.quote(argument) for argument in command)} "$@"')
        launcher = launchers / name
        atomic_write(launcher, "\n".join(lines) + "\n")
        os.chmod(launcher, 0o755)
    write_if_changed(tools_root() / INSTALLATION_METADATA_NAME, json.dumps({
        "agent_browser": str(binaries / "agent-browser"), "browser_executable": str(browser),
    }, indent=2) + "\n")
    return launchers


def write_if_changed(path, content):
    """Skip rewrites of unchanged generated files so repeated syncs stay quiet."""
    ensure_safe_path(path)
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return
    atomic_write(path, content)


def read_installation():
    """Return the installation behind the current launchers, or None when unusable."""
    launchers = tools_root() / LAUNCHER_DIRECTORY
    try:
        _, metadata = read_config(tools_root() / INSTALLATION_METADATA_NAME, json.loads)
    except (OSError, RuntimeError):
        return None
    fields = ("agent_browser", "browser_executable")
    if not all(isinstance(metadata.get(field), str) for field in fields):
        return None
    agent_browser, browser = Path(metadata["agent_browser"]), Path(metadata["browser_executable"])
    launchers_ready = all(os.access(launchers / name, os.X_OK) for name in SERVER_ALIASES)
    if not (launchers_ready and os.access(agent_browser, os.X_OK) and os.access(browser, os.X_OK)):
        return None
    return agent_browser.parent, browser


def portable_servers(provider):
    """Build project registrations that reference launchers through $HOME."""
    servers = {}
    for name in SERVER_ALIASES:
        launcher = (TOOLS_HOME_RELATIVE_PATH / LAUNCHER_DIRECTORY / name).as_posix()
        if provider == "Claude":
            # Claude expands ${VAR} in .mcp.json commands.
            servers[name] = {"command": f"${{HOME}}/{launcher}"}
        else:
            # Codex does not expand variables in commands, so a shell resolves $HOME.
            servers[name] = {"command": "sh", "args": ["-c", f'exec "$HOME/{launcher}"']}
    return servers


def is_managed_server(server):
    """Identify registrations whose command or arguments point into browser-tools."""
    if not hasattr(server, "get"):
        return False
    arguments = server.get("args")
    values = [server.get("command"), *(arguments if isinstance(arguments, list) else [])]
    return any(isinstance(value, str) and MANAGED_COMMAND_FRAGMENT in value for value in values)


def server_map(config, key, location):
    """Return the configured server map, rejecting non-object values."""
    servers = config.get(key, {})
    if not isinstance(servers, dict):
        raise RuntimeError(f"Browser setup preserved invalid server map: {location}")
    return servers


def pending_servers(desired, project_servers, other_servers):
    """Select managed servers to add or refresh without shadowing user-defined aliases."""
    pending = {}
    for name, server in desired.items():
        current = project_servers.get(name)
        if current is not None and is_managed_server(current):
            if any(current.get(field) != server.get(field) for field in SERVER_FIELDS):
                pending[name] = server
        elif not SERVER_ALIASES[name].intersection(set(project_servers) | set(other_servers)):
            pending[name] = server
    return pending


def write_project_servers(provider, destination, original, config, key, pending, allow_dependency_install):
    """Add or refresh managed servers while preserving every other project setting."""
    if provider == "Claude":
        servers = config.setdefault(key, {})
        for name, server in pending.items():
            entry = servers.setdefault(name, {})
            for field in SERVER_FIELDS:
                entry.pop(field, None)
            entry.update(server)
        updated = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    else:
        editor = load_toml_editor(allow_dependency_install)
        document = editor.parse(original)
        if key not in document:
            document[key] = editor.table()
        servers = document[key]
        for name, server in pending.items():
            if name not in servers:
                servers[name] = editor.inline_table() if isinstance(servers, editor.items.InlineTable) else editor.table()
            for field in SERVER_FIELDS:
                if field in servers[name]:
                    del servers[name][field]
            servers[name].update(server)
        updated = editor.dumps(document)
        tomllib.loads(updated)
    atomic_write(destination, updated, original)


def is_set_up(project):
    """True while agent-ready-setup manages the project: apply writes the lockfile before this runs."""
    return (project / AGENT_READY_LOCK_PATH).is_file()


def report_removed_project(project):
    """A detached install can finish after `agent-ready remove`; it must not register servers again."""
    print(f"Browser registration skipped: agent-ready-setup is no longer set up in {project}.", file=sys.stderr)


def ignore_browser_metadata(project):
    """Keep machine-specific browser metadata out of version control."""
    check = subprocess.run(["git", "-C", str(project), "check-ignore", "--quiet", "--no-index", BROWSER_METADATA_PATH],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if check.returncode == 0:
        return
    if check.returncode != 1:
        raise RuntimeError(f"Browser setup requires a Git worktree to ignore {BROWSER_METADATA_PATH}: {project}")
    gitignore = project / ".gitignore"
    original = gitignore.read_text() if gitignore.exists() else ""
    separator = "\n" if original and not original.endswith("\n") else ""
    atomic_write(gitignore, f"{original}{separator}{BROWSER_METADATA_PATH}\n", original)


def register_servers(project, binaries, browser, allow_dependency_install=True):
    """Register portable project servers; user configuration is only read."""
    claude_config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    claude_user_path = Path(claude_config_dir) / ".claude.json" if claude_config_dir else user_home() / ".claude.json"
    codex_user_path = Path(os.environ.get("CODEX_HOME", str(user_home() / ".codex"))) / "config.toml"
    failures = []
    toml_editor_missing = None
    for provider, destination, user_path, parser, key in (
        ("Claude", project / ".mcp.json", claude_user_path, json.loads, "mcpServers"),
        ("Codex", project / ".codex/config.toml", codex_user_path, tomllib.loads, "mcp_servers"),
    ):
        try:
            original, config = read_config(destination, parser)
            project_servers = server_map(config, key, destination)
            _, user_config = read_config(user_path, parser, protect_destination=False)
            other_servers = server_map(user_config, key, user_path)
            if provider == "Claude":
                projects = user_config.get("projects", {})
                if not isinstance(projects, dict):
                    raise RuntimeError(f"Browser setup preserved invalid project map: {user_path}")
                local_config = projects.get(str(project.resolve()), {})
                if not isinstance(local_config, dict):
                    raise RuntimeError(f"Browser setup preserved invalid local server map: {user_path}")
                other_servers = {**other_servers, **server_map(local_config, "mcpServers", user_path)}
            pending = pending_servers(portable_servers(provider), project_servers, other_servers)
            if pending:
                write_project_servers(provider, destination, original, config, key, pending, allow_dependency_install)
            print(f"Browser setup: {provider} registered or refreshed {len(pending)} portable servers; "
                  "user-defined servers preserved", file=sys.stderr)
        except TomlEditorUnavailableError as error:
            toml_editor_missing = error
        except (OSError, RuntimeError, ValueError) as error:
            failures.append(str(error))
    if failures:
        raise RuntimeError("; ".join(failures))
    if toml_editor_missing is not None:
        raise toml_editor_missing
    ignore_browser_metadata(project)
    write_if_changed(project / BROWSER_METADATA_PATH, json.dumps({
        "agent_browser": str(binaries / "agent-browser"), "browser_executable": str(browser),
    }, indent=2) + "\n")


def remove_file(path, original):
    """Delete a project file this setup wrote, unless it changed since it was read."""
    ensure_safe_path(path)
    if path.read_text(encoding="utf-8") != original:
        raise RuntimeError(f"Browser setup preserved concurrent changes: {path}")
    path.unlink()


def unregister_provider(provider, destination, parser, key):
    """Drop the managed servers of one project file; returns removed, edited or None."""
    original, config = read_config(destination, parser)
    servers = server_map(config, key, destination)
    managed = [name for name, server in servers.items() if is_managed_server(server)]
    if not managed:
        return None
    if provider == "Claude":
        for name in managed:
            del config[key][name]
        if not config[key]:
            del config[key]
        updated = json.dumps(config, indent=2, ensure_ascii=False) + "\n" if config else ""
    else:
        editor = load_toml_editor(allow_install=False)
        document = editor.parse(original)
        for name in managed:
            del document[key][name]
        if not document[key]:
            del document[key]
        updated = editor.dumps(document)
        tomllib.loads(updated)
    if updated.strip():
        atomic_write(destination, updated, original)
        return "edited"
    # The file only held what this setup registered.
    remove_file(destination, original)
    return "removed"


def forget_browser_metadata(project):
    """Delete the machine metadata and the .gitignore line that kept it out of version control."""
    changed = []
    metadata = project / BROWSER_METADATA_PATH
    if metadata.is_file() and not metadata.is_symlink():
        ensure_safe_path(metadata)
        metadata.unlink()
        changed.append(("removed", BROWSER_METADATA_PATH))
    gitignore = project / ".gitignore"
    if gitignore.is_file():
        original = gitignore.read_text(encoding="utf-8")
        lines = original.splitlines()
        if BROWSER_METADATA_PATH in lines:
            kept = [line for line in lines if line != BROWSER_METADATA_PATH]
            if any(line.strip() for line in kept):
                atomic_write(gitignore, "\n".join(kept) + "\n", original)
            else:
                remove_file(gitignore, original)
            changed.append(("edited" if gitignore.exists() else "removed", ".gitignore"))
    return changed


def unregister_servers(project):
    """Remove the portable servers this setup registered; every other setting stays.

    Returns (outcome, relative path) pairs, the outcome being removed or edited.
    Entry point: unregister-browser-servers.py, which `agent-ready remove` runs. Never
    installs the TOML editor: without it, the Codex registrations stay and the error says so.
    """
    changed = []
    failures = []
    # The install lock keeps a running install from registering the servers again halfway through.
    with exclusive_lock(tools_root() / INSTALL_LOCK_NAME,
                        "browser setup is installing the tools; run agent-ready remove again when it finishes"):
        for provider, relative_path, parser, key in (
            ("Claude", ".mcp.json", json.loads, "mcpServers"),
            ("Codex", ".codex/config.toml", tomllib.loads, "mcp_servers"),
        ):
            destination = project / relative_path
            if not destination.exists():
                continue
            try:
                outcome = unregister_provider(provider, destination, parser, key)
                if outcome:
                    changed.append((outcome, relative_path))
            except (OSError, RuntimeError, ValueError) as error:
                failures.append(f"{relative_path}: {error}")
        changed += forget_browser_metadata(project)
    if failures:
        raise RuntimeError("; ".join(failures))
    return changed


def main():
    """Install once per pinned version and configure both supported providers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    arguments.project = arguments.project.absolute()
    versions = load_pinned_versions()
    try:
        ensure_safe_path(arguments.project)
        with exclusive_lock(tools_root() / INSTALL_LOCK_NAME,
                            "Browser setup already running; rerun bootstrap after it finishes"):
            binaries, browser = install_tools(tools_root(), versions)
            write_launchers(binaries, browser)
            if not is_set_up(arguments.project):
                report_removed_project(arguments.project)
                return 0
            register_servers(arguments.project, binaries, browser)
        print("Browser setup complete. Restart provider and trust project MCPs when required. cua remains host-provided.", file=sys.stderr)
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Browser setup incomplete: {error}", file=sys.stderr)
        return 1


def adopt_existing_installation():
    """Create launchers from a complete pinned install left by an earlier bootstrap.

    Runs only local commands: no npm, downloads, or network. Returns None when the
    pinned install is incomplete, so a full bootstrap remains required.
    """
    versions = load_pinned_versions()
    prefix = pinned_install_prefix(tools_root(), versions)
    if not shutil.which("node") or not is_pinned_install_complete(prefix, versions):
        return None
    with exclusive_lock(tools_root() / INSTALL_LOCK_NAME,
                        "browser setup is already running; rerun after it finishes"):
        browser = locate_chromium(prefix)
        if not browser.is_file() or not os.access(browser, os.X_OK):
            return None
        binaries = point_current_install(tools_root(), prefix) / "node_modules/.bin"
        write_launchers(binaries, browser)
    print("Browser setup: adopted the existing pinned installation without downloads", file=sys.stderr)
    return read_installation()


def register_from_installation(project):
    """Sync project registrations from the current launchers without installing anything.

    Entry point: register-browser-servers.py, which SessionStart sync runs. Returns
    NO_INSTALLATION_EXIT_CODE when only a full install can provide the tools.
    """
    installation = read_installation()
    if installation is None:
        try:
            installation = adopt_existing_installation()
        except (OSError, RuntimeError, ValueError) as error:
            print(f"Browser registration skipped: could not adopt the existing installation ({error}); "
                  "it retries in the next session.", file=sys.stderr)
            return 0
    if installation is None:
        print("Browser registration skipped: no complete browser installation.", file=sys.stderr)
        return NO_INSTALLATION_EXIT_CODE
    binaries, browser = installation
    if not is_set_up(project):
        report_removed_project(project)
        return 0
    try:
        ensure_safe_path(project)
        register_servers(project, binaries, browser, allow_dependency_install=False)
    except TomlEditorUnavailableError as error:
        print(f"Browser registration incomplete: {error}.", file=sys.stderr)
        return NO_INSTALLATION_EXIT_CODE
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Browser registration incomplete: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
