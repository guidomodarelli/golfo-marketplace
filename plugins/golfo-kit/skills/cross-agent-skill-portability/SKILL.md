---
name: cross-agent-skill-portability
description: "Makes skills, plugins, hooks and MCP servers work across Claude Code, Codex and Hermes: audits what each agent really supports, maps every feature to a native tool or an equivalent mechanism, adapts the skill with runtime detection, ports Claude Code plugins (hooks, skills, MCP) to Hermes native plugins or mirrors a Hermes behavior back into Claude Code hooks, and writes an honest compatibility report. Use whenever someone asks to port a Claude plugin or skill to Hermes or Codex, make a skill or plugin multi-agent, audit which skills work in each agent, update a compatibility report, decide where repo knowledge or a repo-local skill should live so every agent sees it, or says a feature is incompatible because another agent lacks the same tool."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "agent-tooling"
  tags: "portability, claude-code, codex, hermes, plugins, hooks, mcp, compatibility"
  command: "/cross-agent-skill-portability"
---

# Cross-agent skill portability (Claude Code, Codex, Hermes, others)

Audit or adapt a skill set (for example the golfo plugins) so each feature runs on whichever agent is active, using that agent's own mechanism, and port plugins between agents. Inventory real capabilities, map equivalents, adapt before disabling.

The detection signals, the capability table (questions, monitoring, cron, subagents, read-only reviewer, widgets, browser, MCP, hooks, config paths, invoking skills, notifications) and the runtime protocol live in one place: [`references/agent-capabilities.md`](../../references/agent-capabilities.md) of this plugin. Read it before classifying any feature and do not copy its rows into the skill you adapt: link it.

## Rules that always apply

- A feature is NOT incompatible because the original tool is missing. Per feature and per agent: (1) the same feature natively, (2) an equivalent with a different mechanism (plugin, MCP, CLI, workflow, external CLI, OS scheduler, CI), (3) adapt to it, (4) disable only when no viable alternative exists, listing what was investigated. Typical trap: Claude's `mcp__visualize__show_widget` and Codex's `visualize` plugin solve the same need with different mechanics.
- Decide by the capabilities present in the session at runtime, never by agent name. Environment variables are hints only and leak into nested agents (a Claude launched from Hermes sees `HERMES_*` too).
- The compatibility report describes; it is not the switch. Skills still check tools at runtime, and disabled branches are blocked in the skill or script, not just listed.
- Status honesty: `compatible`/`adapted` only with a real run on that agent; documented or simulated-eval evidence stays `unverified`. Distinguish "capability confirmed absent" from "not verified". Keep partial skills partial, never `incompatible` while useful parts remain. A user's report that something works is a lead to implement, not test evidence.
- No unbounded loops: replacements for monitors and crons keep max iterations, timeouts, cancellation and the original guarantees (dedup, round caps, merge gates).
- Where knowledge lives: knowledge about a repo (its gotchas, commands, release rules) must be readable by every agent that works in it, so it goes in the repo itself (`AGENTS.md` or repo-local skills), not in one agent's private skill dir — a Hermes-only skill leaves Claude rediscovering the same pitfall. Keep in an agent's private skills only what is about that agent itself. Before proposing a location, tell the user which agents will and will not see it.

## Repo-local skills shared by every agent

- Canonical dir: `<repo>/.agents/skills/<name>/SKILL.md`. Codex and Hermes read `.agents/skills` natively; Claude Code reads only `.claude/skills`, so add a git symlink `.claude/skills/<name> -> ../../.agents/skills/<name>`. No `.hermes/skills` link is needed.
- Hermes project discovery is trust-gated and cwd-bound: it loads `<root>/.agents/skills` and `<root>/.hermes/skills` only for sessions started inside that git checkout, after `hermes skills trust` (stored in `skills.trusted_project_dirs`). Gateway sessions (Discord, Telegram) start outside the repo, so also list the repo's `.agents/skills` in `skills.external_dirs` (`hermes config set`, no trust needed).
- Windows symlinks: with `core.symlinks=false` git checks a symlink out as a text file holding the path, and Claude does not follow it. Set `git config --global core.symlinks true`; creating real symlinks unelevated also needs Windows Developer Mode. Verify with `git ls-files -s <link>` (mode `120000`) and `ls -la` showing `->`.
- How each agent loads `AGENTS.md`/`CLAUDE.md` (root and nested) and how to install a plugin in each agent: [references/instruction-files-and-install.md](references/instruction-files-and-install.md).

## Procedure: audit or adapt a skill set

1. **Inventory real capabilities before classifying anything**, from config and installed files, not memory:
   - Codex: every `[plugins."..."] enabled = true` in `~/.codex/config.toml`; each `~/.codex/plugins/cache/<mkt>/<plugin>/<ver>/.codex-plugin/plugin.json` and its `skills/*/SKILL.md`; `[mcp_servers]`; `codex --help` / `codex exec --help`. Note what works in the CLI versus only in the desktop app.
   - Hermes: the session tool list and the docs; `hermes plugins list`; plugin skills load as `agent-plugin-<name>-<hash>:<skill>`.
   - Claude Code: the session tools (deferred ones included); `~/.claude/plugins/installed_plugins.json`; `claude -p` for isolated runs.
   - External: any agent with a terminal can call another installed CLI (for example `claude -p --tools "Read,Grep,Glob"` as a read-only isolated reviewer).
2. **Audit every skill**, including implicit needs (a browser, screenshots, asking the user, subagents, waiting or polling, notifications, visual output, config paths), not only the skills that name a tool.
3. **Per feature**: direct → alternatives (with source) → adapt or disable; record `alternatives_investigated` and `resolution: native|alternative|disabled`.
4. **Implement in the skill**: a short "agent compatibility" section that links the shared capability reference and lists only that skill's own adaptations, runtime detection by tool presence, and a closing "Limitaciones del agente" report of what was skipped and why.
5. **Verify with real runs** where possible (`codex exec` in a temp dir, `hermes chat -q`, `claude -p`). Evals that only simulate another agent stay `unverified` evidence.
6. **Before reporting** (yours or a delegated child's), re-check the result against each numbered criterion the user gave and list explicitly what is still unadapted or unverified.

## Procedure: port a Claude Code plugin to Hermes (or back)

Porting hooks, skills and MCP servers from a Claude Code plugin into a Hermes native plugin, the hook event mapping, the pitfalls, and mirroring a Hermes behavior back into Claude Code user hooks: [references/porting-claude-plugins.md](references/porting-claude-plugins.md). Read it before writing any hook or plugin code. For a memory backend such as Engram (session binding, per-project routing, renaming projects), also read [references/engram-integration.md](references/engram-integration.md).

Changes to a Hermes plugin do not affect Claude Code, and the reverse: say so explicitly when the user asks. Shared backends (one MCP server, one database) do carry over.

## Report

Close with, per feature: native / alternative X / disabled because Y, the alternatives investigated, and the evidence level (`verified` with the run, or `unverified`). Then list what remains unadapted or unverified.
