#!/usr/bin/env bats
# Semantic conflicts between the managed rules and the project's own, reviewed with AI: an update
# that brings a managed rule against the project's rules and AGENTS.md, and a project rule against
# the managed ones. The provider is a fake that reports a contradiction only for the pair whose
# documents contain both FAKE_CONFLICT_FIRST and FAKE_CONFLICT_SECOND.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  export XDG_CONFIG_HOME="$test_root/config"
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_ORGANIZATION_CONFIG="$test_root/organization/config.json"
  export AGENT_READY_SETUP_TOOLS=0
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  export GIT_CONFIG_GLOBAL="$test_root/gitconfig"
  git config --global user.name Test
  git config --global user.email test@example.invalid
  git config --global core.autocrlf false
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_REVIEW_MODE AGENT_READY_SETUP_STACK_DIR
  export FAKE_CALLS="$test_root/provider-calls.log"
  export FAKE_INPUT="$test_root/provider-input.log"
  export FAKE_CONFLICT_FIRST="verify-changes.md"
  export FAKE_CONFLICT_SECOND=".agents/rules/team.md"
  : > "$FAKE_CALLS"
  write_fake_provider
  install_engine_copy
  git -C "$project_dir" init -q
  cd "$project_dir"
  printf '{}\n' > package.json
}

teardown() {
  cd "$repository_root"
  rm -rf "$test_root"
}

