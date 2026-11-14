#!/usr/bin/env bats
# The content of agent-ready-setup (sources.golfo): a content pack at a revision, fetched with Git into
# the user cache and composed with the installed engine, which carries no content. The official pack
# is a local repository reached at its real URL through url.insteadOf, so the manifests and the lock
# keep the real origin; a few tests use the development override (AGENT_READY_SETUP_CONTENT_DIR).

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  cli="$skill_dir/scripts/agent-ready"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  source "$BATS_TEST_DIRNAME/content-pack.bash"
  use_content_pack
  export XDG_CONFIG_HOME="$test_root/config"
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_ORGANIZATION_CONFIG="$test_root/organization/config.json"
  export AGENT_READY_SETUP_TOOLS=0
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  export GIT_CONFIG_GLOBAL="$test_root/gitconfig"
  git config --global user.name Test
  git config --global user.email test@example.invalid
  git config --global init.defaultBranch main
  git config --global core.autocrlf false
  git config --global protocol.file.allow always
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_REVIEW_MODE
  unset AGENT_READY_SETUP_CI AGENT_READY_SETUP_REFRESH AGENT_READY_SETUP_DETECTION
  for provider_cli in claude codex; do
    printf '#!/bin/bash\nexit 0\n' > "$fake_bin/$provider_cli"
    chmod +x "$fake_bin/$provider_cli"
  done
  git -C "$project_dir" init -q
  cd "$project_dir"
  printf '{}\n' > package.json
}

teardown() {
  cd "$repository_root"
  local removal_attempt
  for removal_attempt in $(seq 1 50); do
    rm -rf "$test_root" 2>/dev/null && return 0
    sleep 0.2
  done
  rm -rf "$test_root"
}

run_cli() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$cli" "$@"
}

native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

lock_value() {
  python3 -c 'import json,sys; data=json.load(open(".agents/agent-ready.lock.json", encoding="utf-8")); print(eval(sys.argv[1], {"data": data}))' "$1" | tr -d '\r'
}

write_manifest() {
  mkdir -p .agents
  printf '%s\n' "$1" > .agents/agent-ready.json
}

# A new commit of the content repository: one line more in a rule of the base.
advance_content_repository() {
  printf '%s\n' "${1:-A newer sentence of the content.}" >> "$content_repository/base/rules/verify-changes.md"
  git -C "$content_repository" commit -qam "${2:-advance the content}"
  content_revision="$(git -C "$content_repository" rev-parse HEAD)"
}

# Change the catalog of the content repository (the expression receives it as `data`) and commit it.
edit_content_catalog() {
  python3 - "$content_repository/agent-ready-pack.json" "$1" <<'PY'
import json, sys
path, expression = sys.argv[1:]
data = json.load(open(path, encoding="utf-8"))
exec(expression, {"data": data})
json.dump(data, open(path, "w", encoding="utf-8"), indent=2)
PY
  git -C "$content_repository" commit -qam "edit the catalog"
  content_revision="$(git -C "$content_repository" rev-parse HEAD)"
}

wait_for_background_update() {
  local attempt
  for attempt in $(seq 1 300); do
    if [ -n "$(find "$XDG_CACHE_HOME/agent-ready-setup/updates" -name '*.json' 2>/dev/null | head -n 1)" ] && \
      [ "$(find "$XDG_CACHE_HOME/agent-ready-setup/updates" -name '*.lock' 2>/dev/null | wc -l)" -eq 0 ]; then
      return 0
    fi
    sleep 0.2
  done
  echo "the background update did not finish" >&2
  return 1
}

