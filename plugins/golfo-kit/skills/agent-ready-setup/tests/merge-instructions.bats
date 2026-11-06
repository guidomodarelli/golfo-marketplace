#!/usr/bin/env bats

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  test_root="$(mktemp -d)"
  # Native Windows symlinks under Git Bash (needs Developer Mode); ignored elsewhere.
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  # Keeps the SessionStart upgrade window stamp out of the user's real cache.
  export XDG_CACHE_HOME="$test_root/cache"
  git -C "$project_dir" -c init.defaultBranch=main init -q
  cd "$project_dir"
  managed_placeholder='<!-- AGENT-READY MANAGED BLOCK -->'
}

# Background tasks run detached from the hook; wait for their observable effect.
wait_for_file_containing() {
  local path="$1"
  local expected="$2"
  local attempt

  for attempt in $(seq 1 100); do
    if [[ -f "$path" ]] && grep -Fq -- "$expected" "$path"; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

teardown() {
  # Background processes may outlive a timed-out test; stop them so bats can finish.
  if [[ -n "${background_pids:-}" ]]; then
    kill $background_pids 2>/dev/null || true
  fi
  cd "$repository_root"
  # Windows cannot delete files that a detached background review still has open;
  # retry for a few seconds so it can finish before failing the test.
  local removal_attempt
  for removal_attempt in $(seq 1 50); do
    rm -rf "$test_root" 2>/dev/null && return 0
    sleep 0.2
  done
  rm -rf "$test_root"
}

render_managed_block() {
  local stack="$1"
  local source_dir="${2:-$skill_dir}"

  bash "$source_dir/scripts/render-instruction-template.sh" \
    --template "$source_dir/assets/stacks/$stack/agents-template.md" \
    --rules-dir "$source_dir/assets/stacks/$stack/rules" \
    --common-rules-dir "$source_dir/assets/common/rules" \
    --centralization "$source_dir/assets/instruction-centralization.md" \
    --managed-block
}

write_review_response() {
  local project_content="$1"
  local removed_json="${2:-[]}"
  local inconsistencies_json="${3:-[]}"

  jq -n \
    --arg content "$project_content" \
    --argjson removed "$removed_json" \
    --argjson inconsistencies "$inconsistencies_json" \
    '{project_content:$content, removed:$removed, inconsistencies:$inconsistencies, reason:"Reviewed project content."}' \
    > "$test_root/provider-response.json"
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
printf '%s\\n' called >> "$test_root/provider-calls.log"
printf '%s\\n' "\$*" > "$test_root/provider-args.log"
{ cat "$test_root/provider-args.log"; cat; } > "$test_root/provider-prompt.log"
cat "$test_root/provider-response.json"
EOF
  chmod +x "$fake_bin/claude"
}

run_merge() {
  local stack="$1"
  local source_dir="${2:-$skill_dir}"

  PATH="$fake_bin:$PATH" run bash "$source_dir/scripts/merge-instructions.sh" \
    --provider claude --stack "$stack" --skill-dir "$source_dir"
}

provider_call_count() {
  if [[ -f "$test_root/provider-calls.log" ]]; then
    wc -l < "$test_root/provider-calls.log" | tr -d ' '
  else
    printf '0\n'
  fi
}

# Git Bash without native symlinks copies instead of linking; these tests check real symlinks.
skip_without_symlinks() {
  local probe_target="$test_root/symlink-probe-target"
  local probe_link="$test_root/symlink-probe-link"
  : > "$probe_target"
  ln -s "$probe_target" "$probe_link" 2>/dev/null || true
  if [[ ! -L "$probe_link" ]]; then
    rm -f "$probe_target" "$probe_link"
    skip "requiere symlinks reales (en Windows: Modo de desarrollador o una shell elevada)"
  fi
  rm -f "$probe_target" "$probe_link"
}

@test "legacy AGENTS receives the verbatim managed block and keeps project content" {
  cat > AGENTS.md <<'EOF'
# Existing project instructions

Run make verify before merging.

## Rules

@./rules/coding-style.md
@./rules/security.md
EOF
  write_review_response $'# Existing project instructions\n\nRun make verify before merging.\n\n'"$managed_placeholder" \
    '["## Rules — replaced by managed block", "@./rules/coding-style.md — replaced by managed block", "@./rules/security.md — replaced by managed block"]'

  run_merge node

  [ "$status" -eq 0 ]
  [ "$(cat AGENTS.md)" = "$(printf '%s\n\n%s\n\n%s' '# Existing project instructions' 'Run make verify before merging.' "$(render_managed_block node)")" ]
  ! grep -Eq '@[^[:space:]]*rules/' AGENTS.md
  [[ "$output" == *"Removed redundant lines outside the managed block:"* ]]
  [ -f .git/info/agent-ready-instructions-reviewed.sha256 ]

  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
exit 42
EOF
  run_merge node
  [ "$status" -eq 0 ]
  [[ "$output" == *"already reviewed; AI review not required."* ]]
}

@test "managed block is replaced verbatim and content outside markers is preserved" {
  cat > AGENTS.md <<'EOF'
# Project

Project description.

<!-- BEGIN AGENT-READY MANAGED -->
## Rules

- Read and follow `.agents/rules/retired.md`.
Local edit inside the block.
<!-- END AGENT-READY MANAGED -->

## Ownership

Team Astra owns this service.
EOF
  write_review_response $'# Project\n\nProject description.\n\n'"$managed_placeholder"$'\n\n## Ownership\n\nTeam Astra owns this service.'

  run_merge node

  [ "$status" -eq 0 ]
  expected="$(printf '%s\n\n%s\n\n%s\n%s\n\n%s\n\n%s' '# Project' 'Project description.' \
    "$(render_managed_block node)" '' '## Ownership' 'Team Astra owns this service.')"
  [ "$(cat AGENTS.md)" = "$(sed '/^$/N;/^\n$/D' <<< "$expected")" ]
  ! grep -Fq 'Local edit inside the block.' AGENTS.md
  ! grep -Fq 'retired.md' AGENTS.md
  bash "$skill_dir/scripts/render-instruction-template.sh" --validate AGENTS.md \
    --rules-dir "$skill_dir/assets/stacks/node/rules" \
    --common-rules-dir "$skill_dir/assets/common/rules"
}

@test "managed block omits skill lists because providers discover skills natively" {
  printf '%s\n' '# Project' > AGENTS.md
  write_review_response $'# Project\n\n'"$managed_placeholder"

  run_merge frontend

  [ "$status" -eq 0 ]
  ! grep -Fxq '## Skills' AGENTS.md
  ! grep -Fq 'AGENT-READY RULE REFERENCES' AGENTS.md
  grep -Fq 'Claude Code already loads these rules from `.claude/rules/`; do not read them again.' AGENTS.md
  ! grep -Fq '{{AGENT_READY_' AGENTS.md
  grep -Fxq '## Centralización recursiva de instrucciones' AGENTS.md
  [ "$(grep -c '^<!-- BEGIN AGENT-READY MANAGED -->$' AGENTS.md)" -eq 1 ]
}

@test "Claude review defaults to Sonnet 5 with medium effort" {
  unset AGENT_READY_SETUP_MERGE_MODEL AGENT_READY_SETUP_MERGE_REASONING_EFFORT
  printf '%s\n' '# Existing project instructions' > AGENTS.md
  write_review_response $'# Existing project instructions\n\n'"$managed_placeholder"

  run_merge node

  [ "$status" -eq 0 ]
  grep -Fq -- '--model claude-sonnet-5-5 --effort medium' "$test_root/provider-prompt.log"
}

@test "review deletes project lines already covered by rules" {
  cat > AGENTS.md <<'EOF'
# Project

Use Jest and React Testing Library for tests.
Deploy with make release.
EOF
  write_review_response $'# Project\n\nDeploy with make release.\n\n'"$managed_placeholder" \
    '["Use Jest and React Testing Library for tests. — covered by .agents/rules/testing.md"]'

  run_merge frontend

  [ "$status" -eq 0 ]
  ! grep -Fq 'Use Jest and React Testing Library for tests.' AGENTS.md
  grep -Fxq 'Deploy with make release.' AGENTS.md
  [[ "$output" == *"covered by .agents/rules/testing.md"* ]]
}

@test "review reports inconsistencies and keeps the conflicting content" {
  cat > AGENTS.md <<'EOF'
# Project

Mock design system components in every test.
EOF
  write_review_response $'# Project\n\nMock design system components in every test.\n\n'"$managed_placeholder" '[]' \
    '["Mock design system components in every test. — conflicts with .agents/rules/testing.md: design system components must not be mocked"]'

  run_merge frontend

  [ "$status" -eq 0 ]
  grep -Fxq 'Mock design system components in every test.' AGENTS.md
  [[ "$output" == *"Instruction inconsistencies (manual review required; content preserved):"* ]]
  [[ "$output" == *"conflicts with .agents/rules/testing.md"* ]]
}

@test "review that adds or rewrites lines is rejected and only the managed block is applied" {
  printf '%s\n' '# Keep this file' > AGENTS.md
  write_review_response $'# Keep this file, reworded\n\n'"$managed_placeholder"

  run_merge node

  [ "$status" -eq 0 ]
  [[ "$output" == *"review rejected: reviewed content adds or rewrites a line"* ]]
  [ "$(cat AGENTS.md)" = "$(printf '%s\n\n%s' '# Keep this file' "$(render_managed_block node)")" ]
  [ ! -e .git/info/agent-ready-instructions-reviewed.sha256 ]
}

@test "review output without the placeholder or with fences is rejected" {
  printf '%s\n' '# Keep this file' > AGENTS.md
  write_review_response '# Keep this file'

  run_merge node

  [ "$status" -eq 0 ]
  [[ "$output" == *"must keep the managed block placeholder exactly once"* ]]
  grep -Fxq '# Keep this file' AGENTS.md

  write_review_response $'```markdown\n# Keep this file\n'"$managed_placeholder"$'\n```'
  run_merge node
  [ "$status" -eq 0 ]
  [[ "$output" == *"fenced instead of Markdown"* ]]
  grep -Fxq '# Keep this file' AGENTS.md
}

@test "provider failure applies the managed block and retries the review next sync" {
  printf '%s\n' '# Keep this file' > AGENTS.md
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
printf '%s\\n' called >> "$test_root/provider-calls.log"
exit 1
EOF
  chmod +x "$fake_bin/claude"

  run_merge node

  [ "$status" -eq 0 ]
  [[ "$output" == *"Claude review provider failed; applying the managed block without redundancy review."* ]]
  [ "$(cat AGENTS.md)" = "$(printf '%s\n\n%s' '# Keep this file' "$(render_managed_block node)")" ]

  run_merge node
  [ "$status" -eq 0 ]
  [ "$(provider_call_count)" -eq 2 ]
}

@test "invalid structured output keeps project content and applies the managed block" {
  printf '%s\n' '# Keep this file' > AGENTS.md
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf '%s\n' 'not-json'
EOF
  chmod +x "$fake_bin/claude"

  run_merge frontend

  [ "$status" -eq 0 ]
  [[ "$output" == *"invalid structured output"* ]]
  grep -Fxq '# Keep this file' AGENTS.md
  grep -Fxq '<!-- BEGIN AGENT-READY MANAGED -->' AGENTS.md
}

@test "malformed managed markers require human review without invoking the provider" {
  cat > AGENTS.md <<'EOF'
<!-- BEGIN AGENT-READY MANAGED -->
<!-- BEGIN AGENT-READY MANAGED -->
<!-- END AGENT-READY MANAGED -->
EOF
  before_hash="$(shasum AGENTS.md | cut -d ' ' -f 1)"
  write_review_response "$managed_placeholder"

  run_merge node

  [ "$status" -eq 2 ]
  [ "$(shasum AGENTS.md | cut -d ' ' -f 1)" = "$before_hash" ]
  [ "$(provider_call_count)" -eq 0 ]
  [[ "$output" == *"Human confirmation required"* ]]
}

@test "provider prompt includes managed block, rule contents, and project content" {
  printf '%s\n' '# Existing project instructions' > AGENTS.md
  write_review_response $'# Existing project instructions\n\n'"$managed_placeholder"

  run_merge node

  [ "$status" -eq 0 ]
  grep -Fq '<rule path=".agents/rules/security.md">' "$test_root/provider-prompt.log"
  grep -Fq "$(sed -n '1p' "$skill_dir/assets/stacks/node/rules/security.md")" "$test_root/provider-prompt.log"
  grep -Fq '# Existing project instructions' "$test_root/provider-prompt.log"
  grep -Fq '<!-- BEGIN AGENT-READY MANAGED -->' "$test_root/provider-prompt.log"
  ! grep -Fq '{{AGENT_READY_' "$test_root/provider-prompt.log"
  # Documents travel through stdin, never as one oversized command-line argument.
  ! grep -Fq '# Existing project instructions' "$test_root/provider-args.log"
}

@test "new rule files enter the managed block and rule changes trigger a new review" {
  dynamic_skill_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$dynamic_skill_dir"
  printf '%s\n' '# Runtime-specific rules' > "$dynamic_skill_dir/assets/stacks/node/rules/runtime.md"
  printf '%s\n' '# Existing project instructions' > AGENTS.md
  write_review_response $'# Existing project instructions\n\n'"$managed_placeholder"

  run_merge node "$dynamic_skill_dir"

  [ "$status" -eq 0 ]
  grep -Fxq -- '- Read and follow `.agents/rules/runtime.md`.' AGENTS.md
  [ "$(provider_call_count)" -eq 1 ]

  run_merge node "$dynamic_skill_dir"
  [ "$(provider_call_count)" -eq 1 ]

  printf '%s\n' '# Runtime-specific rules, revised' > "$dynamic_skill_dir/assets/stacks/node/rules/runtime.md"
  run_merge node "$dynamic_skill_dir"
  [ "$status" -eq 0 ]
  [ "$(provider_call_count)" -eq 2 ]
}

@test "common rules are template rules for every stack and never project rules" {
  mkdir -p .agents/rules
  cp "$skill_dir/assets/common/rules/lint-gate.md" .agents/rules/lint-gate.md
  printf '%s\n' '# Project' > AGENTS.md
  write_review_response $'# Project\n\n'"$managed_placeholder"

  run_merge go

  [ "$status" -eq 0 ]
  grep -Fxq -- '- Read and follow `.agents/rules/language-consistency.md`.' AGENTS.md
  grep -Fxq -- '- Read and follow `.agents/rules/lint-gate.md`.' AGENTS.md
  [ "$(grep -c 'rules/lint-gate.md' AGENTS.md)" -eq 1 ]
  ! grep -Fxq '### Project rules' AGENTS.md
  grep -Fq '<rule path=".agents/rules/language-consistency.md">' "$test_root/provider-prompt.log"
}

@test "a rule defined in both common and stack rules is rejected" {
  duplicate_skill_dir="$test_root/duplicate-skill"
  cp -R "$skill_dir" "$duplicate_skill_dir"
  cp "$duplicate_skill_dir/assets/common/rules/lint-gate.md" "$duplicate_skill_dir/assets/stacks/node/rules/lint-gate.md"

  run bash "$duplicate_skill_dir/scripts/render-instruction-template.sh" --list-rules \
    --rules-dir "$duplicate_skill_dir/assets/stacks/node/rules" \
    --common-rules-dir "$duplicate_skill_dir/assets/common/rules"

  [ "$status" -ne 0 ]
  [[ "$output" == *"rule is defined in both common and stack rules: lint-gate.md"* ]]
}

@test "project rules are listed in the managed block and reviewed with template rules" {
  skip_without_symlinks
  mkdir -p .agents/rules/area
  printf '%s\n' '# Team conventions' 'Deploy only on Tuesdays.' > .agents/rules/team-conventions.md
  printf '%s\n' '# Area rule' > .agents/rules/area/payments.md
  cp "$skill_dir/assets/stacks/node/rules/security.md" .agents/rules/security.md
  ln -s /etc/hosts .agents/rules/linked.md
  printf '%s\n' '# Project' > AGENTS.md
  write_review_response $'# Project\n\n'"$managed_placeholder"

  run_merge node

  [ "$status" -eq 0 ]
  grep -Fxq '### Project rules' AGENTS.md
  grep -Fxq -- '- Read and follow `.agents/rules/team-conventions.md`.' AGENTS.md
  grep -Fxq -- '- Read and follow `.agents/rules/area/payments.md`.' AGENTS.md
  [ "$(grep -c 'rules/security.md' AGENTS.md)" -eq 1 ]
  ! grep -Fq 'linked.md' AGENTS.md
  grep -Fq '<rule path=".agents/rules/team-conventions.md">' "$test_root/provider-prompt.log"
  grep -Fq 'Deploy only on Tuesdays.' "$test_root/provider-prompt.log"
  bash "$skill_dir/scripts/render-instruction-template.sh" --validate AGENTS.md \
    --rules-dir "$skill_dir/assets/stacks/node/rules" \
    --common-rules-dir "$skill_dir/assets/common/rules" --project-rules-dir .agents/rules
  [ "$(provider_call_count)" -eq 1 ]

  printf '%s\n' 'Deploy only on Wednesdays.' >> .agents/rules/team-conventions.md
  run_merge node
  [ "$status" -eq 0 ]
  [ "$(provider_call_count)" -eq 2 ]

  rm .agents/rules/team-conventions.md
  write_review_response "$(awk '/^<!-- BEGIN AGENT-READY MANAGED -->$/ { print "<!-- AGENT-READY MANAGED BLOCK -->"; skip = 1; next } /^<!-- END AGENT-READY MANAGED -->$/ { skip = 0; next } !skip' AGENTS.md)"
  run_merge node
  [ "$status" -eq 0 ]
  ! grep -Fq 'team-conventions.md' AGENTS.md
}

@test "review metadata is isolated per linked worktree" {
  git config user.email "agent-ready-tests@example.com"
  git config user.name "Agent Ready Tests"
  printf '%s\n' '# Initial repository content' > README.md
  git add README.md
  git commit -qm "Initialize linked worktree test"

  linked_project_dir="$test_root/linked-project"
  git worktree add -q -b linked-worktree "$linked_project_dir"
  printf '%s\n' '# Existing project instructions' > AGENTS.md
  printf '%s\n' '# Existing project instructions' > "$linked_project_dir/AGENTS.md"
  write_review_response $'# Existing project instructions\n\n'"$managed_placeholder"

  run_merge node
  [ "$status" -eq 0 ]
  cd "$linked_project_dir"
  run_merge node
  [ "$status" -eq 0 ]

  main_hash_file="$(git -C "$project_dir" rev-parse --absolute-git-dir)/info/agent-ready-instructions-reviewed.sha256"
  linked_hash_file="$(git -C "$linked_project_dir" rev-parse --absolute-git-dir)/info/agent-ready-instructions-reviewed.sha256"
  [ -f "$main_hash_file" ]
  [ -f "$linked_hash_file" ]
  [ "$main_hash_file" != "$linked_hash_file" ]
  [ "$(provider_call_count)" -eq 2 ]
}

@test "successful merge replaces AGENTS atomically without temporary residue" {
  printf '%s\n' '# Existing project instructions' > AGENTS.md
  write_review_response $'# Existing project instructions\n\n'"$managed_placeholder"
  original_inode="$(ls -di AGENTS.md | awk '{print $1}')"

  run_merge node

  [ "$status" -eq 0 ]
  [ "$(ls -di AGENTS.md | awk '{print $1}')" != "$original_inode" ]
  temporary_files=(.AGENTS.md.agent-ready-merge.*)
  [ ! -e "${temporary_files[0]}" ]
}

@test "concurrent AGENTS changes are not overwritten by a stale merge" {
  printf '%s\n' '# Original instructions' > AGENTS.md
  write_review_response $'# Original instructions\n\n'"$managed_placeholder"
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
printf '%s\n' '# Newer user instructions' > AGENTS.md
cat "$test_root/provider-response.json"
EOF
  chmod +x "$fake_bin/claude"

  run_merge node

  [ "$status" -ne 0 ]
  [ "$(cat AGENTS.md)" = '# Newer user instructions' ]
  [[ "$output" == *"changed before descriptor write"* ]]
}

@test "atomic replacement rejects stale descriptor write" {
  printf '%s\n' '# Original instructions' > AGENTS.md
  write_review_response $'# Original instructions\n\n'"$managed_placeholder"
  real_python="$(command -v python3)"
  # Only the four-argument descriptor writer races; split and assembly run first.
  cat > "$fake_bin/python3" <<EOF
#!/bin/bash
if [[ \$# -eq 4 ]]; then
  printf '%s\n' '# Newer descriptor instructions' > .AGENTS.md.new
  mv .AGENTS.md.new AGENTS.md
fi
exec "$real_python" "\$@"
EOF
  chmod +x "$fake_bin/python3"

  run_merge node

  [ "$status" -ne 0 ]
  [ "$(cat AGENTS.md)" = '# Newer descriptor instructions' ]
  [[ "$output" == *"changed before descriptor write"* ]]
}

@test "directory lock protects against pathname replacement during atomic update" {
  python3 - <<'PY'
with open('AGENTS.md', 'w', encoding='utf-8') as agents_file:
    agents_file.write('# Original instructions\n\n')
    for index in range(250000):
        agents_file.write(f'Project line {index}\n')
PY
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
exit 1
EOF
  chmod +x "$fake_bin/claude"
  race_marker="$test_root/race-detected"
  writer_script="$test_root/replace-after-merge.py"
  cat > "$writer_script" <<'PY'
import glob
import os
import sys
import time

# Same protocol as managed-block.sh: directory flock on POSIX, msvcrt lock file on Windows.
try:
    import fcntl
except ImportError:
    fcntl = None
    import msvcrt


race_marker = sys.argv[1]
windows_lock_path = sys.argv[2]
open(sys.argv[3], 'w').close()
deadline = time.monotonic() + 30
while not glob.glob('.AGENTS.md.agent-ready-merge.*'):
    if time.monotonic() >= deadline:
        sys.exit('merge temporary file was not created')
    time.sleep(0.001)

directory_descriptor = None
windows_lock_file = None
try:
    if fcntl is not None:
        directory_descriptor = os.open('.', os.O_RDONLY)
        fcntl.flock(directory_descriptor, fcntl.LOCK_EX)
    else:
        windows_lock_file = open(windows_lock_path, 'a+b')
        while True:
            try:
                windows_lock_file.seek(0)
                msvcrt.locking(windows_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except PermissionError:
                time.sleep(0.01)
    if glob.glob('.AGENTS.md.agent-ready-merge.*'):
        open(race_marker, 'w').close()
    replacement_path = '.concurrent-agents.md'
    with open(replacement_path, 'w', encoding='utf-8') as replacement_file:
        replacement_file.write('# Newer user instructions\n')
        replacement_file.flush()
        os.fsync(replacement_file.fileno())
    os.replace(replacement_path, 'AGENTS.md')
finally:
    if directory_descriptor is not None:
        os.close(directory_descriptor)
    if windows_lock_file is not None:
        windows_lock_file.close()
PY

  # The writer polls before the merge starts: a slow Python startup would otherwise
  # miss the short-lived temporary file and wait for it until the deadline.
  ready_marker="$test_root/writer-ready"
  windows_lock_path="$(git rev-parse --absolute-git-dir)/agent-ready-agents-md.lock"
  python3 "$writer_script" "$race_marker" "$windows_lock_path" "$ready_marker" \
    > "$test_root/writer-output.log" 2>&1 3>&- &
  writer_pid=$!
  background_pids="$writer_pid"
  local wait_attempt
  for wait_attempt in $(seq 1 300); do
    [ -e "$ready_marker" ] && break
    sleep 0.1
  done
  PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/merge-instructions.sh" \
    --provider claude --stack node --skill-dir "$skill_dir" \
    > "$test_root/merge-output.log" 2>&1 3>&- &
  merge_pid=$!
  background_pids="$merge_pid $writer_pid"

  if wait "$merge_pid"; then
    merge_status=0
  else
    merge_status=$?
  fi
  if wait "$writer_pid"; then
    writer_status=0
  else
    writer_status=$?
  fi

  # bats shows this output only when the test fails.
  cat "$test_root/writer-output.log"
  [ "$merge_status" -eq 0 ]
  [ "$writer_status" -eq 0 ]
  [ ! -e "$race_marker" ]
  [ "$(cat AGENTS.md)" = '# Newer user instructions' ]
  [ ! -e .concurrent-agents.md ]
}

@test "review works with Codex structured output" {
  printf '%s\n' '# Existing project instructions' > AGENTS.md
  write_review_response $'# Existing project instructions\n\n'"$managed_placeholder"
  cat > "$fake_bin/codex" <<EOF
#!/bin/bash
printf '%s\\n' "\$*" > "$test_root/codex-args.log"
result_file=""
while [[ \$# -gt 0 ]]; do
  if [[ "\$1" == "--output-last-message" ]]; then
    result_file="\$2"
    shift 2
  else
    shift
  fi
done
cat "$test_root/provider-response.json" > "\$result_file"
EOF
  chmod +x "$fake_bin/codex"

  unset AGENT_READY_SETUP_MERGE_MODEL AGENT_READY_SETUP_MERGE_REASONING_EFFORT
  PATH="$fake_bin:$PATH" run bash "$skill_dir/scripts/merge-instructions.sh" \
    --provider codex --stack node --skill-dir "$skill_dir"

  [ "$status" -eq 0 ]
  grep -Fq -- '--model gpt-6-luna -c model_reasoning_effort="high"' "$test_root/codex-args.log"
  [ "$(cat AGENTS.md)" = "$(printf '%s\n\n%s' '# Existing project instructions' "$(render_managed_block node)")" ]
  [ -f .git/info/agent-ready-instructions-reviewed.sha256 ]
}

@test "existing merge lock prevents a second provider invocation" {
  printf '%s\n' '# Keep this file' > AGENTS.md
  mkdir -p .agents/.agent-ready-instructions.lock
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf '%s\n' called > "$CLAUDE_CALL_LOG"
EOF
  chmod +x "$fake_bin/claude"

  CLAUDE_CALL_LOG="$test_root/claude-called.log" PATH="$fake_bin:$PATH" \
    run bash "$skill_dir/scripts/merge-instructions.sh" \
      --provider claude --stack node --skill-dir "$skill_dir"

  [ "$status" -eq 2 ]
  [ ! -e "$test_root/claude-called.log" ]
  [[ "$output" == *"another instruction merge is running"* ]]
}

@test "missing AGENTS is created from template without invoking provider" {
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf '%s\n' called > "$CLAUDE_CALL_LOG"
EOF
  chmod +x "$fake_bin/claude"

  CLAUDE_CALL_LOG="$test_root/claude-called.log" PATH="$fake_bin:$PATH" \
    run bash "$skill_dir/scripts/merge-instructions.sh" \
      --provider claude --stack node --skill-dir "$skill_dir"

  [ "$status" -eq 0 ]
  [ -f AGENTS.md ]
  grep -Fq '# [Project Name]' AGENTS.md
  grep -Fxq '<!-- BEGIN AGENT-READY MANAGED -->' AGENTS.md
  grep -Fxq '## Centralización recursiva de instrucciones' AGENTS.md
  [ ! -e "$test_root/claude-called.log" ]
}

run_apply_managed_block() {
  local stack="$1"

  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
printf '%s\\n' called >> "$test_root/provider-calls.log"
exit 1
EOF
  chmod +x "$fake_bin/claude"
  PATH="$fake_bin:$PATH" run bash "$skill_dir/scripts/apply-managed-block.sh" --stack "$stack" --skill-dir "$skill_dir"
}

@test "apply-managed-block replaces the verbatim block without invoking the provider" {
  cat > AGENTS.md <<'EOF'
# Project

<!-- BEGIN AGENT-READY MANAGED -->
- Read and follow `.agents/rules/retired.md`.
<!-- END AGENT-READY MANAGED -->

## Ownership

Team Astra owns this service.
EOF

  run_apply_managed_block node

  [ "$status" -eq 0 ]
  [ "$(provider_call_count)" -eq 0 ]
  ! grep -Fq 'retired.md' AGENTS.md
  grep -Fxq 'Team Astra owns this service.' AGENTS.md
  [[ "$output" == *"redundancy review runs in the background"* ]]
  bash "$skill_dir/scripts/render-instruction-template.sh" --validate AGENTS.md \
    --rules-dir "$skill_dir/assets/stacks/node/rules" \
    --common-rules-dir "$skill_dir/assets/common/rules"

  run_apply_managed_block node
  [ "$status" -eq 0 ]
  [[ "$output" == *"managed block is current"* ]]
}

@test "apply-managed-block leaves legacy AGENTS for the background review" {
  printf '%s\n' '# Legacy project' '' '## Rules' '' '- Legacy rule list.' > AGENTS.md
  cp AGENTS.md "$test_root/original-agents.md"

  run_apply_managed_block node

  [ "$status" -eq 0 ]
  [ "$(provider_call_count)" -eq 0 ]
  cmp -s AGENTS.md "$test_root/original-agents.md"
  [[ "$output" == *"no managed markers yet"* ]]
}

@test "apply-managed-block creates missing AGENTS from the template" {
  run_apply_managed_block frontend

  [ "$status" -eq 0 ]
  [ "$(provider_call_count)" -eq 0 ]
  [ "$(grep -c '^<!-- BEGIN AGENT-READY MANAGED -->$' AGENTS.md)" -eq 1 ]
}

@test "automatic sync hook runs upgrade, projection, and merge in order" {
  source_dir="$test_root/agent-ready-setup"
  event_log="$test_root/hook-events.log"
  merge_log="$test_root/hook-merge.log"
  mkdir -p \
    "$source_dir/assets/common/hooks" \
    "$source_dir/assets/codex" \
    "$source_dir/assets/stacks/frontend/hooks" \
    "$source_dir/scripts"
  touch "$source_dir/SKILL.md"
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
    "$source_dir/assets/common/hooks/sync-marketplace.sh"
  cp "$skill_dir/scripts/asset-sync-common.sh" "$source_dir/scripts/asset-sync-common.sh"
  # Minimal sources still need the profile catalog and the state helper the hook resolves.
  cp "$skill_dir/scripts/agent-ready-state.py" "$source_dir/scripts/agent-ready-state.py"
  cp "$skill_dir/assets/profiles.json" "$source_dir/assets/profiles.json"
  cp "$skill_dir/scripts/merge-managed-settings.py" "$source_dir/scripts/merge-managed-settings.py"
  printf '%s\n' '#!/bin/bash' > "$source_dir/scripts/normalize-instructions.sh"
  cp "$skill_dir/scripts/run-detached.py" "$source_dir/scripts/run-detached.py"
  printf '%s\n' '{}' > "$source_dir/assets/common/settings.json"
  printf '%s\n' '{}' > "$source_dir/assets/codex/hooks.json"
  cat > "$source_dir/scripts/apply-managed-block.sh" <<'EOF'
#!/bin/bash
printf 'apply\n' >> "$EVENT_LOG"
EOF
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
[[ "${AGENT_READY_SETUP_NON_INTERACTIVE:-0}" == "1" ]] || exit 99
printf '%s\n' "$*" > "$MERGE_LOG"
printf 'merge\n' >> "$EVENT_LOG"
EOF
  chmod +x "$source_dir/scripts/merge-instructions.sh"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf 'upgrade\n' >> "$EVENT_LOG"
EOF
  chmod +x "$fake_bin/claude"
  printf '%s\n' '{"dependencies":{"react":"1.0.0"}}' > package.json

  EVENT_LOG="$event_log" \
    MERGE_LOG="$merge_log" \
    AGENT_READY_SETUP_SKILL_DIR="$source_dir" \
    AGENT_READY_SETUP_BROWSER_INSTALL=0 \
    PATH="$fake_bin:$PATH" \
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude
  [ "$status" -eq 0 ]
  wait_for_file_containing "$event_log" "merge"
  [ "$(sed -n '1p' "$event_log")" = "upgrade" ]
  [ "$(sed -n '2p' "$event_log")" = "apply" ]
  [ "$(sed -n '3p' "$event_log")" = "merge" ]
  [ "$(wc -l < "$event_log")" -eq 3 ]
  grep -Fq -- "Sync hook updated; restarting with latest version." <<< "$output"
  [ -f .agents/hooks/sync-marketplace.sh ]
  cmp -s .agents/hooks/sync-marketplace.sh "$source_dir/assets/common/hooks/sync-marketplace.sh"
  expected_skill_dir="$source_dir"
  # Git Bash translates paths passed to native Windows Python (run-detached.py) into C:/ form.
  if command -v cygpath >/dev/null 2>&1 && grep -Fq -- "$(cygpath -m "$source_dir")" "$merge_log"; then
    expected_skill_dir="$(cygpath -m "$source_dir")"
  fi
  grep -Fq -- "--provider claude --stack frontend --skill-dir $expected_skill_dir" "$merge_log"
}

@test "automatic sync hook preserves session when the managed block needs human review" {
  source_dir="$test_root/agent-ready-setup"
  mkdir -p \
    "$source_dir/assets/common/hooks" \
    "$source_dir/assets/codex" \
    "$source_dir/assets/stacks/node/hooks" \
    "$source_dir/scripts"
  touch "$source_dir/SKILL.md"
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
    "$source_dir/assets/common/hooks/sync-marketplace.sh"
  cp "$skill_dir/scripts/asset-sync-common.sh" "$source_dir/scripts/asset-sync-common.sh"
  # Minimal sources still need the profile catalog and the state helper the hook resolves.
  cp "$skill_dir/scripts/agent-ready-state.py" "$source_dir/scripts/agent-ready-state.py"
  cp "$skill_dir/assets/profiles.json" "$source_dir/assets/profiles.json"
  cp "$skill_dir/scripts/merge-managed-settings.py" "$source_dir/scripts/merge-managed-settings.py"
  printf '%s\n' '#!/bin/bash' > "$source_dir/scripts/normalize-instructions.sh"
  printf '%s\n' '{}' > "$source_dir/assets/common/settings.json"
  printf '%s\n' '{}' > "$source_dir/assets/codex/hooks.json"
  cat > "$source_dir/scripts/apply-managed-block.sh" <<'EOF'
#!/bin/bash
exit 2
EOF
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
exit 0
EOF
  chmod +x "$fake_bin/claude"
  printf '%s\n' '{}' > package.json

  AGENT_READY_SETUP_SKILL_DIR="$source_dir" PATH="$fake_bin:$PATH" \
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude --stack node
  [ "$status" -eq 0 ]
  [[ "$output" == *"requires human review"* ]]
}