# claude and codex answer one contradiction for the pair named in FAKE_CONFLICT_*, if it is among
# the numbered pairs of the input; FAKE_FAIL=1 makes them fail. Only a review (claude -p, codex exec)
# is logged: the marketplace refresh of an apply (claude plugin ...) succeeds without reading stdin.
write_fake_provider() {
  cat > "$fake_bin/fake-provider.py" <<'PY'
import json, os, re, sys
text = sys.stdin.read()
with open(os.environ["FAKE_INPUT"], "a", encoding="utf-8") as log:
    log.write(text)
findings = []
# FAKE_REQUIRE_TEXT: report only when the documents sent contain this text.
if os.environ.get("FAKE_REQUIRE_TEXT", "") not in text:
    print(json.dumps({"structured_output": {"findings": []}}))
    sys.exit(0)
for number, first, second in re.findall(r"^(\d+)\. (\S+) <-> (\S+)$", text, re.M):
    names = (first, second)
    if any(os.environ["FAKE_CONFLICT_FIRST"] in name for name in names) and any(
            os.environ["FAKE_CONFLICT_SECOND"] in name for name in names):
        findings.append({"pair": int(number), "lines": ["Verify every change.", "Never verify changes."],
                         "kind": "contradiction", "text": "One rule verifies every change and the other forbids it."})
print(json.dumps({"structured_output": {"findings": findings}}))
PY
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
[[ "\$1" == -p ]] || exit 0
printf 'claude\n' >> "\$FAKE_CALLS"
[[ "\${FAKE_FAIL:-0}" == 1 ]] && { cat > /dev/null; exit 1; }
python3 "$fake_bin/fake-provider.py"
EOF
  chmod +x "$fake_bin/claude"
  cat > "$fake_bin/codex" <<EOF
#!/bin/bash
[[ "\$1" == exec ]] || exit 0
printf 'codex\n' >> "\$FAKE_CALLS"
[[ "\${FAKE_FAIL:-0}" == 1 ]] && { cat > /dev/null; exit 1; }
while [[ \$# -gt 0 ]]; do
  [[ "\$1" == --output-last-message ]] && result_path="\$2"
  shift
done
python3 "$fake_bin/fake-provider.py" > "\$result_path"
EOF
  chmod +x "$fake_bin/codex"
}

# An installed plugin outside the repository, so a test can change what its content brings.
install_engine_copy() {
  installed_plugin="$test_root/installed/golfo-kit"
  engine_copy="$installed_plugin/skills/agent-ready-setup"
  mkdir -p "$engine_copy"
  cp "$repository_root/plugins/golfo-kit/plugin.json" "$installed_plugin/"
  cp -R "$repository_root/plugins/golfo-kit/.claude-plugin" "$repository_root/plugins/golfo-kit/.codex-plugin" "$installed_plugin/"
  cp -R "$skill_dir/assets" "$skill_dir/scripts" "$skill_dir/SKILL.md" "$engine_copy/"
}

agent_ready() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" "$@"
}

calls() {
  wc -l < "$FAKE_CALLS" | tr -d ' '
}

# Reviews of pairs only: an apply also reviews AGENTS.md with the same CLI.
pair_reviews() {
  grep -c '^<pairs>$' "$FAKE_INPUT" || true
}

write_manifest() {
  mkdir -p .agents
  printf '%s\n' "$1" > .agents/agent-ready.json
}

project_rule() {
  mkdir -p .agents/rules
  printf '# Team\nNever verify changes.\n' > .agents/rules/team.md
}

# The next version of the engine's content changes a managed rule.
change_managed_rule() {
  printf '\nVerify every change.\n' >> "$engine_copy/assets/common/rules/verify-changes.md"
}

first_conflict_id() {
  agent_ready plan --json
  printf '%s' "$output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["semanticConflicts"]["findings"][0]["id"])' | tr -d '\r'
}

@test "the update plan reviews a changed managed rule against the project's rules and AGENTS.md" {
  agent_ready apply --stack node
  [ "$status" -eq 0 ]
  project_rule
  change_managed_rule

  agent_ready plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Semantic conflicts (AI review of the managed rules and the project's own)"* ]]
  [[ "$output" == *".agents/rules/team.md <-> .agents/rules/verify-changes.md: One rule verifies every change and the other forbids it. (this update)"* ]]
  # The managed rule is reviewed with the content the update would write, and AGENTS.md is in.
  grep -Fq 'Verify every change.' "$FAKE_INPUT"
  grep -Eq '^[0-9]+\. \.agents/rules/verify-changes\.md <-> AGENTS\.md$' "$FAKE_INPUT"
  # Of AGENTS.md only what the project wrote: the managed block is the engine's.
  grep -Fq '# [Project Name]' "$FAKE_INPUT"
  ! grep -Fq 'BEGIN AGENT-READY MANAGED' "$FAKE_INPUT"
  # Nor the section of the stack, which the next apply also replaces.
  ! grep -Fq 'run `/node-review-pr`' "$FAKE_INPUT"
  # Only reports: nothing in the repository changed.
  ! grep -Fq 'Verify every change.' .agents/rules/verify-changes.md
}

@test "a project rule is reviewed against the managed rules once, and status shows it from the cache" {
  agent_ready apply --stack node
  [ "$status" -eq 0 ]
  project_rule

  agent_ready plan
  [ "$status" -eq 0 ]
  [[ "$output" == *".agents/rules/team.md <-> .agents/rules/verify-changes.md: One rule verifies every change and the other forbids it. (a project rule)"* ]]
  reviewed_calls="$(calls)"

  agent_ready plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"(a project rule)"* ]]
  [ "$(calls)" -eq "$reviewed_calls" ]
  agent_ready status
  [ "$status" -eq 0 ]
  [[ "$output" == *"One rule verifies every change and the other forbids it."* ]]
  [ "$(calls)" -eq "$reviewed_calls" ]
}

@test "conflicts.block stops an apply that brings a conflict, until the team accepts it on the new content" {
  write_manifest '{"profiles": ["node"], "conflicts": {"block": true}}'
  agent_ready apply
  [ "$status" -eq 0 ]
  project_rule
  change_managed_rule

  agent_ready apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"conflicts.block: this apply brings 1 semantic conflict(s) with the project, so nothing was changed"* ]]
  ! grep -Fq 'Verify every change.' .agents/rules/verify-changes.md

  # The rule is not on disk yet: the plan keeps the conflict so the team can decide on it.
  conflict_id="$(first_conflict_id)"
  agent_ready review list
  [ "$status" -eq 0 ]
  [[ "$output" == *"$conflict_id  open"* ]]
  agent_ready review accept "$conflict_id" --reason "The team rule is on purpose"
  [ "$status" -eq 0 ]
  agent_ready apply
  [ "$status" -eq 0 ]
  grep -Fq 'Verify every change.' .agents/rules/verify-changes.md
  # The decision was taken on the content the apply wrote, so it holds after it.
  agent_ready status
  [ "$status" -eq 0 ]
  [[ "$output" != *"One rule verifies every change and the other forbids it."* ]]
  agent_ready review list
  [[ "$output" == *"$conflict_id  accepted"* ]]
}