@test "without declaring anything the content comes from the official pack, following main" {
  publish_content_pack_repository
  run_cli apply --stack node
  [ "$status" -eq 0 ]
  [ -f .agents/rules/node-security.md ]
  [ "$(lock_value '[data["source"][key] for key in ("name", "kind", "revision", "origin", "requestedRef", "version")]')" = \
    "['golfo', 'git', '$content_revision', 'https://github.com/guidomodarelli/golfo-agent-profiles', 'main', '1.0.0']" ]
  # The engine projected it: its hooks are the installed engine's.
  cmp -s .agents/hooks/check-harness-consistency.sh "$skill_dir/assets/common/hooks/check-harness-consistency.sh"
  run_cli status
  [[ "$output" == *"Locked source: golfo 1.0.0 (git, revision ${content_revision:0:12}, from https://github.com/guidomodarelli/golfo-agent-profiles"* ]]

  # In auto, the next apply adopts what main has.
  advance_content_repository 'Content of the next commit.'
  run_cli apply
  [ "$status" -eq 0 ]
  grep -Fq 'Content of the next commit.' .agents/rules/verify-changes.md
  [ "$(lock_value 'data["source"]["revision"]')" = "$content_revision" ]
}

@test "pinned content keeps its revision until agent-ready update golfo adopts its ref" {
  publish_content_pack_repository
  first_revision="$content_revision"
  write_manifest '{"profiles": ["node"], "sources": {"golfo": {"updates": "pinned"}}}'
  # There is no installed content to start from: the first apply adopts the ref.
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]

  advance_content_repository 'A pinned repository waits for this.'
  rm .agents/rules/verify-changes.md
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -Fq 'A pinned repository waits for this.' .agents/rules/verify-changes.md
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]

  run_cli update golfo
  [ "$status" -eq 0 ]
  grep -Fq 'A pinned repository waits for this.' .agents/rules/verify-changes.md
  [ "$(lock_value 'data["source"]["revision"]')" = "$content_revision" ]

  # --to adopts exactly that revision.
  run_cli update golfo --to "$first_revision"
  [ "$status" -eq 0 ]
  ! grep -Fq 'A pinned repository waits for this.' .agents/rules/verify-changes.md
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]
}

@test "update --to needs exactly one source and golfo is always a known source" {
  publish_content_pack_repository
  run_cli apply --stack node
  [ "$status" -eq 0 ]
  run_cli update golfo acme --to main
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"--to needs exactly one source"* ]]
  run_cli update other --to main
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"the sources are: golfo"* ]]
}

@test "sources.golfo.source takes the content of another repository, and changing it adopts other content" {
  publish_content_pack_repository
  git config --global --add "url.file:///$(native_path "$content_repository" | sed 's#^/##').insteadOf" "https://mirror.example.invalid/golfo"
  run_cli apply --stack node
  [ "$status" -eq 0 ]

  # The same commit from a mirror is another source: the lock names it, and only an apply adopts it.
  write_manifest '{"profiles": ["node"], "sources": {"golfo": {"source": "git+https://mirror.example.invalid/golfo"}}}'
  run_cli apply --from-lock
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"the lock comes from other content than the one sources.golfo declares"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value '[data["source"][key] for key in ("revision", "origin")]')" = "['$content_revision', 'https://mirror.example.invalid/golfo']" ]
  run_cli apply --from-lock
  [ "$status" -eq 0 ]
}

