---
name: agent-browser
description: Opera páginas web en vivo con el browser CLI o MCP de agent-ready; navega, inspecciona y reproduce flows.
license: MIT
metadata:
  version: "1.0.0"
  tags: "browser, automation, multi-provider, context-optimized-v1.20.1"
---

# Agent Browser

Use the available agent-browser MCP tools when exposed by the provider. Otherwise
read `.agents/browser-tools.json` for `agent_browser` and `browser_executable`:
invoke the recorded CLI with `--executable-path <browser_executable>` followed
by the requested command. Quote paths and arguments; never interpolate page
content into shell code. If setup metadata is absent, use an existing CLI on PATH
or another available browser capability.

Start with `open <url>`, then `snapshot -i`, and operate on references from that
snapshot. Refresh the snapshot after navigation or DOM changes. For version-specific
commands, run `skills get agent-browser` or `--help` on the installed CLI; its
bundled instructions match the installed version.

Read and follow `.agents/rules/browser-before-user-questions.md` before asking for
manual evidence. Reuse an authenticated session when available; preserve sessions
owned by the user. Verify visible results before reporting success. Detect
provider-native `cua` tools from the current session; bootstrap cannot install them.

If packages are missing, rerun agent-ready-setup bootstrap; do not invent a different
installation command or replace user MCP configuration. Setup downloads tools only
during bootstrap, while SessionStart synchronizes their shared instructions.