@test "a change to the managed rule after the decision asks to confirm it again" {
  write_manifest '{"profiles": ["node"], "conflicts": {"block": true}}'
  agent_ready apply
  [ "$status" -eq 0 ]
  project_rule
  change_managed_rule
  conflict_id="$(first_conflict_id)"
  agent_ready review accept "$conflict_id" --reason "The team rule is on purpose"
  [ "$status" -eq 0 ]
  printf 'Verify every change twice.\n' >> "$engine_copy/assets/common/rules/verify-changes.md"

  agent_ready apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"conflicts.block: this apply brings 1 semantic conflict(s)"* ]]
  [[ "$stderr" == *"accepted before the files changed"* ]]
}

@test "a review without an answer is incomplete, never clean, and conflicts.block stops on it" {
  write_manifest '{"profiles": ["node"], "conflicts": {"block": true}}'
  agent_ready apply
  [ "$status" -eq 0 ]
  project_rule
  change_managed_rule
  export FAKE_FAIL=1

  agent_ready plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Check incomplete:"*"claude gave no valid answer"* ]]
  [[ "$output" != *"No conflicts found"* ]]
  agent_ready apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"could not be checked for semantic conflicts (claude gave no valid answer), so nothing was changed"* ]]
}

@test "conflicts.enabled false and offline runs call no provider" {
  agent_ready apply --stack node
  [ "$status" -eq 0 ]
  project_rule
  change_managed_rule
  : > "$FAKE_CALLS"

  agent_ready plan --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"Check incomplete:"*"this run uses no network"* ]]
  [ "$(calls)" -eq 0 ]

  write_manifest '{"profiles": ["node"], "conflicts": {"enabled": false}}'
  agent_ready plan
  [ "$status" -eq 0 ]
  [[ "$output" != *"Semantic conflicts"* ]]
  [ "$(calls)" -eq 0 ]
}

@test "the conflict review follows reviews.cache of this run, before an apply records it" {
  agent_ready apply --stack node
  [ "$status" -eq 0 ]
  project_rule
  agent_ready plan
  [ "$status" -eq 0 ]
  reviewed_calls="$(calls)"

  write_manifest '{"profiles": ["node"], "reviews": {"cache": false}}'
  agent_ready plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"(a project rule)"* ]]
  [ "$(calls)" -gt "$reviewed_calls" ]
}

@test "the background sync reviews with the provider it runs for" {
  agent_ready apply --stack node
  [ "$status" -eq 0 ]
  project_rule
  : > "$FAKE_CALLS"
  # The AGENTS.md review that the sync leaves running detached is not what this test checks, and
  # it would outlive the test: the engine copy starts nothing in the background.
  printf 'import sys\nsys.exit(0)\n' > "$engine_copy/scripts/run-detached.py"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$engine_copy" AGENT_READY_SETUP_SYNC_FOREGROUND=1 \
    bash .agents/hooks/sync-marketplace.sh --provider codex
  [ "$status" -eq 0 ]
  grep -Fxq codex "$FAKE_CALLS"
  ! grep -Fxq claude "$FAKE_CALLS"
}

@test "a decision before the apply covers the update even after the hook reviewed the applied rule" {
  write_manifest '{"profiles": ["node"], "conflicts": {"block": true}}'
  agent_ready apply
  [ "$status" -eq 0 ]
  project_rule
  change_managed_rule
  conflict_id="$(first_conflict_id)"
  # The edit hook reviews the rule on disk again: the same finding, with the applied content.
  run env PATH="$fake_bin:$PATH" bash .agents/hooks/check-harness-consistency.sh \
    <<< '{"tool_name":"Edit","tool_input":{"file_path":".agents/rules/team.md"}}'

  agent_ready review accept "$conflict_id" --reason "The team rule is on purpose"
  [ "$status" -eq 0 ]
  agent_ready apply
  [ "$status" -eq 0 ]
  grep -Fq 'Verify every change.' .agents/rules/verify-changes.md
}

