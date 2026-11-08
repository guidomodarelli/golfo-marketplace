#!/usr/bin/env bats
# The cache of the AI reviews: one entry per unit (a pair of rules or skills, or AGENTS.md
# against its rules), keyed by everything that can change the verdict, written atomically
# under a lock, pruned, read by status without the provider, and switched by the reviews
# options that the last apply records for the hooks.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  hook="$skill_dir/assets/common/hooks/check-harness-consistency.sh"
  cache_script="$skill_dir/assets/common/hooks/review-cache.py"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  export XDG_CONFIG_HOME="$test_root/config"
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_ORGANIZATION_CONFIG="$test_root/organization.json"
  export GIT_CONFIG_GLOBAL="$test_root/gitconfig"
  git config --global core.autocrlf false
  unset AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_REVIEW_MODE AGENT_READY_SETUP_MERGE_MODEL
  export FAKE_CALLS="$test_root/provider-calls.log"
  export FAKE_INPUT="$test_root/provider-input.log"
  export FAKE_ARGUMENTS="$test_root/provider-arguments.log"
  export FAKE_RESPONSE="$test_root/provider-response.json"
  export FAKE_ARGV="$test_root/provider-argv.bin"
  : > "$FAKE_CALLS"
  printf '%s\n' '{"findings": []}' > "$FAKE_RESPONSE"
  # A provider that counts its calls, keeps the documents and the exact arguments it received
  # (NUL-separated) and answers FAKE_RESPONSE: on stdout like claude, or in the
  # --output-last-message file like codex exec.
  for provider_cli in claude codex; do
    cat > "$fake_bin/$provider_cli" <<'EOF'
#!/bin/bash
cat > "$FAKE_INPUT"
basename "$0" >> "$FAKE_CALLS"
printf '%s\n' "$(basename "$0") $*" >> "$FAKE_ARGUMENTS"
printf '%s\0' "$@" > "$FAKE_ARGV"
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --output-last-message ]]; then
    cat "$FAKE_RESPONSE" > "$2"
    exit 0
  fi
  shift
done
printf '{"structured_output": %s}\n' "$(cat "$FAKE_RESPONSE")"
EOF
    chmod +x "$fake_bin/$provider_cli"
  done
  git -C "$project_dir" init -q
  cd "$project_dir"
  mkdir -p .agents/rules .agents/skills/demo
  printf '# Testing\nMock every dependency.\n' > .agents/rules/testing.md
  printf '# Style\nNever mock dependencies.\n' > .agents/rules/style.md
  printf -- '---\nname: demo\n---\nUse the test runner of the project.\n' > .agents/skills/demo/SKILL.md
}

teardown() {
  cd "$repository_root"
  rm -rf "$test_root"
}

calls() {
  wc -l < "$FAKE_CALLS" | tr -d ' '
}

edit_payload() {
  printf '{"tool_input":{"file_path":"%s"}}' "$1"
}

run_hook() {
  run env PATH="$fake_bin:$PATH" bash "$hook" <<< "$(edit_payload "$1")"
}

run_cli() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready" "$@"
}

# Two findings of the pair style.md <-> testing.md, each quoting its own lines.
two_findings() {
  printf '%s\n' '{"findings": [
    {"pair": 1, "lines": ["Never mock dependencies.", "Mock every dependency."], "kind": "contradiction", "text": "Mocks are both required and forbidden."},
    {"pair": 1, "lines": ["# Style", "# Testing"], "kind": "inconsistency", "text": "The headings use different conventions."}]}' > "$FAKE_RESPONSE"
}

# Id of the finding whose text starts with $1, from review list --json.
finding_id_of() {
  python3 -c 'import json,sys; print(next(f["id"] for f in json.loads(sys.argv[1])["findings"] if f["text"].startswith(sys.argv[2])))' \
    "$(PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready" review list --json)" "$1" | tr -d '\r'
}

decision_value() {
  python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(eval(sys.argv[2], {"data": data}))' \
    .agents/agent-ready.reviews.json "$1" | tr -d '\r'
}

cache_file() {
  printf '%s/.git/info/agent-ready/reviews.json' "$project_dir"
}

cache_value() {
  python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(eval(sys.argv[2], {"data": data}))' \
    "$(cache_file)" "$1" | tr -d '\r'
}

