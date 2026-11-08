#!/usr/bin/env node
/**
 * agent-ready: puts the CLI of agent-ready-setup on the PATH of a person.
 *
 * It finds the engine of the installed golfo-kit plugin and runs its own CLI with the
 * same arguments, standard streams and exit status. Every subcommand, flag and question
 * belongs to the engine; the launcher only adds the error for a missing engine or Python.
 */
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { constants, homedir } from "node:os";
import { join } from "node:path";
import {
  ENGINE_ENTRY_POINT,
  EngineError,
  INSTALL_HINT,
  UPDATE_HINT,
  newestInstallationWithoutEngine,
  resolveEngine,
} from "../lib/resolve-engine.js";

const CLI_NAME = "agent-ready";
const EXIT_FAILED = 1;
const SIGNAL_EXIT_BASE = 128;
// Windows runs the Microsoft Store alias, which exits with 9009, when Python is not installed.
const WINDOWS_STORE_ALIAS_STATUS = 9009;
const PYTHON_COMMANDS = process.platform === "win32" ? [["python3"], ["py", "-3"], ["python"]] : [["python3"], ["python"]];
const INFORMATION_FLAGS = new Set(["-h", "--help", "--version"]);
// The engine reads the provider from here when --provider is not passed; the installation tells which one it is.
const PROVIDER_VARIABLE = "AGENT_READY_SETUP_ACTIVE_PROVIDER";
const ENGINE_PROVIDERS = new Set(["claude", "codex"]);
const FORWARDED_SIGNALS = ["SIGINT", "SIGTERM", "SIGHUP"];
// A terminal Ctrl+C reaches the engine on its own. Waiting this long before forwarding one keeps it
// from being interrupted twice, while a SIGINT sent only to the launcher still reaches it.
const INTERRUPT_FORWARD_DELAY_MS = 1000;

let runningEngine = null;
let pendingInterrupt = null;

/** Passes a cancellation on to the engine, which decides what to keep, and waits for it. */
function forwardSignal(signal) {
  if (!runningEngine || runningEngine.exitCode !== null || runningEngine.signalCode !== null) {
    return;
  }
  if (signal !== "SIGINT") {
    runningEngine.kill(signal);
    return;
  }
  clearTimeout(pendingInterrupt);
  pendingInterrupt = setTimeout(() => runningEngine?.kill("SIGINT"), INTERRUPT_FORWARD_DELAY_MS);
}

/** The environment of the engine: the provider of the installation, unless the person chose one. */
function engineEnvironment(engine) {
  const environment = { ...process.env };
  if (!environment[PROVIDER_VARIABLE] && ENGINE_PROVIDERS.has(engine.provider)) {
    environment[PROVIDER_VARIABLE] = engine.provider;
  }
  return environment;
}

function launcherVersion() {
  return JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")).version;
}

function fail(message) {
  process.stderr.write(`${CLI_NAME}: ${message}\n`);
  process.exitCode = EXIT_FAILED;
}

/** Runs the engine with the first Python that exists; the engine needs Python 3.8 or newer. */
function runEngine(engine, engineArguments, pythonIndex = 0) {
  if (pythonIndex >= PYTHON_COMMANDS.length) {
    fail("the engine needs Python 3.8 or newer; install it and make python3 reachable from PATH");
    return;
  }
  const [command, ...pythonArguments] = PYTHON_COMMANDS[pythonIndex];
  const entryPoint = join(engine.skillDirectory, ENGINE_ENTRY_POINT);
  const child = spawn(command, [...pythonArguments, entryPoint, ...engineArguments], {
    stdio: "inherit",
    env: engineEnvironment(engine),
  });
  runningEngine = child;
  child.on("error", (error) => {
    if (error.code === "ENOENT") {
      runEngine(engine, engineArguments, pythonIndex + 1);
      return;
    }
    fail(`could not start ${command}: ${error.message}`);
  });
  child.on("exit", (status, signal) => {
    clearTimeout(pendingInterrupt);
    if (process.platform === "win32" && status === WINDOWS_STORE_ALIAS_STATUS) {
      runEngine(engine, engineArguments, pythonIndex + 1);
      return;
    }
    process.exitCode = signal ? SIGNAL_EXIT_BASE + (constants.signals[signal] ?? 0) : status ?? EXIT_FAILED;
  });
}

function main() {
  const engineArguments = process.argv.slice(2);
  let engine;
  try {
    engine = resolveEngine(process.env, homedir());
  } catch (error) {
    if (error instanceof EngineError) {
      fail(error.message);
      return;
    }
    throw error;
  }
  if (!engine) {
    const outdated = newestInstallationWithoutEngine(process.env, homedir());
    const problem = outdated
      ? `the installed golfo-kit ${outdated.version ?? "(unknown version)"} (${outdated.provider}) predates the agent-ready CLI.\n${UPDATE_HINT}`
      : `no installed golfo-kit plugin has the agent-ready-setup engine.\n${INSTALL_HINT}`;
    if (engineArguments.some((argument) => INFORMATION_FLAGS.has(argument))) {
      process.stdout.write(`@golfo/agent-ready ${launcherVersion()}: ${problem}\n`);
      return;
    }
    fail(problem);
    return;
  }
  // The engine answers a cancellation itself (exit 130, nothing left half written); the launcher waits for it.
  for (const signal of FORWARDED_SIGNALS) {
    process.on(signal, () => forwardSignal(signal));
  }
  runEngine(engine, engineArguments);
}

main();