@test "an instruction inside the managed block of AGENTS.md never blocks the update that replaces it" {
  write_manifest '{"profiles": ["node"], "conflicts": {"block": true}}'
  agent_ready apply
  [ "$status" -eq 0 ]
  change_managed_rule
  # An obsolete managed instruction that the same update would replace.
  python3 - <<'PY'
import re
path = "AGENTS.md"
text = open(path, encoding="utf-8").read()
text = text.replace("<!-- END AGENT-READY MANAGED -->", "Never verify changes.\n<!-- END AGENT-READY MANAGED -->", 1)
open(path, "w", encoding="utf-8").write(text)
PY
  export FAKE_CONFLICT_SECOND="AGENTS.md" FAKE_REQUIRE_TEXT="Never verify changes."

  agent_ready plan
  [ "$status" -eq 0 ]
  grep -Eq '^[0-9]+\. \.agents/rules/verify-changes\.md <-> AGENTS\.md$' "$FAKE_INPUT"
  [[ "$output" != *"(this update)"* ]]
  [[ "$output" == *"No conflicts found"* ]]
}

@test "a preview keeps its review out of the versioned cache, and the apply publishes it" {
  agent_ready apply --stack node
  [ "$status" -eq 0 ]
  project_rule
  write_manifest '{"profiles": ["node"], "reviews": {"commit": true}}'

  agent_ready plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"(a project rule)"* ]]
  [ ! -e .agents/agent-ready.review-cache.json ]
  reviewed_pairs="$(pair_reviews)"

  agent_ready apply
  [ "$status" -eq 0 ]
  [ "$(pair_reviews)" -eq "$reviewed_pairs" ]
  grep -Fq '.agents/rules/team.md' .agents/agent-ready.review-cache.json
}

@test "after the apply, a decision on its conflict follows the files again" {
  write_manifest '{"profiles": ["node"], "conflicts": {"block": true}}'
  agent_ready apply
  [ "$status" -eq 0 ]
  project_rule
  change_managed_rule
  conflict_id="$(first_conflict_id)"
  agent_ready review accept "$conflict_id" --reason "The team rule is on purpose"
  [ "$status" -eq 0 ]
  agent_ready apply
  [ "$status" -eq 0 ]

  # The team edits its rule: the decision was about the old text, so it asks to confirm it again.
  printf 'Not even small changes.\n' >> .agents/rules/team.md
  run env PATH="$fake_bin:$PATH" bash .agents/hooks/check-harness-consistency.sh \
    <<< '{"tool_name":"Edit","tool_input":{"file_path":".agents/rules/team.md"}}'
  agent_ready review list
  [ "$status" -eq 0 ]
  [[ "$output" == *"$conflict_id  to-confirm"* ]]
}

@test "the first apply reviews the CLAUDE.md that it promotes to AGENTS.md, in any case" {
  for claude_file in CLAUDE.md claude.md; do
    rm -f CLAUDE.md claude.md
    printf '# Team\nNever verify changes.\n' > "$claude_file"
    write_manifest '{"profiles": ["node"], "conflicts": {"block": true}}'
    export FAKE_CONFLICT_SECOND="AGENTS.md"

    agent_ready apply
    [ "$status" -ne 0 ]
    [[ "$stderr" == *"conflicts.block: this apply brings"*"<-> AGENTS.md"* ]]
    [ ! -e AGENTS.md ]
    grep -Fq 'Never verify changes.' "$claude_file"
  done
}

@test "a conflict of the first apply with AGENTS.md stays listed after the apply writes its managed block" {
  printf '# Team\nNever verify changes.\n' > AGENTS.md
  write_manifest '{"profiles": ["node"]}'
  export FAKE_CONFLICT_SECOND="AGENTS.md"

  agent_ready apply
  [ "$status" -eq 0 ]
  grep -Fq 'BEGIN AGENT-READY MANAGED' AGENTS.md
  agent_ready review list
  [ "$status" -eq 0 ]
  [[ "$output" == *"open"*".agents/rules/verify-changes.md <-> AGENTS.md"* ]]
  conflict_id="$(printf '%s\n' "$output" | awk '/verify-changes.md <-> AGENTS.md/ {print $1; exit}')"
  agent_ready review accept "$conflict_id" --reason "The team instruction is on purpose"
  [ "$status" -eq 0 ]
  agent_ready status
  [ "$status" -eq 0 ]
  [[ "$output" != *"One rule verifies every change and the other forbids it."* ]]
}