# The argument the provider received right after $1, exactly as it arrived.
argument_after() {
  python3 -c 'import sys; arguments = open(sys.argv[1], "rb").read().split(b"\0")[:-1]; sys.stdout.write(arguments[arguments.index(sys.argv[2].encode()) + 1].decode())' \
    "$FAKE_ARGV" "$1"
}

write_settings() {
  python3 -B - "$skill_dir" "$1" "$2" "$3" <<'PY'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("review_cache", os.path.join(sys.argv[1], "assets/common/hooks/review-cache.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ttl = None if sys.argv[4] == "none" else int(sys.argv[4])
module.ReviewCache(".").write_settings(sys.argv[2] == "true", sys.argv[3] == "true", ttl)
PY
}

@test "the hook reviews only the pairs of the edited file, in one call, and reuses them until a file changes" {
  run_hook .agents/rules/testing.md
  [ "$status" -eq 0 ]
  [ "$(calls)" -eq 1 ]
  [[ "$output" == *"reviewing 2 of 2 pairs with claude (0 from the cache)"* ]]
  grep -Fq '<document path=".agents/rules/style.md">' "$FAKE_INPUT"
  # Each argument arrives whole, also the ones with double quotes, which a native Windows
  # process starting bash.exe would split.
  argument_after --json-schema | python3 -c 'import json, sys; assert json.load(sys.stdin)["required"] == ["findings"]'
  [ "$(argument_after --tools)" = "" ]
  [ "$(argument_after --effort)" = medium ]
  # The pairs travel on stdin with the documents, never in an argument that a bulk edit could overflow.
  grep -Fxq '1. .agents/rules/style.md <-> .agents/rules/testing.md' "$FAKE_INPUT"
  [[ "$(argument_after -p)" != *"<->"* ]]

  run_hook .agents/rules/testing.md
  [ "$(calls)" -eq 1 ]
  [[ "$output" == *"reviewing 0 of 2 pairs with claude (2 from the cache)"* ]]

  printf 'Prefer fakes over mocks.\n' >> .agents/skills/demo/SKILL.md
  run_hook .agents/skills/demo/SKILL.md
  [ "$(calls)" -eq 2 ]
  [[ "$output" == *"reviewing 2 of 2 pairs"* ]]

  printf 'Name tests after the behavior.\n' >> .agents/rules/style.md
  run_hook .agents/rules/style.md
  [ "$(calls)" -eq 3 ]
  # Only the two pairs of style.md go to the provider; testing.md <-> SKILL.md stays cached.
  [[ "$output" == *"reviewing 2 of 2 pairs"* ]]
  [ "$(cache_value 'len(data["entries"])')" -eq 3 ]
}

@test "pairs the provider did not answer leave the check incomplete, never clean" {
  printf '%s\n' 'not json' > "$FAKE_RESPONSE"
  run_hook .agents/rules/testing.md
  [ "$status" -eq 0 ]
  [[ "$output" == *"Check incomplete: 2 of 2 pairs were not reviewed."* ]]
  [[ "$output" != *"No contradictions found."* ]]
  [ ! -e "$(cache_file)" ]
}

@test "a finding is kept per pair and status shows it without calling the provider" {
  printf '%s\n' '{"findings": [{"pair": 1, "lines": ["Never mock dependencies.", "Mock every dependency."], "kind": "contradiction", "text": "One rule mocks every dependency and the other forbids mocks."}]}' > "$FAKE_RESPONSE"
  run_hook .agents/rules/testing.md
  [[ "$output" == *"! ["*"] .agents/rules/style.md <-> .agents/rules/testing.md: One rule mocks every dependency"* ]]
  [ "$(calls)" -eq 1 ]

  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --format json
  [ "$(calls)" -eq 1 ]
  [ "$(python3 -c 'import json,sys; r=json.loads(sys.argv[1])["reviews"]; print(r["units"], len(r["findings"]), r["findings"][0]["kind"])' "$output" | tr -d '\r')" = "2 1 contradiction" ]

  run env PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready-state.py" status --project .
  [[ "$output" == *"AI reviews: 1 known finding(s) in 2 reviewed unit(s), from the cache:"* ]]
  [[ "$output" == *"! ["*"] .agents/rules/style.md <-> .agents/rules/testing.md: One rule mocks every dependency"* ]]

  printf 'Mock only the network.\n' >> .agents/rules/testing.md
  run --separate-stderr python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --format json
  [ "$(python3 -c 'import json,sys; r=json.loads(sys.argv[1])["reviews"]; print(r["units"], r["stale"], len(r["findings"]))' "$output" | tr -d '\r')" = "0 2 0" ]
}

@test "the key changes with the content, the check version, the model and the engine, and nothing else" {
  run python3 -B - "$cache_script" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("review_cache", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
base = dict(check="harness-consistency", version=1, provider="claude", model="m", engine="1.0.0", contents={"a.md": "x\n", "b.md": "y\n"})
key = lambda **change: module.unit_key(**dict(base, **change))
assert key() == key(contents={"b.md": "y\r\n".replace("\r\n", "\n"), "a.md": "x\n"}), "order and line endings do not matter"
for change in ({"version": 2}, {"model": "other"}, {"engine": "1.1.0"}, {"provider": "codex"}, {"contents": {"a.md": "x\n", "b.md": "z\n"}}):
    assert key(**change) != key(), change
assert module.unit_id("c", ["b.md", "a.md"]) == module.unit_id("c", ["a.md", "b.md"])
print("ok")
PY
  [ "$status" -eq 0 ]
  [ "$output" = "ok" ]

  run_hook .agents/rules/testing.md
  [ "$(calls)" -eq 1 ]
  mkdir -p .agents
  printf '%s\n' '{"generator": {"version": "9.9.9"}, "assets": {}}' > .agents/agent-ready.lock.json
  run_hook .agents/rules/testing.md
  [ "$(calls)" -eq 2 ]
  [[ "$output" == *"reviewing 2 of 2 pairs"* ]]
}

@test "reviews.enabled false skips the hook and reviews.cache false reviews every time without storing" {
  write_settings false true none
  run_hook .agents/rules/testing.md
  [ "$status" -eq 0 ]
  [[ "$output" == *"AI reviews are off (reviews.enabled: false); consistency check skipped."* ]]
  [ "$(calls)" -eq 0 ]

  write_settings true false none
  run_hook .agents/rules/testing.md
  run_hook .agents/rules/testing.md
  [ "$(calls)" -eq 2 ]
  [ "$(cache_value 'len(data["entries"])')" -eq 0 ]
}

@test "merge-instructions applies the managed block without the AI review when reviews are off" {
  printf '%s\n' '# Project' > AGENTS.md
  write_settings false true none
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/merge-instructions.sh" \
    --provider claude --stack node --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *"AI reviews are off (reviews.enabled: false); applying the managed block without redundancy review."* ]]
  [ "$(calls)" -eq 0 ]
  grep -Fxq '<!-- BEGIN AGENT-READY MANAGED -->' AGENTS.md

  # Without the cache, every sync reviews AGENTS.md again and nothing is stored.
  write_settings true false none
  printf '%s\n' '{"project_content": "# Project\n\n<!-- AGENT-READY MANAGED BLOCK -->", "removed": [], "inconsistencies": [], "reason": "Nothing to remove."}' > "$FAKE_RESPONSE"
  for attempt in 1 2; do
    run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/merge-instructions.sh" \
      --provider claude --stack node --skill-dir "$skill_dir"
    [ "$status" -eq 0 ]
  done
  [ "$(calls)" -eq 2 ]
  [ "$(cache_value 'len(data["entries"])')" -eq 0 ]
}

@test "an entry older than reviews.ttl hours is reviewed again" {
  run_hook .agents/rules/testing.md
  [ "$(calls)" -eq 1 ]
  write_settings true true 1
  python3 - "$(cache_file)" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
for entry in data["entries"].values():
    entry["checkedAt"] = "2000-01-01T00:00:00Z"
json.dump(data, open(path, "w", encoding="utf-8"))
PY
  run_hook .agents/rules/testing.md
  [ "$(calls)" -eq 2 ]
}

@test "entries of deleted files are pruned on the next write" {
  run_hook .agents/rules/testing.md
  [ "$(cache_value 'len(data["entries"])')" -eq 2 ]
  rm .agents/skills/demo/SKILL.md
  printf 'Keep tests fast.\n' >> .agents/rules/style.md
  run_hook .agents/rules/style.md
  [ "$(cache_value 'sorted(data["entries"])')" = "['harness-consistency:.agents/rules/style.md|.agents/rules/testing.md']" ]
}

@test "processes that write the cache at the same time keep it valid and lose no entry" {
  for index in $(seq 1 8); do
    printf 'rule %s\n' "$index" > "rule-$index.md"
    printf '%s\n' '{"findings": []}' > "result-$index.json"
  done
  writer_pids=()
  for index in $(seq 1 8); do
    python3 -B "$cache_script" store --project . --check concurrency --version 1 --provider claude --model m \
      --file "rule-$index.md" "rule-$index.md" --result "result-$index.json" &
    writer_pids+=("$!")
  done
  # Only the writers: a bare wait would also wait for the timer of BATS_TEST_TIMEOUT.
  wait "${writer_pids[@]}"
  [ "$(cache_value 'len(data["entries"])')" -eq 8 ]
  [ ! -e .git/info/agent-ready/reviews.lock ]
}

@test "a cache directory that cannot be written fails fast instead of waiting for the lock" {
  run python3 -B - "$cache_script" <<'PY'
import importlib.util, os, sys, time
spec = importlib.util.spec_from_file_location("review_cache", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def denied(path, *arguments, **keywords):
    raise PermissionError(13, "Permission denied", path)
module.os.mkdir = denied
started = time.monotonic()
try:
    module.ReviewCache(".").store({"unit": {"files": {}, "findings": []}})
except PermissionError:
    elapsed = time.monotonic() - started
    print("denied in time" if elapsed < module.LOCK_WAIT_SECONDS else f"denied after {elapsed:.0f}s")
PY
  [ "$status" -eq 0 ]
  [ "$output" = "denied in time" ]
}

@test "a lookup prints ASCII JSON, so a legacy code page never turns a cached entry into a miss" {
  printf 'rule\n' > rule.md
  printf '%s\n' '{"findings": [{"files": ["rule.md"], "lines": [], "kind": "inconsistency", "text": "usa → en vez de ⇒"}]}' > result.json
  python3 -B "$cache_script" store --project . --check codepage --version 1 --provider claude --model m \
    --file rule.md rule.md --result result.json
  run env PYTHONIOENCODING=cp1252 python3 -B "$cache_script" lookup --project . --check codepage --version 1 \
    --provider claude --model m --file rule.md rule.md
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | jq -r '.findings[0].text' | tr -d '\r')" = "usa → en vez de ⇒" ]
}

@test "each worktree keeps its own reviews options while the entries stay shared" {
  git -c user.email=tests@example.invalid -c user.name=Tests commit -q --allow-empty -m init
  git worktree add -q -b other "$test_root/other-worktree"
  write_settings false true none
  (cd "$test_root/other-worktree" && write_settings true true 2)

  run python3 -B - "$cache_script" "$project_dir" "$test_root/other-worktree" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("review_cache", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
main, other = module.ReviewCache(sys.argv[2]), module.ReviewCache(sys.argv[3])
print(main.path == other.path, main.settings()["enabled"], other.settings()["enabled"], other.settings()["ttl"])
PY
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | tr -d '\r')" = "True False True 2" ]
  run_hook .agents/rules/testing.md
  [[ "$output" == *"AI reviews are off (reviews.enabled: false)"* ]]
}

@test "a Codex edit is reviewed with codex exec, through the Bash of the hook, without a Claude binary" {
  mkdir codex-only-bin
  cp "$fake_bin/codex" codex-only-bin/codex
  # The fake provider runs through Bash; Python and Git are the real ones, which a native
  # Windows Python can only start from their own directories.
  for tool in cat basename; do
    printf '#!%s\nexec "%s" "$@"\n' "$BASH" "$(command -v "$tool")" > "codex-only-bin/$tool"
    chmod +x "codex-only-bin/$tool"
  done
  only_codex="$PWD/codex-only-bin:$(dirname "$(command -v git)"):$(dirname "$(command -v python3)")"
  payload='{"tool_name":"apply_patch","tool_input":{"command":"*** Update File: .agents/rules/testing.md"}}'

  run env PATH="$only_codex" "$BASH" "$hook" <<< "$payload"
  [ "$status" -eq 0 ]
  [ "$(cat "$FAKE_CALLS")" = "codex" ]
  grep -Fq 'codex exec --model gpt-6-luna' "$FAKE_ARGUMENTS"
  [ "$(argument_after -c)" = 'model_reasoning_effort="high"' ]
  [ "$(argument_after --sandbox)" = read-only ]
  # The answer came back through --output-last-message, so both pairs are cached.
  [ "$(cache_value 'len(data["entries"])')" -eq 2 ]

  rm codex-only-bin/codex
  run env PATH="$only_codex" "$BASH" "$hook" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *"codex CLI is not available; consistency check skipped."* ]]
}

@test "an entry stays while another worktree still has its files" {
  git -c user.email=tests@example.invalid -c user.name=Tests commit -q --allow-empty -m init
  git worktree add -q -b other "$test_root/other-worktree"
  printf 'only here\n' > main-only.md
  printf '%s\n' '{"findings": []}' > result.json
  python3 -B "$cache_script" store --project . --check worktrees --version 1 --provider claude --model m \
    --file main-only.md main-only.md --result result.json

  # A write from the worktree that lacks the file keeps the entry of this one.
  (cd "$test_root/other-worktree" && write_settings true true 3)
  [ "$(cache_value 'sorted(data["entries"])')" = "['worktrees:main-only.md']" ]

  rm main-only.md
  (cd "$test_root/other-worktree" && write_settings true true 4)
  [ "$(cache_value 'len(data["entries"])')" -eq 0 ]
}

@test "the AGENTS.md review and the hook read the provider defaults from one place" {
  run python3 -B "$cache_script" defaults --provider codex
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | tr -d '\r')" = "gpt-6-luna high" ]

  run_hook .agents/rules/testing.md
  [ "$(argument_after --model)" = claude-sonnet-5-5 ]
  [ "$(argument_after --effort)" = medium ]
}

