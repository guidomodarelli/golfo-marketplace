"""Exercise browser installation recovery and real JSON/TOML registration."""

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import tomllib
import unittest
from unittest.mock import patch

try:
    import tomlkit
except ImportError:
    print("Browser test dependencies missing; run pnpm run setup:browser-tests before testing.", file=sys.stderr)
    sys.exit(1)

HELPER_PATH = Path(__file__).resolve().parents[1] / "scripts/setup-browser-tools.py"
SPEC = importlib.util.spec_from_file_location("browser_setup", HELPER_PATH)
browser_setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser_setup)


class BrowserToolsTests(unittest.TestCase):
    """Verify observable configuration and installation outcomes."""

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.root = Path(self.workspace.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True)
        self.tools_root = self.root / ".local/share/agent-ready-setup/browser-tools"
        self.binaries = self.tools_root / "current/node_modules/.bin"
        self.browser = self.root / "Chrome for Testing.app/chrome"
        self.browser.parent.mkdir()
        self.claude_user = self.root / ".claude.json"
        self.codex_user = self.root / ".codex/config.toml"
        self.environment = patch.dict(os.environ, {"HOME": str(self.root), "CODEX_HOME": str(self.root / ".codex"), "CLAUDE_CONFIG_DIR": ""})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.workspace.cleanup()

    def register(self):
        browser_setup.register_servers(self.project, self.binaries, self.browser)

    def project_servers(self):
        claude = json.loads((self.project / ".mcp.json").read_text())["mcpServers"]
        codex = tomllib.loads((self.project / ".codex/config.toml").read_text())["mcp_servers"]
        return claude, codex

    def write_fake_binaries(self):
        self.binaries.mkdir(parents=True)
        for name in ("chrome-devtools-mcp", "playwright-mcp", "agent-browser"):
            fake = self.binaries / name
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$(basename "$0")" "$@" "env=${AGENT_BROWSER_EXECUTABLE_PATH:-}"\n')
            fake.chmod(0o755)

    def test_should_register_portable_project_servers_for_both_providers(self):
        self.register()
        claude, codex = self.project_servers()
        self.assertEqual(set(claude), {"chrome-devtools", "playwright", "agent-browser"})
        self.assertEqual(set(codex), set(claude))
        self.assertEqual(claude["playwright"], {"command": "${HOME}/.local/share/agent-ready-setup/browser-tools/bin/playwright"})
        self.assertEqual(codex["playwright"], {"command": "sh", "args": ["-c", 'exec "$HOME/.local/share/agent-ready-setup/browser-tools/bin/playwright"']})
        for config in (".mcp.json", ".codex/config.toml"):
            self.assertNotIn(str(self.root), (self.project / config).read_text())
        self.assertFalse(self.claude_user.exists())
        self.assertFalse(self.codex_user.exists())
        status = json.loads((self.project / ".agents/browser-tools.json").read_text())
        self.assertEqual(status["agent_browser"], str(self.binaries / "agent-browser"))

    def test_should_run_installed_tools_through_generated_launchers(self):
        self.write_fake_binaries()
        # A display keeps launchers headed on Linux CI too; the headless path has its own test.
        with patch.dict(os.environ, {"DISPLAY": ":0"}):
            browser_setup.write_launchers(self.binaries, self.browser)
        self.register()
        claude, codex = self.project_servers()
        claude_command = claude["agent-browser"]["command"].replace("${HOME}", str(self.root))
        claude_output = subprocess.run([claude_command], capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(claude_output, ["agent-browser", "mcp", f"env={self.browser}"])
        codex_output = subprocess.run([codex["playwright"]["command"], *codex["playwright"]["args"]],
                                      capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(codex_output, ["playwright-mcp", "--executable-path", str(self.browser), "--isolated", "env="])
        launcher = self.tools_root / "bin/chrome-devtools"
        self.assertTrue(os.access(launcher, os.X_OK))
        self.assertIn("--no-usage-statistics", subprocess.run([launcher], capture_output=True, text=True, check=True).stdout)

    def install_fake_tools(self):
        self.write_fake_binaries()
        self.browser.write_text("#!/bin/sh\n")
        self.browser.chmod(0o755)
        browser_setup.write_launchers(self.binaries, self.browser)

    def test_should_register_from_existing_installation_without_installing(self):
        self.install_fake_tools()
        legacy = "/Users/someone/.local/share/agent-ready-setup/browser-tools/1.9.0-0.0.81-0.38.0/node_modules/.bin"
        (self.project / ".mcp.json").write_text(json.dumps({"mcpServers": {"playwright": {"command": f"{legacy}/playwright-mcp"}}}))
        with patch.object(browser_setup, "run_command", side_effect=AssertionError("register-only must not run installers")):
            self.assertEqual(browser_setup.register_from_installation(self.project), 0)
        claude, codex = self.project_servers()
        self.assertEqual(claude["playwright"], {"command": "${HOME}/.local/share/agent-ready-setup/browser-tools/bin/playwright"})
        self.assertEqual(set(codex), {"chrome-devtools", "playwright", "agent-browser"})
        status = json.loads((self.project / ".agents/browser-tools.json").read_text())
        self.assertEqual(status, {"agent_browser": str(self.binaries / "agent-browser"), "browser_executable": str(self.browser)})

    def test_should_register_through_dedicated_entry_point(self):
        self.install_fake_tools()
        entry_point = HELPER_PATH.with_name("register-browser-servers.py")
        result = subprocess.run([sys.executable, str(entry_point), "--project", str(self.project)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        claude, codex = self.project_servers()
        self.assertEqual(set(claude), {"chrome-devtools", "playwright", "agent-browser"})
        self.assertEqual(set(codex), set(claude))
        self.assertFalse(self.claude_user.exists())
        rejected = subprocess.run([sys.executable, str(HELPER_PATH), "--register-only"], capture_output=True, text=True, check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("unrecognized arguments: --register-only", rejected.stderr)

    def create_pinned_install(self, executables=browser_setup.REQUIRED_EXECUTABLES):
        versions = browser_setup.load_pinned_versions()
        prefix = self.tools_root / "-".join(versions.values())
        for package, version in versions.items():
            manifest = prefix / "node_modules" / package / "package.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"version": version}))
        (prefix / "node_modules/.bin").mkdir(parents=True, exist_ok=True)
        for name in executables:
            (prefix / "node_modules/.bin" / name).touch(mode=0o755)
        self.browser.touch(mode=0o755)
        return prefix

    def local_chromium_lookup(self, operations):
        def external_operation(arguments, operation, capture=False):
            operations.append(arguments[0])
            self.assertEqual(arguments[0], "node", "adoption must not run npm or download Chromium")
            return str(self.browser)
        return external_operation

    def test_should_adopt_existing_pinned_install_without_downloads(self):
        prefix = self.create_pinned_install()
        operations = []
        with patch.object(browser_setup.shutil, "which", return_value="/usr/bin/node"), \
                patch.object(browser_setup, "run_command", side_effect=self.local_chromium_lookup(operations)):
            self.assertEqual(browser_setup.register_from_installation(self.project), 0)
        self.assertEqual(operations, ["node"])
        self.assertEqual((self.tools_root / "current").resolve(), prefix)
        self.assertTrue(os.access(self.tools_root / "bin/agent-browser", os.X_OK))
        installation = json.loads((self.tools_root / "installation.json").read_text())
        self.assertEqual(installation["browser_executable"], str(self.browser))
        claude, codex = self.project_servers()
        self.assertEqual(set(claude), {"chrome-devtools", "playwright", "agent-browser"})
        self.assertEqual(set(codex), set(claude))

    def test_should_not_adopt_incomplete_pinned_install(self):
        self.create_pinned_install(executables=("chrome-devtools-mcp", "agent-browser"))
        with patch.object(browser_setup.shutil, "which", return_value="/usr/bin/node"), \
                patch.object(browser_setup, "run_command", side_effect=AssertionError("incomplete install must not run commands")):
            self.assertEqual(browser_setup.register_from_installation(self.project), browser_setup.NO_INSTALLATION_EXIT_CODE)
        self.assertFalse((self.tools_root / "current").exists())
        self.assertFalse((self.tools_root / "bin").exists())
        self.assertFalse((self.project / ".mcp.json").exists())

    def test_should_not_adopt_while_bootstrap_holds_the_install_lock(self):
        self.create_pinned_install()
        lock_path = self.tools_root / ".install.lock"
        with lock_path.open("w") as competing_lock:
            fcntl.flock(competing_lock, fcntl.LOCK_EX)
            with patch.object(browser_setup.shutil, "which", return_value="/usr/bin/node"), \
                    patch.object(browser_setup, "run_command", side_effect=AssertionError("locked adoption must not run commands")):
                self.assertEqual(browser_setup.register_from_installation(self.project), 0)
        self.assertFalse((self.tools_root / "current").exists())
        self.assertFalse((self.project / ".mcp.json").exists())

    def test_should_report_missing_installation_without_changing_the_project(self):
        (self.project / ".mcp.json").write_text('{"mcpServers": {}}')
        self.assertEqual(browser_setup.register_from_installation(self.project), browser_setup.NO_INSTALLATION_EXIT_CODE)
        self.install_fake_tools()
        (self.tools_root / "bin/playwright").unlink()
        self.assertEqual(browser_setup.register_from_installation(self.project), browser_setup.NO_INSTALLATION_EXIT_CODE)
        self.assertEqual((self.project / ".mcp.json").read_text(), '{"mcpServers": {}}')
        self.assertFalse((self.project / ".agents/browser-tools.json").exists())

    def load_background_installer(self):
        specification = importlib.util.spec_from_file_location("background_installer", HELPER_PATH.with_name("start-browser-install.py"))
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module

    def start_background_install(self, installer, **environment):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.root / "cache"), **environment}), \
                patch.object(installer.shutil, "which", return_value="/usr/bin/tool"), \
                patch.object(subprocess, "Popen") as spawn:
            message = installer.start_install(browser_setup, self.project)
        return message, spawn

    def test_should_start_detached_full_install_when_tools_are_missing(self):
        installer = self.load_background_installer()
        message, spawn = self.start_background_install(installer)
        spawn.assert_called_once()
        command = spawn.call_args.args[0]
        self.assertEqual(command[1:], [str(HELPER_PATH), "--project", str(self.project)])
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        self.assertIs(spawn.call_args.kwargs["stdin"], subprocess.DEVNULL)
        log_path = self.root / "cache/agent-ready-setup/browser-install.log"
        self.assertEqual(log_path.stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.root / "cache/agent-ready-setup/browser-install-attempt.stamp").is_file())
        self.assertIn("next session", message)

    def test_should_retry_background_install_at_most_once_per_interval(self):
        installer = self.load_background_installer()
        self.start_background_install(installer)
        message, spawn = self.start_background_install(installer)
        spawn.assert_not_called()
        self.assertIn("less than 24 hours", message)
        stamp = self.root / "cache/agent-ready-setup/browser-install-attempt.stamp"
        expired = stamp.stat().st_mtime - installer.RETRY_INTERVAL_SECONDS - 1
        os.utime(stamp, (expired, expired))
        _, spawn = self.start_background_install(installer)
        spawn.assert_called_once()

    def test_should_not_consume_the_retry_window_when_node_is_missing(self):
        installer = self.load_background_installer()
        with patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.root / "cache")}), \
                patch.object(installer.shutil, "which", return_value=None), \
                patch.object(subprocess, "Popen") as spawn:
            message = installer.start_install(browser_setup, self.project)
        spawn.assert_not_called()
        self.assertIn("Node.js 24+ and npm", message)
        self.assertNotIn("bootstrap", message)
        self.assertFalse((self.root / "cache/agent-ready-setup/browser-install-attempt.stamp").exists())

    def test_should_not_start_background_install_when_tools_exist_or_setup_is_running(self):
        installer = self.load_background_installer()
        self.install_fake_tools()
        message, spawn = self.start_background_install(installer)
        spawn.assert_not_called()
        self.assertIn("already installed", message)
        (self.tools_root / "installation.json").unlink()
        with (self.tools_root / ".install.lock").open("w") as competing_lock:
            fcntl.flock(competing_lock, fcntl.LOCK_EX)
            message, spawn = self.start_background_install(installer)
        spawn.assert_not_called()
        self.assertIn("already running", message)
        self.assertFalse((self.root / "cache/agent-ready-setup/browser-install-attempt.stamp").exists())

    def test_should_not_launch_a_second_install_while_another_session_is_starting_one(self):
        installer = self.load_background_installer()
        launch_lock = self.root / "cache/agent-ready-setup/browser-install-launch.lock"
        launch_lock.parent.mkdir(parents=True, exist_ok=True)
        with launch_lock.open("w") as competing_lock:
            fcntl.flock(competing_lock, fcntl.LOCK_EX)
            message, spawn = self.start_background_install(installer)
        spawn.assert_not_called()
        self.assertIn("another session is starting", message)
        self.assertFalse((self.root / "cache/agent-ready-setup/browser-install-attempt.stamp").exists())
        self.assertFalse((self.root / "cache/agent-ready-setup/browser-install.log").exists())

    def test_should_not_rewrite_unchanged_generated_files_on_repeated_sync(self):
        self.install_fake_tools()
        browser_setup.register_from_installation(self.project)
        generated = [self.project / ".mcp.json", self.project / ".codex/config.toml", self.project / ".agents/browser-tools.json",
                     self.tools_root / "installation.json"]
        identities = [path.stat().st_ino for path in generated]
        browser_setup.write_launchers(self.binaries, self.browser)
        browser_setup.register_from_installation(self.project)
        self.assertEqual([path.stat().st_ino for path in generated], identities)

    def without_toml_editor(self):
        real_import, real_find_spec = browser_setup.importlib.import_module, browser_setup.importlib.util.find_spec

        def import_without_tomlkit(name):
            if name == "tomlkit":
                raise ImportError(name)
            return real_import(name)

        def find_spec_without_tomlkit(name, *arguments):
            return None if name == "tomlkit" else real_find_spec(name, *arguments)

        return patch.multiple(browser_setup.importlib, import_module=import_without_tomlkit), \
            patch.object(browser_setup.importlib.util, "find_spec", side_effect=find_spec_without_tomlkit)

    def test_should_never_pip_install_the_toml_editor_without_permission(self):
        import_patch, find_spec_patch = self.without_toml_editor()
        with import_patch, find_spec_patch:
            with self.assertRaisesRegex(RuntimeError, "the browser install provides"):
                browser_setup.load_toml_editor(allow_install=False)
        self.assertFalse((self.root / ".local/share/agent-ready-setup/browser-tools/python").exists())

    def test_should_request_full_install_when_toml_editor_is_missing(self):
        self.install_fake_tools()
        import_patch, find_spec_patch = self.without_toml_editor()
        with import_patch, find_spec_patch:
            self.assertEqual(browser_setup.register_from_installation(self.project), browser_setup.NO_INSTALLATION_EXIT_CODE)
            message, spawn = self.start_background_install(self.load_background_installer())
        claude = json.loads((self.project / ".mcp.json").read_text())["mcpServers"]
        self.assertEqual(set(claude), {"chrome-devtools", "playwright", "agent-browser"})
        self.assertFalse((self.project / ".codex/config.toml").exists())
        spawn.assert_called_once()
        self.assertIn("next session", message)

    def test_should_add_headless_to_launchers_on_linux_without_display(self):
        self.write_fake_binaries()
        with patch.object(browser_setup.sys, "platform", "linux"), patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}):
            browser_setup.write_launchers(self.binaries, self.browser)
        for name in ("chrome-devtools", "playwright"):
            output = subprocess.run([self.tools_root / "bin" / name], capture_output=True, text=True, check=True).stdout
            self.assertIn("--headless", output.splitlines())

    def test_should_preserve_project_configuration_and_be_idempotent(self):
        (self.project / ".mcp.json").write_text(json.dumps({"custom": "ñandú", "mcpServers": {"playwright": {"command": "custom-browser"}}}, ensure_ascii=False))
        (self.project / ".codex").mkdir()
        (self.project / ".codex/config.toml").write_text('# custom comment\nmodel = "custom-model"\n[mcp_servers.playwright]\ncommand = "custom-browser"\nenabled = false\n')
        self.register()
        original_claude = (self.project / ".mcp.json").read_bytes()
        original_codex = (self.project / ".codex/config.toml").read_bytes()
        self.register()
        self.assertEqual((self.project / ".mcp.json").read_bytes(), original_claude)
        self.assertEqual((self.project / ".codex/config.toml").read_bytes(), original_codex)
        self.assertIn("ñandú", original_claude.decode())
        self.assertIn("# custom comment", original_codex.decode())
        claude, codex = self.project_servers()
        self.assertEqual(claude["playwright"], {"command": "custom-browser"})
        self.assertFalse(codex["playwright"]["enabled"])
        self.assertEqual(set(codex), {"playwright", "chrome-devtools", "agent-browser"})

    def test_should_replace_legacy_absolute_registrations_and_keep_custom_settings(self):
        legacy = "/Users/someone/.local/share/agent-ready-setup/browser-tools/1.9.0-0.0.81-0.38.0/node_modules/.bin"
        (self.project / ".mcp.json").write_text(json.dumps({"mcpServers": {
            "playwright": {"command": f"{legacy}/playwright-mcp", "args": ["--executable-path", "/Users/someone/chrome"]},
            "custom": {"command": "custom-server"}}}))
        (self.project / ".codex").mkdir()
        (self.project / ".codex/config.toml").write_text(
            f'[mcp_servers.agent-browser]\ncommand = "{legacy}/agent-browser"\nargs = ["mcp"]\nenabled = false\n\n'
            '[mcp_servers.agent-browser.env]\nAGENT_BROWSER_EXECUTABLE_PATH = "/Users/someone/chrome"\n')
        self.register()
        claude, codex = self.project_servers()
        self.assertEqual(claude["playwright"], {"command": "${HOME}/.local/share/agent-ready-setup/browser-tools/bin/playwright"})
        self.assertEqual(claude["custom"], {"command": "custom-server"})
        self.assertEqual(codex["agent-browser"]["command"], "sh")
        self.assertNotIn("env", codex["agent-browser"])
        self.assertFalse(codex["agent-browser"]["enabled"])
        for config in (".mcp.json", ".codex/config.toml"):
            self.assertNotIn("/Users/someone", (self.project / config).read_text())

    def test_should_only_read_user_configuration_to_avoid_duplicate_aliases(self):
        local = {"projects": {str(self.project): {"mcpServers": {"playwright": {"command": "local"}}}},
                 "mcpServers": {"chrome_devtools": {"command": "existing"}}}
        self.claude_user.write_text(json.dumps(local))
        self.codex_user.parent.mkdir()
        source = self.root / "dotfiles.toml"
        source.write_text('[mcp_servers.chrome_devtools]\ncommand = "existing"\n')
        self.codex_user.symlink_to(source)
        claude_before = self.claude_user.read_bytes()
        self.register()
        claude, codex = self.project_servers()
        self.assertEqual(set(claude), {"agent-browser"})
        self.assertEqual(set(codex), {"playwright", "agent-browser"})
        self.assertEqual(self.claude_user.read_bytes(), claude_before)
        self.assertEqual(source.read_text(), '[mcp_servers.chrome_devtools]\ncommand = "existing"\n')
        self.assertTrue(self.codex_user.is_symlink())

    def test_should_read_custom_claude_config_directory(self):
        directory = self.root / "custom-claude"
        directory.mkdir()
        (directory / ".claude.json").write_text(json.dumps({"mcpServers": {"chrome_devtools": {"command": "existing"}}}))
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(directory)}):
            self.register()
        claude, _ = self.project_servers()
        self.assertNotIn("chrome-devtools", claude)

    def test_should_preserve_malformed_config_and_complete_other_provider(self):
        destination = self.project / ".mcp.json"
        destination.write_text("{malformed")
        with self.assertRaisesRegex(RuntimeError, "malformed configuration"):
            self.register()
        self.assertEqual(destination.read_text(), "{malformed")
        self.assertEqual(len(tomllib.loads((self.project / ".codex/config.toml").read_text())["mcp_servers"]), 3)
        self.assertFalse((self.project / ".agents/browser-tools.json").exists())

    def test_should_preserve_inline_codex_map_and_other_settings(self):
        (self.project / ".codex").mkdir()
        destination = self.project / ".codex/config.toml"
        destination.write_text('# custom settings\nmodel = "custom-model"\nmcp_servers = { custom = { command = "existing", enabled = false } } # preserved\n')
        self.register()
        result = tomllib.loads(destination.read_text())
        self.assertEqual(result["model"], "custom-model")
        self.assertEqual(result["mcp_servers"]["custom"], {"command": "existing", "enabled": False})
        self.assertEqual(set(result["mcp_servers"]), {"custom", "chrome-devtools", "playwright", "agent-browser"})
        first_write = destination.read_bytes()
        self.register()
        self.assertEqual(destination.read_bytes(), first_write)

    def test_should_ignore_browser_metadata_once(self):
        (self.project / ".gitignore").write_text("node_modules/")
        self.register()
        self.register()
        self.assertEqual((self.project / ".gitignore").read_text(), "node_modules/\n.agents/browser-tools.json\n")

    def test_should_keep_gitignore_when_metadata_is_already_ignored(self):
        (self.project / ".gitignore").write_text(".agents/\n")
        self.register()
        self.assertEqual((self.project / ".gitignore").read_text(), ".agents/\n")

    def test_should_unregister_only_managed_servers_and_keep_project_settings(self):
        (self.project / ".mcp.json").write_text(json.dumps({"custom": "ñandú", "mcpServers": {"own": {"command": "own-server"}}}, ensure_ascii=False))
        (self.project / ".codex").mkdir()
        (self.project / ".codex/config.toml").write_text('# custom comment\nmodel = "custom-model"\n[mcp_servers.own]\ncommand = "own-server"\n')
        (self.project / ".gitignore").write_text("node_modules/")
        self.register()
        changed = browser_setup.unregister_servers(self.project)
        self.assertEqual(set(changed), {("edited", ".mcp.json"), ("edited", ".codex/config.toml"),
                                        ("removed", ".agents/browser-tools.json"), ("edited", ".gitignore")})
        claude, codex = self.project_servers()
        self.assertEqual(claude, {"own": {"command": "own-server"}})
        self.assertEqual(set(codex), {"own"})
        self.assertIn("ñandú", (self.project / ".mcp.json").read_text())
        self.assertIn("# custom comment", (self.project / ".codex/config.toml").read_text())
        self.assertEqual((self.project / ".gitignore").read_text(), "node_modules/\n")
        self.assertEqual(browser_setup.unregister_servers(self.project), [])

    def test_should_unregister_through_dedicated_entry_point_and_delete_files_it_created(self):
        self.register()
        entry_point = HELPER_PATH.with_name("unregister-browser-servers.py")
        result = subprocess.run([sys.executable, str(entry_point), "--project", str(self.project)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.splitlines()), {"removed\t.mcp.json", "removed\t.codex/config.toml",
                                                           "removed\t.agents/browser-tools.json", "removed\t.gitignore"})
        for created in (".mcp.json", ".codex/config.toml", ".gitignore", ".agents/browser-tools.json"):
            self.assertFalse((self.project / created).exists(), created)
        self.assertFalse(self.claude_user.exists())

    def test_should_preserve_symlinked_project_config_without_touching_target(self):
        target = self.root / "target.json"
        target.write_text("{}")
        (self.project / ".mcp.json").symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "symlinked"):
            self.register()
        self.assertEqual(target.read_text(), "{}")
        self.assertTrue((self.project / ".mcp.json").is_symlink())

    def test_should_reject_stale_config_snapshot(self):
        destination = self.project / "config.json"
        destination.write_text("updated-by-user")
        with self.assertRaisesRegex(RuntimeError, "concurrent changes"):
            browser_setup.atomic_write(destination, "replacement", "old-snapshot")
        self.assertEqual(destination.read_text(), "updated-by-user")

    def test_should_reject_old_node_before_installing(self):
        # Mock only our external-command boundary to avoid changing host runtimes
        # or downloading packages. A separate real smoke test exercises npm/MCP.
        with patch.object(browser_setup, "run_command", return_value="v22.12.0") as commands:
            with self.assertRaisesRegex(RuntimeError, "Node.js 24"):
                browser_setup.install_tools(self.root / "tools", {"agent-browser": "0.38.0"})
        self.assertEqual(commands.call_count, 1)

    def test_should_skip_package_and_browser_downloads_when_already_installed(self):
        versions = json.loads(HELPER_PATH.with_name("browser-tools.json").read_text())
        prefix = self.root / "tools" / "-".join(versions.values())
        for package, version in versions.items():
            manifest = prefix / "node_modules" / package / "package.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"version": version}))
        binaries = prefix / "node_modules/.bin"
        binaries.mkdir()
        for name in ("chrome-devtools-mcp", "playwright-mcp", "agent-browser", "playwright"):
            (binaries / name).touch(mode=0o700)
        self.browser.touch(mode=0o700)
        with patch.object(browser_setup, "run_command", side_effect=["v24.17.0", str(self.browser), ""]) as commands:
            actual_binaries, actual_browser = browser_setup.install_tools(self.root / "tools", versions)
        self.assertEqual(actual_binaries, self.root / "tools/current/node_modules/.bin")
        self.assertEqual(actual_binaries.resolve(), binaries)
        self.assertEqual(actual_browser, self.browser)
        self.assertEqual(commands.call_count, 3)

    def test_should_repoint_current_install_after_version_change(self):
        tools_root = self.root / "tools"
        for prefix_name in ("1.0.0", "2.0.0"):
            (tools_root / prefix_name).mkdir(parents=True)
            current = browser_setup.point_current_install(tools_root, tools_root / prefix_name)
        self.assertEqual(current.resolve(), tools_root / "2.0.0")
        self.assertEqual(os.readlink(current), "2.0.0")
        self.assertEqual(sorted(path.name for path in tools_root.iterdir()), ["1.0.0", "2.0.0", "current"])

    def test_should_report_external_command_failure_with_private_diagnostic(self):
        with self.assertRaisesRegex(RuntimeError, "failed \\(exit 7\\); diagnostic:") as failure:
            browser_setup.run_command([sys.executable, "-c", "import sys; sys.exit(7)"], "install packages")
        diagnostic = Path(str(failure.exception).split("diagnostic: ")[1].split(";")[0])
        self.assertEqual(diagnostic.stat().st_mode & 0o777, 0o600)
        diagnostic.unlink()

    def test_should_repair_executables_missing_from_a_partial_installation(self):
        versions = json.loads(HELPER_PATH.with_name("browser-tools.json").read_text())
        prefix = self.root / "tools" / "-".join(versions.values())
        for package, version in versions.items():
            manifest = prefix / "node_modules" / package / "package.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"version": version}))
        self.browser.touch(mode=0o700)
        binaries = prefix / "node_modules/.bin"
        operations = []

        def external_operation(arguments, operation, capture=False):
            operations.append(arguments)
            if arguments[0] == "npm":
                binaries.mkdir()
                for name in ("chrome-devtools-mcp", "playwright-mcp", "agent-browser", "playwright"):
                    (binaries / name).touch(mode=0o700)
                return ""
            if arguments == ["node", "--version"]:
                return "v24.17.0"
            return str(self.browser) if capture else ""

        with patch.object(browser_setup, "run_command", side_effect=external_operation):
            actual_binaries, _ = browser_setup.install_tools(self.root / "tools", versions)
        self.assertEqual(actual_binaries.resolve(), binaries)
        self.assertEqual(len([arguments for arguments in operations if arguments[0] == "npm"]), 1)
        self.assertTrue((binaries / "agent-browser").is_file())

    def test_should_stop_timed_out_command_and_allow_retry(self):
        with patch.object(browser_setup, "COMMAND_TIMEOUT_SECONDS", 0.05):
            with self.assertRaisesRegex(RuntimeError, "timed out") as failure:
                browser_setup.run_command([sys.executable, "-c", "import time; time.sleep(10)"], "download browser")
        diagnostic = Path(str(failure.exception).split("diagnostic: ")[1].split(";")[0])
        diagnostic.unlink()
        self.assertEqual(browser_setup.run_command([sys.executable, "-c", "print('ready')"], "retry", capture=True), "ready")

    @unittest.skipUnless(os.environ.get("AGENT_READY_SETUP_BROWSER_SMOKE_ROOT") and os.environ.get("AGENT_READY_SETUP_BROWSER_SMOKE_EXECUTABLE"),
                         "Set smoke root and executable to exercise installed Chromium without downloads")
    def test_should_launch_registered_chromium_when_cache_has_no_headless_shell(self):
        browser = Path(os.environ["AGENT_READY_SETUP_BROWSER_SMOKE_EXECUTABLE"])
        chromium_directory = next(parent for parent in browser.parents if parent.name.startswith("chromium-"))
        cache = self.root / "browser-cache"
        cache.mkdir()
        (cache / chromium_directory.name).symlink_to(chromium_directory, target_is_directory=True)
        versions = json.loads(HELPER_PATH.with_name("browser-tools.json").read_text())
        with patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": str(cache)}):
            _, executable = browser_setup.install_tools(Path(os.environ["AGENT_READY_SETUP_BROWSER_SMOKE_ROOT"]), versions)
        self.assertTrue(executable.is_file())
        self.assertTrue(executable.is_relative_to(cache))


if __name__ == "__main__":
    unittest.main()
