# Engram (Gentleman-Programming/engram) — integration notes

## HTTP API (local server, default 127.0.0.1:7437)
- `GET /health` -> `{service: engram, status: ok, instance_id}`; start with `engram serve` (detached) if down.
- `GET /project/current?cwd=<dir>` -> `{project, project_source, project_path}`; sources: config, git_remote, git_root, git_child, dir_basename. A home dir with one child repo auto-promotes that repo (git_child).
- `POST /sessions {id, project, directory, ownership_mode: project_owned, resume: true}`; `POST /sessions/{id}/end`.
- `GET /context?project=..&compact=1&pinned=N&max_bytes=N` -> `{context}`.
- `POST /prompts/capture-decision` accepts only `source: "claude-code"`; then `POST /prompts {session_id, project, content}`.
- `POST /observations/passive {session_id, content, project, source}`.
- Deleting via HTTP needs a token; use CLI instead: `engram delete <obs_id> --hard`, `engram delete session <id>`.

## MCP write tools
- `mem_save`, `mem_save_prompt`, `mem_session_summary` take `project` + `session_id`; `mem_capture_passive`, `mem_judge`, `mem_compare` take `session_id`. Explicit session ids must be registered first (`POST /sessions`).
- Explicit `project` is accepted only when the `session_id` is registered for that same project; a write with a session owned by another project fails with `session_project_mismatch`. Per-project routing therefore needs satellite sessions `<sid>@<project>` registered for the target repo, with both `session_id` and `project` injected (Hermes: `pre_tool_call` modify).
- Claude Code: the engram plugin's PreToolUse (`engram hook claude-pre-tool-use`) always rebinds `session_id` to Claude's session (project = Claude's cwd). To route cross-repo, run that same command from your own hook with `session_id=<sid>@<project>` and `cwd=<repo dir>` in the payload (it registers/confirms the satellite), add `project`, and win the last-finisher race (see `porting-claude-plugins.md`, "Hermes → Claude Code"). End satellites on `SessionEnd` (`POST /sessions/<id>/end`).
- Routing source = last repo MODIFIED (Edit/Write/patch path, or mutating shell command in its leading `cd`/cwd); folder names/paths passed as `project` are translated to the Engram name via `/project/current`.
- Accept only `config`, `git_remote`, `git_root`, `process_override` as routing sources. Reject `dir_basename` (not a repo) and `git_child` — it means the path is a non-repo folder that merely contains one repo (e.g. editing `$HERMES_HOME/SOUL.md` resolves to the bundled `hermes-agent` checkout), so routing would hijack writes to an unrelated project.
- Engram project names can differ from folder names; always resolve paths through `/project/current`, never guess from the folder.
- End-to-end test: spawn `engram mcp --tools=agent` over stdio JSON-RPC (initialize, notifications/initialized, tools/call) from Python, then clean up test rows with the CLI deletes.

## Renaming a project (folder/remote renamed but Engram keeps the old name)
- Cause: Engram pins the first name in `<repo>/.git/engram-project-identity.json` (`{version, id, project}`), surviving remote renames. `engram projects merge` only accepts separator/case variants, so unrelated renames have no CLI path.
- Procedure (confirm with user first; check `sync_enrolled_projects` is empty = no cloud sync):
  1. Online backup of `~/.engram/engram.db` with sqlite3 `backup()` into `~/.engram/backups/`.
  2. One `BEGIN IMMEDIATE` transaction: update `project` in observations, sessions, user_prompts, prompt_tombstones, sync_delete_tombstones, sync_mutations, plus `local_creation_project` in sessions/user_prompts.
  3. Rename session ids embedding the name (`manual-save-<old>`, `migration-<old>`) and their `session_id` refs in observations, user_prompts, memory_relations, sync_delete_tombstones — otherwise doctor flags manual_session_name_project_mismatch.
  4. `INSERT INTO observations_fts(observations_fts) VALUES('rebuild')`, commit.
  5. Rewrite the `project` field in each repo's identity JSON (keep `id`).
  6. Verify: `/project/current` per repo, `/projects`, a scoped `/search`, and `engram doctor` all `[ok]`.
- Renames live in Engram itself, so they apply to every agent sharing the DB (Claude Code, Hermes, Codex).

## Updating old memory CONTENT after a rename
- Find candidates with a regex over title/topic_key/content of non-deleted observations; exclude false positives (substrings inside ordinary words, e.g. "astra" in "arrastrar").
- Do not blind-replace: memories whose subject is a rename/migration keep historical names (rewriting falsifies history) and get a top line `> Nombres actuales: old → new, ...`; current-state memories (conventions, how-tos, architecture, paths) get names replaced; session summaries get the title renamed and paths/next steps updated. Gather the true current names from the repos first (package names, env prefixes, config filenames, plugin names) and give them to the rewriters.
- For many memories, split into batches and delegate rewrites to subagents that only write `outN.json` (`{id,title,topic_key,content,changed,note}`) — never the DB.
- Apply with a script that diffs against the originals, prints a dry run, then calls MCP `mem_update` (`id`, `expected_project`, changed fields) on `--apply`; `mem_update` keeps prior versions in `observation_versions`, so it is reversible.
