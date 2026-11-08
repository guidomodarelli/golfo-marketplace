// The launcher runs the engine of the installed golfo-kit plugin with the same arguments,
// streams and exit status, prefers the newest installed version, and fails with an
// install hint when there is none. The engines here are small Python scripts in the
// layouts that Claude Code, Codex and Hermes use; the last test runs the real engine.
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { constants, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, beforeEach, test } from "node:test";
import { fileURLToPath } from "node:url";

import { compareVersions, resolveEngine } from "../lib/resolve-engine.js";

const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const LAUNCHER = join(PACKAGE_ROOT, "bin", "agent-ready.js");
const REPOSITORY_SKILL = join(PACKAGE_ROOT, "..", "..", "plugins", "golfo-kit", "skills", "agent-ready-setup");
const FAKE_ENGINE = [
  "import json, os, sys",
  "print(json.dumps({'engine': os.environ['FAKE_ENGINE_NAME'], 'arguments': sys.argv[1:],",
  "                  'provider': os.environ.get('AGENT_READY_SETUP_ACTIVE_PROVIDER')}))",
  "sys.stderr.write('engine progress\\n')",
  "sys.exit(int(os.environ.get('FAKE_ENGINE_STATUS', '0')))",
].join("\n");

let home;

beforeEach(() => {
  home = mkdtempSync(join(tmpdir(), "agent-ready-launcher-"));
});

afterEach(() => {
  rmSync(home, { recursive: true, force: true });
});

/** A golfo-kit plugin with its manifest and a fake engine, in the layout the provider uses. */
function installPlugin(pluginRoot, version, name) {
  mkdirSync(join(pluginRoot, ".claude-plugin"), { recursive: true });
  writeFileSync(join(pluginRoot, ".claude-plugin", "plugin.json"), JSON.stringify({ name: "golfo-kit", version }));
  const scripts = join(pluginRoot, "skills", "agent-ready-setup", "scripts");
  mkdirSync(scripts, { recursive: true });
  writeFileSync(join(scripts, "agent-ready"), FAKE_ENGINE.replace("os.environ['FAKE_ENGINE_NAME']", JSON.stringify(name)));
  return join(pluginRoot, "skills", "agent-ready-setup");
}

function environment(extra = {}) {
  const variables = { ...process.env, HOME: home, USERPROFILE: home, LOCALAPPDATA: join(home, "local"), ...extra };
  for (const name of ["CLAUDE_CONFIG_DIR", "CODEX_HOME", "HERMES_HOME", "AGENT_READY_SETUP_SKILL_DIR"]) {
    if (!(name in extra)) {
      delete variables[name];
    }
  }
  return variables;
}

function launch(argumentsList, extra) {
  return spawnSync(process.execPath, [LAUNCHER, ...argumentsList], { env: environment(extra), encoding: "utf8" });
}

test("runs the newest installed engine with the same arguments, streams and exit status", () => {
  const claudeCache = join(home, ".claude", "plugins", "cache", "golfo-marketplace", "golfo-kit");
  installPlugin(join(claudeCache, "0.39.0"), "0.39.0", "claude-0.39.0");
  installPlugin(join(claudeCache, "0.40.0"), "0.40.0", "claude-0.40.0");
  installPlugin(join(home, ".hermes", "plugins", "golfo-kit"), "0.38.0", "hermes-0.38.0");

  const result = launch(["plan", "--json"], { FAKE_ENGINE_STATUS: "4" });

  assert.equal(result.status, 4);
  assert.deepEqual(JSON.parse(result.stdout), { engine: "claude-0.40.0", arguments: ["plan", "--json"], provider: "claude" });
  // Python on Windows writes CRLF in text mode; the launcher passes the stream through untouched.
  assert.equal(result.stderr.replace(/\r\n/g, "\n"), "engine progress\n");
});

test("compares versions numerically across providers, so 0.10.0 is newer than 0.9.0", () => {
  installPlugin(join(home, ".codex", "plugins", "cache", "golfo-marketplace", "golfo-kit", "0.9.0"), "0.9.0", "codex-0.9.0");
  installPlugin(join(home, "local", "hermes", "plugins", "golfo-kit"), "0.10.0", "hermes-0.10.0");

  const engine = resolveEngine(environment(), home);

  assert.equal(engine.provider, "hermes");
  assert.equal(engine.version, "0.10.0");
  assert.ok(compareVersions("0.10.0", "0.9.0") > 0);
  assert.ok(compareVersions(null, "0.1.0") < 0);
});

test("reads the marketplace snapshots of Claude Code and Codex when there is no cache", () => {
  installPlugin(join(home, ".codex", ".tmp", "marketplaces", "golfo-marketplace", "plugins", "golfo-kit"), "0.40.0", "codex-snapshot");

  const result = launch(["status"]);

  assert.equal(result.status, 0);
  assert.equal(JSON.parse(result.stdout).engine, "codex-snapshot");
});

test("a local Codex marketplace counts from the source its config names", () => {
  installPlugin(join(home, ".codex", "plugins", "cache", "golfo-marketplace", "golfo-kit", "0.40.0"), "0.40.0", "codex-cache");
  const source = join(home, "clones", "golfo-marketplace");
  installPlugin(join(source, "plugins", "golfo-kit"), "0.41.0", "codex-local");
  writeFileSync(join(home, ".codex", "config.toml"),
    `model = "x"\n\n[marketplaces.golfo-marketplace]\nsource_type = "local"\nsource = ${JSON.stringify(source)}\n`);

  const result = launch(["status"]);

  assert.deepEqual(JSON.parse(result.stdout), { engine: "codex-local", arguments: ["status"], provider: "codex" });
});