@test "each finding has an id and accepting one with a reason silences only that one" {
  two_findings
  run_hook .agents/rules/testing.md
  mock_id="$(finding_id_of Mocks)"
  heading_id="$(finding_id_of 'The headings')"
  [ -n "$mock_id" ] && [ -n "$heading_id" ] && [ "$mock_id" != "$heading_id" ]
  [[ "$output" == *"! [$mock_id] .agents/rules/style.md <-> .agents/rules/testing.md: Mocks are both required"* ]]

  run_cli review accept "$mock_id"
  [ "$status" -eq 2 ]
  run_cli review accept "$mock_id" --reason "   "
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"--reason cannot be empty"* ]]
  [ ! -e .agents/agent-ready.reviews.json ]
  run_cli review accept 0000000000 --reason "on purpose"
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"no current finding has the id 0000000000"* ]]

  git config user.name "Ada Reviewer"
  run_cli review accept "$mock_id" --reason "golfo mocks the network on purpose"
  [ "$status" -eq 0 ]
  [ "$(decision_value "[data['decisions']['$mock_id'][key] for key in ('decision', 'scope', 'reason', 'by')]")" = \
    "['accepted', 'content', 'golfo mocks the network on purpose', 'Ada Reviewer']" ]

  # The hook, status and plan keep showing the other finding of the same pair.
  run_hook .agents/rules/testing.md
  [ "$(calls)" -eq 1 ]
  [[ "$output" != *"[$mock_id]"* ]]
  [[ "$output" == *"! [$heading_id]"* ]]
  run --separate-stderr python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --format json
  [ "$(python3 -c 'import json,sys; r=json.loads(sys.argv[1])["reviews"]; print([f["id"] for f in r["findings"]], r["quiet"])' "$output" | tr -d '\r')" = \
    "['$heading_id'] 1" ]
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project .
  [[ "$output" == *"1 known finding(s) in 2 reviewed unit(s), from the cache; 1 accepted or dismissed:"* ]]
  [[ "$output" == *"! [$heading_id]"* ]]
}

