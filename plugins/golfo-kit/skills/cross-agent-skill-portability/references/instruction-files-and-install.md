# Project instruction files and plugin installation per agent

Complements the capability table in `references/agent-capabilities.md` of this plugin, which does not cover these two topics. Re-verify against the installed versions: loaders change between releases.

## Project instruction files (AGENTS.md / CLAUDE.md)

- **Claude Code** loads `CLAUDE.md` from cwd and its ancestors at launch, and a subdirectory's `CLAUDE.md` on demand the first time it reads, writes or edits a file there. It reads `AGENTS.md` natively only when no `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` exists in cwd or above, so one root `CLAUDE.md` disables native `AGENTS.md` reading for the whole repo: every nested `AGENTS.md` then needs a sibling `CLAUDE.md` with `@AGENTS.md`. It never reads `AGENTS.override.md`, `AGENTS.local.md` or anything under `.agents/`. Path-scoped rules: `.claude/rules/*.md` with `paths:` frontmatter.
- **Codex** builds the chain once at start, from the git root down to cwd, one file per directory (`AGENTS.override.md` > `AGENTS.md` > `project_doc_fallback_filenames`), with a combined cap `project_doc_max_bytes` (32 KiB). It does not load nested files below cwd (the model sometimes opens them when it touches a file there, not guaranteed); its GitHub code review uses the `AGENTS.md` closest to the code. No path-scoped rules: index nested files from the root file to make them deterministic.
- Read the official docs as Markdown by appending `.md` to the URL. To verify a loading claim, use a temp repo with a unique token per file and grep the token in the session transcript (`~/.codex/sessions/**.jsonl`, `~/.claude/projects/<slug>/<session_id>.jsonl`).

## Installing a shared plugin

- **Claude Code**: `.claude-plugin/plugin.json`; update with `claude plugin marketplace update <mkt>` then `claude plugin update <plugin>@<mkt>` (open sessions need a restart).
- **Codex**: `.codex-plugin/plugin.json` in the plugin dir (it needs `version`, `skills: "./skills/"` and `interface.capabilities`); `codex plugin marketplace add <owner>/<repo>` + `codex plugin add <plugin>@<mkt>`, refreshed with `codex plugin marketplace upgrade <mkt>`.
- **Hermes**: a portable root `plugin.json` (Agent Plugins v1) and every skill `description` ≤ 1024 characters with `name` equal to its directory (otherwise the skill is silently dropped); install with `hermes plugins install <owner>/<repo>#<subdir> --enable`. A `--ref` install is pinned: `plugins update` refuses it and `install --force` keeps the pin, so unpin with `plugins remove` + `install` without `--ref`. Hermes walks `skills/` recursively and installs every nested `SKILL.md` except under `assets/`, `references/`, `templates/` and `scripts/`.