@test "a content source that is not a valid content pack stops before writing" {
  publish_content_pack_repository
  write_manifest '{"profiles": ["node"], "sources": {"golfo": {"source": "git+https://github.com/guidomodarelli/golfo-agent-profiles#main"}}}'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"has a revision after '#'; put it in sources.golfo.ref"* ]]
  write_manifest '{"profiles": ["node"], "sources": {"golfo": {"source": "path:./content"}}}'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"sources.golfo.source 'path:./content' must start with git+https:// or git+ssh://"* ]]

  write_manifest '{"profiles": ["node"]}'
  edit_content_catalog 'data["profiles"]["ci-own"] = {"kind": "ci"}'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"declares the CI profile 'ci-own': CI profiles come with the engine"* ]]
  edit_content_catalog 'del data["profiles"]["ci-own"]; data["profiles"]["ci-github"] = {"kind": "capability"}'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"profile 'ci-github' takes the name of a CI profile of the engine"* ]]
  edit_content_catalog 'del data["profiles"]["ci-github"]; data["profiles"]["common"] = {"kind": "capability"}'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"declares a profile named 'common', the name the engine gives the base"* ]]
  mkdir -p "$content_repository/config/rules"
  printf '# Config\n' > "$content_repository/config/rules/node-config.md"
  git -C "$content_repository" add -A
  git -C "$content_repository" commit -qm "assets where the engine keeps its own"
  edit_content_catalog 'del data["profiles"]["common"]; data["profiles"]["node"]["assets"] = "config"'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"puts the assets of 'node' in config/, a name the engine uses"* ]]
  edit_content_catalog 'data["profiles"]["node"]["assets"] = "stacks/node"; del data["baseAssets"]'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"declares no baseAssets"* ]]
  git -C "$content_repository" rm -q agent-ready-pack.json
  git -C "$content_repository" commit -qm "not a content pack"
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"has no agent-ready-pack.json at its root"* ]]
  [ ! -e .agents/rules ]
}

@test "only the content source publishes the base, and no pack takes its name" {
  mkdir -p agent-packs/acme/profiles/team/rules agent-packs/acme/base/rules
  printf '# Team\n' > agent-packs/acme/profiles/team/rules/acme-team.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "baseAssets": "base", "profiles": {"team": {"kind": "capability", "assets": "profiles/team"}}}' > agent-packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node", "acme/team"], "sources": {"packs": [{"name": "acme", "source": "path:./agent-packs/acme"}]}}'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"pack 'acme' declares baseAssets, but only the content source (sources.golfo) publishes the base"* ]]

  mkdir -p agent-packs/golfo
  write_manifest '{"profiles": ["node"], "sources": {"packs": [{"name": "golfo", "source": "path:./agent-packs/golfo"}]}}'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"which is reserved for the content (sources.golfo)"* ]]
  [ ! -e .agents/rules ]
}

@test "a session start without the content in the cache downloads it in the background" {
  publish_content_pack_repository
  run_cli apply --stack node
  [ "$status" -eq 0 ]
  # Another machine: the lock is committed and its cache is empty; main moved since.
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"
  advance_content_repository 'Downloaded in the background.'

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" == *"The golfo content of this repository is not on this machine yet; the sync downloads it in the background."* ]]
  [[ "$output" != *"could not prepare the golfo content"* ]]
  wait_for_background_update
  grep -Fq 'Downloaded in the background.' .agents/rules/verify-changes.md
}

@test "init downloads the content this machine does not have to choose its profiles" {
  publish_content_pack_repository
  run_cli init --profiles node --yes
  [ "$status" -eq 0 ]
  [ -f .agents/rules/node-security.md ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$content_revision" ]
}

@test "offline, content this machine never downloaded stops a run before writing" {
  publish_content_pack_repository
  run_cli apply --stack node
  [ "$status" -eq 0 ]
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"
  before="$(cat .agents/agent-ready.lock.json)"
  run_cli apply --offline
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"is not in the cache of this machine"* ]]
  [ "$(cat .agents/agent-ready.lock.json)" = "$before" ]

  # The check cannot compare with the locked content: the source is unavailable, nothing is outdated.
  run_cli check --offline
  [ "$status" -eq 5 ]
  [[ "$output" == *"source not available"* ]]
  run_cli check
  [ "$status" -eq 0 ]
}

@test "content that needs a newer engine stops before writing" {
  publish_content_pack_repository
  edit_content_catalog 'data["minEngine"] = "99.0.0"'
  run_cli apply --stack node
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"the golfo catalog needs the agent-ready-setup engine 99.0.0 or newer"* ]]
  [ ! -e .agents/rules ]
}

