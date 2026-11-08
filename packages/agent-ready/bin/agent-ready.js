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
  const child = spawn(command, [...pythonArguments, entryPoint, ...engineArguments], { stdio: "inherit" });
  child.on("error", (error) => {
    if (error.code === "ENOENT") {
      runEngine(engine, engineArguments, pythonIndex + 1);
      return;
    }
    fail(`could not start ${command}: ${error.message}`);
  });
  child.on("exit", (status, signal) => {
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
  // Ctrl+C reaches the engine too: it answers with exit 130 and nothing written, so the launcher waits for it.
  process.on("SIGINT", () => {});
  runEngine(engine, engineArguments);
}

main();