@test "a content decision asks to be confirmed once its files change; a pair decision stays" {
  two_findings
  run_hook .agents/rules/testing.md
  mock_id="$(finding_id_of Mocks)"
  heading_id="$(finding_id_of 'The headings')"
  run_cli review accept "$mock_id" --reason "on purpose"
  run_cli review dismiss "$heading_id" --reason "not a real conflict" --scope pair

  printf 'Keep tests fast.\n' >> .agents/rules/testing.md
  run_hook .agents/rules/testing.md
  [ "$(calls)" -eq 2 ]
  [[ "$output" == *"? [$mock_id] .agents/rules/style.md <-> .agents/rules/testing.md: Mocks are both required and forbidden. (accepted before the files changed: on purpose)"* ]]
  [[ "$output" != *"[$heading_id]"* ]]
  run_cli review list --json
  [ "$(python3 -c 'import json,sys; print(sorted((f["id"] == sys.argv[2], f["status"]) for f in json.loads(sys.argv[1])["findings"]))' "$output" "$mock_id" | tr -d '\r')" = \
    "[(False, 'dismissed'), (True, 'to-confirm')]" ]

  # Accepting it again records the current files, so it is quiet again.
  run_cli review accept "$mock_id" --reason "still on purpose"
  run_hook .agents/rules/testing.md
  [[ "$output" != *"[$mock_id]"* ]]
  [[ "$output" == *"No contradictions found. (2 accepted or dismissed)"* ]]
}