@test "update golfo --dry-run shows the version jump and the changes the content declares" {
  publish_content_pack_repository
  write_manifest '{"profiles": ["node"], "sources": {"golfo": {"updates": "pinned"}}}'
  run_cli apply
  [ "$status" -eq 0 ]
  edit_content_catalog 'data["version"] = "2.0.0"; data["changes"].insert(0, {"version": "2.0.0", "summary": "A rule asks for something new", "breaking": True})'

  run_cli update golfo --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"golfo 1.0.0 -> 2.0.0  (major version jump)"* ]]
  [[ "$output" == *"A rule asks for something new"* ]]
  [ "$(lock_value 'data["source"]["version"]')" = "1.0.0" ]
}

@test "without a selection, detection uses the catalog of the content" {
  copy_content_pack
  # package.json and build.gradle are node and java; a stack of this content supersedes both.
  python3 - "$content_dir/agent-ready-pack.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
data["profiles"]["fullstack"] = {"kind": "stack", "requires": ["software-development"],
                                 "detect": {"supersedes": ["node", "java"], "signals": [{"type": "file", "paths": ["build.gradle"]}]}}
json.dump(data, open(sys.argv[1], "w", encoding="utf-8"), indent=2)
PY
  printf 'plugins {}\n' > build.gradle
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value '"fullstack" in data["profileOrder"]')" = "True" ]
}

@test "the development override projects a local directory as it is" {
  copy_content_pack
  run_cli apply --stack node
  [ "$status" -eq 0 ]
  [ "$(lock_value '[data["source"].get(key) for key in ("kind", "revision", "origin")]')" = "['local', None, 'local']" ]

  printf 'Written in the local directory.\n' >> "$content_dir/base/rules/verify-changes.md"
  run_cli apply
  [ "$status" -eq 0 ]
  grep -Fq 'Written in the local directory.' .agents/rules/verify-changes.md
}

@test "a new engine whose catalog only changes a CI profile composes the content again" {
  # An installed engine that tests can change: the plugin, with the skill without its tests.
  engine_plugin="$test_root/engine/golfo-kit"
  mkdir -p "$engine_plugin/skills"
  cp -R "$repository_root/plugins/golfo-kit/plugin.json" "$repository_root/plugins/golfo-kit/.claude-plugin" \
    "$repository_root/plugins/golfo-kit/.codex-plugin" "$engine_plugin/"
  cp -R "$skill_dir" "$engine_plugin/skills/agent-ready-setup"
  rm -rf "$engine_plugin/skills/agent-ready-setup/tests" "$engine_plugin/skills/agent-ready-setup/evals"
  engine_cli="$engine_plugin/skills/agent-ready-setup/scripts/agent-ready"
  write_manifest '{"profiles": ["node"], "ci": {"provider": "github"}}'
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_cli" plan
  [ "$status" -eq 0 ]
  [[ "$output" == *".github/workflows/agent-ready.yml"* ]]

  # Only the CI catalog of the engine changes: ci-github now takes the files of GitLab, which the engine already has.
  python3 - "$engine_plugin/skills/agent-ready-setup/assets/ci/profiles.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
data["profiles"]["ci-github"]["assets"] = data["profiles"]["ci-gitlab"]["assets"]
json.dump(data, open(sys.argv[1], "w", encoding="utf-8"), indent=2)
PY
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_cli" plan
  [ "$status" -eq 0 ]
  [[ "$output" != *".github/workflows/agent-ready.yml"* ]]
  [[ "$output" == *"gitlab-ci.yml"* ]]
}

@test "remove recognizes the AGENTS.md and CLAUDE.md that the content of the lock generated" {
  publish_content_pack_repository
  git add -A && git commit -qm initial
  run_cli apply --stack node
  [ "$status" -eq 0 ]
  [ -f AGENTS.md ]
  [ -f CLAUDE.md ]
  # Another machine: the cache is empty, and remove downloads the revision of the lock to recognize them.
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"

  run_cli remove --yes < /dev/null
  [ "$status" -eq 0 ]
  [ ! -e AGENTS.md ]
  [ ! -e CLAUDE.md ]
  [ -z "$(git status --porcelain)" ]
}
