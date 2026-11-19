# Porting Claude Code plugins to Hermes (and mirroring back)

Maps Claude Code hooks, skills and MCP servers onto Hermes MCP config and a native Hermes plugin, and the reverse direction with Claude Code user hooks.

## Claude Code → Hermes

1. Inspect the source: `~/.claude/settings.json` (`enabledPlugins`), `~/.claude.json` (`mcpServers`) and `~/.claude/plugins/cache/<mkt>/<plugin>/<ver>/` (`hooks/hooks.json`, `scripts/`, `skills/`).
2. MCP server: `yes | hermes mcp add <name> --command <exe> --args ...` (non-interactive; `--args` must be last). Tools become `mcp_<server>_<tool>`.
3. Hooks and always-on skills: write a native plugin in `$HERMES_HOME/plugins/<name>/` (`plugin.yaml` + `__init__.py` with `register(ctx)`), then `hermes plugins doctor <dir>` and `hermes plugins enable <name>`. The gateway hot-reloads hooks; system prompt sections apply on the next session.
4. Skills that only need to be read: package them as an Agent Plugins v1 plugin (portable root `plugin.json`) instead of a native plugin; see [instruction-files-and-install.md](instruction-files-and-install.md).

### Event mapping

- Always-on `SKILL.md` → `ctx.register_system_prompt_section(id, text_or_callable, max_chars<=4000)`.
- `SessionStart` → `on_session_start` (plus lazy init in `pre_llm_call`; ordering is not guaranteed).
- `UserPromptSubmit` / `additionalContext` → `pre_llm_call` returning `{"context": ...}` (appended to the user message).
- `SessionStart` with matcher `compact` → `post_compaction` (observer: set a flag, inject on the next `pre_llm_call`).
- `SubagentStop` → `subagent_stop` (`parent_session_id`, `child_summary`).
- `SessionEnd` → `on_session_finalize` + `on_session_reset` (`old_session_id`).
- `PreToolUse` that rewrites tool input (`updatedInput`) → `pre_tool_call` returning `{"action": "modify", "args": {...partial}}`, shallow-merged into the args (undocumented in `hooks.md`, present in `hermes_cli/plugins.py`).
- Tracking what the agent modified → `post_tool_call`: `write_file`/`patch` `path`; for `terminal`, the `workdir` or a leading `cd` ONLY when the command matches a mutating regex (git commit/merge/checkout/push, package install/add, mkdir/mv/cp/rm/touch/tee, `sed -i`, a `>` redirect not to `/dev/null`). Inject mid-turn information with `transform_tool_result` (append to the result string).

### Pitfalls

- Keep every hook fail-open (try/except, short HTTP timeouts); use the standard library (`urllib`), no new dependencies.
- Test by importing the module with `importlib` and calling the hooks directly with a fake session id; on Windows pass native `C:/...` paths to Python, not `/tmp`.
- Never treat a bare `cd` or read command as "working in" a repo: inspecting another repo (ls, cat, git log, grep) would hijack the routing of later writes to it. Unit-test the mutating regex against read-only and mutating samples before enabling.
- After editing a plugin: `hermes plugins doctor <dir>`, then `hermes plugins disable <name>` + `enable <name>` to hot-reload hooks in the running gateway.
- Subagents (`delegate_task`) trigger `on_session_start` for their own session: end it in `subagent_stop` (`child_session_id`), or the backend accumulates stale active sessions.
- Make plugins portable: resolve binaries through PATH (`shutil.which`) with an OS-aware fallback, and set the MCP `command` to the bare binary name (`hermes config set mcp_servers.<n>.command <bin>`) instead of an absolute Windows path.

## Hermes → Claude Code (mirroring a behavior back)

Add user-level hooks; never edit the plugin cache, which is overwritten on plugin updates.

1. Keep the script in the user's versioned dotfiles or config repo if they have one (ask where), not loose in `~/.claude/hooks/`: `<repo>/scripts/<area>/<name>.mjs` plus a POSIX `<name>.sh` launcher, and `settings.json` calls `sh "<path>/<name>.sh" pre|post|end`. The launcher picks `bun`, else `node`, else known bun install paths, else drains stdin and exits 0. One script, mode via argv, reading the hook JSON from stdin and printing nothing to abstain. Never hardcode `C:/Users/...`, `.exe` or `;`-separated lists: use `os.homedir()`, PATH lookup and `path.delimiter`.
   - In Git Bash, convert the script path with `cygpath -m` before handing it to native bun or node: they cannot open `/c/...` paths (the hook fails with "Module not found").
   - Translate MSYS `/c/...` paths to `C:/...` only when `process.platform === "win32"`; on Linux they are real paths.
2. Back up `~/.claude/settings.json`, then add entries under `hooks.PreToolUse` / `PostToolUse` / `SessionEnd` with a JSON-aware script (idempotent: drop old entries containing the script name before appending).
3. `PostToolUse` can return `hookSpecificOutput.additionalContext` to tell Claude something mid-turn (the equivalent of Hermes `transform_tool_result`).
4. Test each mode by piping fake payloads into the script, then one real `claude -p '<scripted steps>' --allowedTools ...` run from a neutral cwd, and clean up any test rows.

- When a plugin hook already returns `updatedInput` for the same tool, Claude Code runs matching hooks in parallel and keeps the rewrite of the hook that FINISHES LAST (each hook sees the original input). So your hook must produce the full final input itself: call the plugin's own hook command with your adjusted payload, merge your fields into its `updatedInput`, then wait a margin (~400 ms) before printing so yours wins. Only emit when you actually need to override; otherwise abstain.
- Mirror the plugin's output shape exactly (for example no `permissionDecision` if the plugin omits it) so the permission flow is unchanged; pass a plugin `deny` through with your reason prefixed.