@test "reset brings findings back, and an unknown id or a missing target fails" {
  two_findings
  run_hook .agents/rules/testing.md
  mock_id="$(finding_id_of Mocks)"
  run_cli review accept "$mock_id" --reason "on purpose"
  [ -f .agents/agent-ready.reviews.json ]

  run_cli review reset
  [ "$status" -eq 2 ]
  run_cli review reset 1234567890
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"no decision has the id 1234567890"* ]]
  run_cli review reset "$mock_id"
  [ "$status" -eq 0 ]
  # No decision left: the file goes away instead of staying empty.
  [ ! -e .agents/agent-ready.reviews.json ]
  run_hook .agents/rules/testing.md
  [[ "$output" == *"! [$mock_id]"* ]]

  run_cli review accept "$mock_id" --reason "on purpose"
  run_cli review reset --all
  [ "$status" -eq 0 ]
  [ ! -e .agents/agent-ready.reviews.json ]
}

@test "a broken decisions file never blocks the hook and the CLI refuses to overwrite it" {
  two_findings
  run_hook .agents/rules/testing.md
  mock_id="$(finding_id_of Mocks)"
  printf '{ not json\n' > .agents/agent-ready.reviews.json

  run_hook .agents/rules/testing.md
  [ "$status" -eq 0 ]
  [[ "$output" == *"! [$mock_id]"* ]]
  run_cli review accept "$mock_id" --reason "on purpose"
  [ "$status" -eq 1 ]
  [[ "$stderr" == *".agents/agent-ready.reviews.json is not valid JSON"* ]]
  [ "$(cat .agents/agent-ready.reviews.json)" = "{ not json" ]
}