test("the provider of the installation reaches the engine, unless the person chose one", () => {
  installPlugin(join(home, "custom-claude", "plugins", "cache", "golfo-marketplace", "golfo-kit", "0.40.0"), "0.40.0", "custom");

  const found = launch(["status"], { CLAUDE_CONFIG_DIR: join(home, "custom-claude") });
  assert.equal(JSON.parse(found.stdout).provider, "claude");

  const chosen = launch(["status"], { CLAUDE_CONFIG_DIR: join(home, "custom-claude"), AGENT_READY_SETUP_ACTIVE_PROVIDER: "codex" });
  assert.equal(JSON.parse(chosen.stdout).provider, "codex");
});

const WAITING_ENGINE = [
  "import os, signal, sys, time",
  "def stop(number, frame):",
  "    open(os.environ['FAKE_ENGINE_MARKER'], 'w').write(str(number))",
  "    sys.exit(130 if number == signal.SIGINT else 143)",
  "signal.signal(signal.SIGINT, stop)",
  "signal.signal(signal.SIGTERM, stop)",
  "print('ready', flush=True)",
  "time.sleep(30)",
].join("\n");

/** Starts the launcher on an engine that waits, sends it one signal and returns its exit status. */
async function cancelWith(signal) {
  const skill = installPlugin(join(home, ".claude", "plugins", "cache", "golfo-marketplace", "golfo-kit", "0.40.0"), "0.40.0", "waiting");
  writeFileSync(join(skill, "scripts", "agent-ready"), WAITING_ENGINE);
  const marker = join(home, "signal");
  const launcher = spawn(process.execPath, [LAUNCHER, "apply"], { env: environment({ FAKE_ENGINE_MARKER: marker }) });
  await new Promise((resolve) => launcher.stdout.once("data", resolve));
  launcher.kill(signal);
  const [status] = await once(launcher, "exit");
  return { status, received: readFileSync(marker, "utf8") };
}

test("a SIGTERM or a SIGINT sent only to the launcher reaches the engine, which exits first", { skip: process.platform === "win32" && "POSIX signals" }, async () => {
  assert.deepEqual(await cancelWith("SIGTERM"), { status: 143, received: String(constants.signals.SIGTERM) });
  assert.deepEqual(await cancelWith("SIGINT"), { status: 130, received: String(constants.signals.SIGINT) });
});

test("AGENT_READY_SETUP_SKILL_DIR wins over every installation and must hold an engine", () => {
  installPlugin(join(home, ".claude", "plugins", "cache", "golfo-marketplace", "golfo-kit", "9.0.0"), "9.0.0", "installed");
  const checkout = installPlugin(join(home, "checkout", "plugins", "golfo-kit"), "0.1.0", "checkout");

  assert.equal(JSON.parse(launch(["check"], { AGENT_READY_SETUP_SKILL_DIR: checkout }).stdout).engine, "checkout");

  const broken = launch(["check"], { AGENT_READY_SETUP_SKILL_DIR: join(home, "missing") });
  assert.equal(broken.status, 1);
  assert.equal(broken.stdout, "");
  assert.match(broken.stderr, /AGENT_READY_SETUP_SKILL_DIR points to .*missing, which has no scripts.agent-ready/);
});

test("without an installed plugin it fails with exit 1 and says how to install one", () => {
  const result = launch(["apply"]);

  assert.equal(result.status, 1);
  assert.equal(result.stdout, "");
  assert.match(result.stderr, /no installed golfo-kit plugin has the agent-ready-setup engine/);
  assert.match(result.stderr, /claude plugin install --scope user golfo-kit@golfo-marketplace/);
  assert.match(result.stderr, /hermes plugins install guidomodarelli\/golfo-marketplace#plugins\/golfo-kit --enable/);

  const version = launch(["--version"]);
  assert.equal(version.status, 0);
  const { version: launcherVersion } = JSON.parse(readFileSync(join(PACKAGE_ROOT, "package.json"), "utf8"));
  assert.match(version.stdout, new RegExp(`^@golfo/agent-ready ${launcherVersion.replaceAll(".", "\\.")}: no installed golfo-kit plugin`));
});

test("an installed golfo-kit older than the CLI is named, with how to update it", () => {
  const skill = installPlugin(join(home, ".hermes", "plugins", "golfo-kit"), "0.36.1", "old");
  rmSync(join(skill, "scripts"), { recursive: true });
  writeFileSync(join(skill, "SKILL.md"), "---\nname: agent-ready-setup\n---\n");

  const result = launch(["doctor"]);

  assert.equal(result.status, 1);
  assert.match(result.stderr, /the installed golfo-kit 0\.36\.1 \(hermes\) predates the agent-ready CLI/);
  assert.match(result.stderr, /hermes plugins update golfo-kit/);
});

test("runs the real engine of this repository", () => {
  const { version } = JSON.parse(readFileSync(join(REPOSITORY_SKILL, "..", "..", "plugin.json"), "utf8"));

  const result = launch(["--version"], { AGENT_READY_SETUP_SKILL_DIR: REPOSITORY_SKILL });

  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), `agent-ready ${version}`);
});