@test "merge-instructions shows the id of each inconsistency and hides the accepted ones" {
  # As an apply leaves them: the template rules the review sees are in the repository.
  cp "$skill_dir"/assets/common/rules/*.md "$skill_dir"/assets/stacks/node/rules/*.md .agents/rules/
  printf '%s\n' '# Project' 'Mock every dependency.' > AGENTS.md
  printf '%s\n' '{"project_content": "# Project\nMock every dependency.\n\n<!-- AGENT-READY MANAGED BLOCK -->", "removed": [], "inconsistencies": ["Mock every dependency. — conflicts with .agents/rules/style.md: it forbids mocks"], "reason": "One conflict."}' > "$FAKE_RESPONSE"
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/merge-instructions.sh" --provider claude --stack node --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  inconsistency_id="$(finding_id_of 'Mock every dependency.')"
  [[ "$output" == *"! [$inconsistency_id] Mock every dependency. — conflicts with .agents/rules/style.md"* ]]

  run_cli review accept "$inconsistency_id" --reason "this repository mocks on purpose"
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/merge-instructions.sh" --provider claude --stack node --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *"already reviewed; AI review not required."* ]]
  [[ "$output" != *"Instruction inconsistencies"* ]]
  [ "$(calls)" -eq 1 ]
}

@test "the hook leaves no bytecode beside its scripts" {
  run_hook .agents/rules/testing.md
  [ "$status" -eq 0 ]
  [ -z "$(find "$skill_dir/assets" -name __pycache__)" ]
}
