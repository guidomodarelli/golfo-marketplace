#!/usr/bin/env bats
# Declarative detection contract of agent-ready-setup: signals, selection
# precedence, deterministic primary stack and suggestions that are never applied.

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  cli_calls="$test_root/cli-calls.log"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  # Sync flows run with an empty home: nothing installed on this machine may decide them.
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_TOOLS=0
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  export AGENT_READY_SETUP_SYNC_FOREGROUND=1
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_REVIEW_MODE
  unset AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES
  # Fake provider CLIs record every call, so tests can prove read-only modes stay offline.
  for provider_cli in claude codex; do
    cat > "$fake_bin/$provider_cli" <<EOF
#!/bin/bash
printf '%s %s\n' "$provider_cli" "\$*" >> "$cli_calls"
exit 0
EOF
    chmod +x "$fake_bin/$provider_cli"
  done
  git -C "$project_dir" -c init.defaultBranch=main init -q
  cd "$project_dir"
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

run_detect() {
  run python3 "$skill_dir/scripts/agent-ready-state.py" detect --project . --skill-dir "${1:-$skill_dir}"
}

run_bootstrap() {
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" --skill-dir "$skill_dir" --provider claude "$@"
}

run_sync_hook() {
  mkdir -p .agents/hooks
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh
  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
}

# Content fingerprint of the project tree, including symlink targets.
tree_fingerprint() {
  find . -path ./.git -prune -o -print | LC_ALL=C sort | while IFS= read -r path; do
    if [[ -L "$path" ]]; then
      printf 'L %s %s\n' "$path" "$(readlink "$path")"
    elif [[ -f "$path" ]]; then
      printf 'F %s %s\n' "$path" "$(cksum < "$path")"
    else
      printf 'D %s\n' "$path"
    fi
  done
}

json_value() {
  python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(eval(sys.argv[2], {"data": data}))' "$1" "$2" | tr -d '\r'
}

manifest_profiles() {
  json_value .agents/agent-ready.json '",".join(data["profiles"])'
}

# Copy of the skill whose catalog a test edits; the Python expression receives it as `catalog`.
copy_skill_with_catalog() {
  source_copy="$test_root/skill"
  cp -R "$skill_dir" "$source_copy"
  python3 - "$source_copy/assets/profiles.json" "$1" <<'PY'
import json, sys
path, expression = sys.argv[1:]
with open(path, encoding="utf-8") as catalog_file:
    catalog = json.load(catalog_file)
exec(expression, {"catalog": catalog})
with open(path, "w", encoding="utf-8") as catalog_file:
    json.dump(catalog, catalog_file)
PY
}

@test "React wins over the generic Node signal and explains why" {
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > package.json

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: react" ]]
  [[ "$output" == *"react: package.json declares react in dependencies"* ]]
  [[ "$output" == *"node: package.json exists (superseded by react)"* ]]
}

@test "React declared only as a peer dependency still selects react" {
  printf '%s\n' '{"peerDependencies": {"react": "*"}}' > package.json

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: react" ]]
  [[ "$output" == *"declares react in peerDependencies"* ]]
}

@test "the word react outside the dependency fields is not a signal" {
  printf '%s\n' '{"keywords": ["react"], "scripts": {"react": "true"}}' > package.json

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: node" ]]
}

@test "Android wins over the generic Gradle signal and explains why" {
  printf '%s\n' 'plugins {}' > build.gradle.kts
  mkdir -p feature/login/src/main
  printf '%s\n' '<manifest />' > feature/login/src/main/AndroidManifest.xml

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: android" ]]
  [[ "$output" == *"feature/login/src/main/AndroidManifest.xml matches */*/src/main/AndroidManifest.xml"* ]]
  [[ "$output" == *"java: build.gradle.kts exists (superseded by android)"* ]]
}

@test "each single stack is detected from its own signal" {
  for fixture in pom.xml:java build.gradle:java settings.gradle.kts:java go.mod:go package.json:node; do
    file_name="${fixture%%:*}"
    expected_stack="${fixture##*:}"
    printf '{}\n' > "$file_name"
    run_detect
    [ "$status" -eq 0 ]
    [[ "${lines[0]}" == "Stack: $expected_stack" ]]
    rm "$file_name"
  done
}

@test "stacks without priority between them are ambiguous and listed with their evidence" {
  printf '{}\n' > package.json
  printf 'module example\n' > go.mod

  run_detect
  [ "$status" -eq 3 ]
  [[ "${lines[0]}" == "Stack: ambiguous (go, node)" ]]
  [[ "$output" == *"go: go.mod exists"* ]]
  [[ "$output" == *"node: package.json exists"* ]]
  [[ "$output" == *"select one explicitly"* ]]
}

@test "an ambiguous repository fails before writing, and an explicit stack resolves it" {
  printf '{}\n' > package.json
  printf 'module example\n' > go.mod
  before="$(tree_fingerprint)"

  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"Stack: ambiguous (go, node)"* ]]
  [[ "$output" == *"go: go.mod exists"* ]]
  [[ "$output" == *"could not detect project stack; pass --profiles or --stack"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e "$cli_calls" ]

  run_bootstrap --stack go
  [ "$status" -eq 0 ]
  [ "$(manifest_profiles)" = "go" ]
}

@test "a repository without signals fails before writing and names the available stacks" {
  before="$(tree_fingerprint)"

  run_detect
  [ "$status" -eq 3 ]
  [[ "${lines[0]}" == "Stack: none" ]]

  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"Stack: none"* ]]
  [[ "$output" == *"android, go, java, nextjs, nextjs-app-router, node, react"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "SessionStart reports an ambiguous repository and skips the projection" {
  printf '{}\n' > package.json
  printf 'module example\n' > go.mod

  run_sync_hook
  [ "$status" -eq 0 ]
  [[ "$output" == *"several stacks match and none has priority"* ]]
  [[ "$output" == *"local projection skipped"* ]]
  [ ! -e .agents/agent-ready.lock.json ]
}

@test "the state commands name the matches when a repository has no selection" {
  printf '{}
' > package.json
  printf 'module example
' > go.mod
  for state_command in resolve plan; do
    run python3 "$skill_dir/scripts/agent-ready-state.py" "$state_command" --project . --skill-dir "$skill_dir"
    [ "$status" -eq 2 ]
    [[ "$output" == *"go (go.mod exists), node (package.json exists)"* ]]
    [[ "$output" == *"--stack android|go|java|nextjs|nextjs-app-router|node|react"* ]]
  done
}

@test "status works in a repository without a selection" {
  run_bootstrap --status
  [ "$status" -eq 0 ]
  [[ "$output" == *"no profiles selected"* ]]
}

@test "the initial detection is persisted with the stack defaults and shown to the user" {
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > package.json

  run_bootstrap
  [ "$status" -eq 0 ]
  [[ "$output" == *"Detected stack: react (package.json declares react in dependencies)"* ]]
  [[ "$output" == *"Stack: react"* ]]
  [ "$(manifest_profiles)" = "react" ]
}

@test "the android defaults stay without browser after a detection" {
  mkdir -p app/src/main
  printf '%s\n' '<manifest />' > app/src/main/AndroidManifest.xml

  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(manifest_profiles)" = "android" ]
}

@test "explicit flags win over the manifest, and the manifest wins over detection" {
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > package.json
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  [ "$(manifest_profiles)" = "node" ]

  # The signals still say React: the persisted selection does not move.
  manifest_before="$(cksum < .agents/agent-ready.json)"
  lock_before="$(cksum < .agents/agent-ready.lock.json)"
  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.lock.json 'data["primaryStack"]')" = "node" ]
  [ "$(cksum < .agents/agent-ready.json)" = "$manifest_before" ]
  [ "$(cksum < .agents/agent-ready.lock.json)" = "$lock_before" ]

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Selected by: manifest"* ]]
  [[ "$output" == *"Signals point to react, but the selection from manifest keeps node"* ]]

  run_bootstrap --plan --profiles go
  [ "$status" -eq 0 ]
  [[ "$output" == *"Selected by: --profiles"* ]]
  [[ "$output" == *"Profiles: go, browser (primary stack: go)"* ]]
}

@test "a detected capability is only a suggestion with evidence, also on the initial apply" {
  mkdir -p app/src/main
  printf '%s\n' '<manifest />' > app/src/main/AndroidManifest.xml
  printf '%s\n' 'dependencies { implementation("androidx.webkit:webkit:1.12.0") }' > app/build.gradle.kts

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"? browser: app/build.gradle.kts declares the Gradle dependency androidx.webkit:webkit"* ]]
  [[ "$output" == *"Adopt them with --profiles android,browser"* ]]

  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(manifest_profiles)" = "android" ]
  [ "$(json_value .agents/agent-ready.lock.json '",".join(data["profileOrder"])')" = "android" ]
  [ "$(json_value .agents/agent-ready.lock.json 'sorted(data["profiles"])')" = "['android', 'common']" ]
}

@test "a capability already selected is not suggested again" {
  printf '%s\n' '{"devDependencies": {"@playwright/test": "1.0.0"}}' > package.json

  run_bootstrap --plan --profiles node,browser
  [ "$status" -eq 0 ]
  [[ "$output" != *"Suggestions"* ]]

  # node brings browser by default: only a repository that leaves it out gets the suggestion.
  mkdir -p .agents
  printf '%s\n' '{"profiles": ["node"], "excludedDefaults": ["browser"]}' > .agents/agent-ready.json
  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"? browser: package.json declares @playwright/test in devDependencies"* ]]
}

@test "business-flows stays manual: no signal selects or suggests it" {
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > package.json
  mkdir -p flows
  printf 'flow\n' > flows/checkout.md

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" != *"? business-flows"* ]]
  [[ "$output" != *"[business-flows]"* ]]
}

@test "the Gradle formats documented in the contract are recognized in scripts" {
  mkdir -p module
  for script in \
    "plugins { id 'com.android.application' }" \
    'plugins { id "com.android.library" version "8.0.0" apply false }' \
    'plugins { id("com.android.application") }' \
    "apply plugin: 'com.android.library'" \
    'apply(plugin = "com.android.application")'
  do
    printf '%s\n' "$script" > module/build.gradle
    run_detect
    [ "$status" -eq 0 ]
    [[ "${lines[0]}" == "Stack: android" ]]
    [[ "$output" == *"module/build.gradle declares the Gradle plugin com.android."* ]]
  done
}

@test "a Gradle version catalog declares plugins and libraries in its sections" {
  mkdir -p gradle
  cat > gradle/libs.versions.toml <<'EOF'
[versions]
agp = "8.5.0"

[libraries]
webkit = { group = "androidx.webkit", name = "webkit", version = "1.12.0" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
EOF

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: android" ]]
  [[ "$output" == *"gradle/libs.versions.toml declares the Gradle plugin com.android.application"* ]]
  [[ "$output" == *"? browser: gradle/libs.versions.toml declares the Gradle dependency androidx.webkit:webkit"* ]]
}

@test "commented-out Gradle declarations and look-alike ids are not signals" {
  cat > build.gradle.kts <<'EOF'
// id("com.android.application")
/* apply(plugin = "com.android.library") */
plugins { id("com.android.application.extra") }
val site = "https://example.com" // id("com.android.library")
EOF

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: java" ]]
  [[ "$output" != *"com.android"* ]]
}

@test "the result does not depend on the order of the catalog or the signals" {
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}, "devDependencies": {"cypress": "1.0.0"}}' > package.json
  printf 'module example\n' > go.mod
  run_detect
  expected_status="$status"
  expected_output="$output"
  [ "$expected_status" -eq 3 ]

  copy_skill_with_catalog 'catalog["profiles"] = dict(reversed(list(catalog["profiles"].items())))
for profile in catalog["profiles"].values():
    if "detect" in profile:
        profile["detect"]["signals"].reverse()'
  run_detect "$source_copy"
  [ "$status" -eq "$expected_status" ]
  [ "$output" = "$expected_output" ]
}

@test "an invalid detect block stops the catalog before anything is written" {
  printf '{}\n' > package.json
  before="$(tree_fingerprint)"
  for expression in \
    'catalog["profiles"]["node"]["detect"]["signals"][0]["type"] = "exec"' \
    'catalog["profiles"]["node"]["detect"]["signals"][0]["paths"] = ["../outside.json"]' \
    'catalog["profiles"]["node"]["detect"]["signals"][0]["paths"] = ["*.json"]' \
    'catalog["profiles"]["browser"]["detect"]["supersedes"] = ["node"]' \
    'catalog["profiles"]["node"]["detect"]["supersedes"] = ["unknown-stack"]' \
    'catalog["profiles"]["java"]["detect"]["supersedes"] = ["react"]; catalog["profiles"]["android"]["detect"]["supersedes"] = ["java"]; catalog["profiles"]["react"]["detect"]["supersedes"] = ["android"]'
  do
    rm -rf "$test_root/skill"
    copy_skill_with_catalog "$expression"
    run_detect "$source_copy"
    [ "$status" -eq 2 ]
    [[ "$output" == *"ERROR: agent-ready profiles: profile catalog"* ]]
    run env PATH="$fake_bin:$PATH" bash "$source_copy/scripts/bootstrap.sh" --skill-dir "$source_copy" --provider claude --stack node
    [ "$status" -ne 0 ]
    [ "$(tree_fingerprint)" = "$before" ]
  done
}

@test "a package.json that cannot be parsed is reported and adds no dependency signals" {
  printf '{ not json' > package.json

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: node" ]]
  [[ "$output" == *"package.json is not valid JSON"* ]]
}

@test "a package.json saved with a byte order mark is still read" {
  printf '\357\273\277{"dependencies": {"react": "19.0.0"}}\n' > package.json

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: react" ]]
}

@test "a symlink that leaves the project is not evidence" {
  mkdir -p "$test_root/outside"
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > "$test_root/outside/package.json"
  ln -s "$test_root/outside/package.json" package.json 2>/dev/null || true
  [ -L package.json ] || skip "requiere symlinks reales (en Windows: Modo de desarrollador o una shell elevada)"

  run_detect
  [ "$status" -eq 3 ]
  [[ "${lines[0]}" == "Stack: none" ]]
}

@test "a symlinked directory is not traversed by a wildcard" {
  mkdir -p "$test_root/outside/src/main"
  printf '%s\n' '<manifest />' > "$test_root/outside/src/main/AndroidManifest.xml"
  ln -s "$test_root/outside" linked 2>/dev/null || true
  [ -L linked ] || skip "requiere symlinks reales (en Windows: Modo de desarrollador o una shell elevada)"

  run_detect
  [ "$status" -eq 3 ]
  [[ "${lines[0]}" == "Stack: none" ]]
}

@test "a recursive glob finds nested files and skips dependency directories" {
  copy_skill_with_catalog 'catalog["profiles"]["business-flows"]["detect"] = {"signals": [{"type": "glob", "patterns": ["**/flows/*.flow.yaml"]}]}'
  printf 'module example\n' > go.mod
  mkdir -p node_modules/vendor-package/flows
  printf 'flow\n' > node_modules/vendor-package/flows/checkout.flow.yaml

  run_detect "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" != *"business-flows"* ]]

  mkdir -p services/billing/flows
  printf 'flow\n' > services/billing/flows/refund.flow.yaml
  run_detect "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *"? business-flows: services/billing/flows/refund.flow.yaml matches **/flows/*.flow.yaml"* ]]
}

@test "detect and plan are read-only and never call the provider CLI or a package script" {
  cat > package.json <<'EOF'
{
  "scripts": { "preinstall": "touch executed-preinstall", "prepare": "touch executed-prepare" },
  "dependencies": { "react": "19.0.0" }
}
EOF
  printf '%s\n' 'file("executed-gradle").writeText("ran")' > build.gradle.kts
  before="$(tree_fingerprint)"

  run_detect
  [ "$status" -eq 3 ]
  run_bootstrap --plan --offline --stack react
  [ "$status" -eq 0 ]

  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e "$cli_calls" ]
}

@test "editing only the detection signals of a release does not report an update" {
  source_copy="$test_root/skill"
  cp -R "$skill_dir" "$source_copy"
  printf 'module example\n' > go.mod
  run env PATH="$fake_bin:$PATH" bash "$source_copy/scripts/bootstrap.sh" --skill-dir "$source_copy" --provider claude
  [ "$status" -eq 0 ]
  lock_before="$(cksum < .agents/agent-ready.lock.json)"

  python3 - "$source_copy/assets/profiles.json" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as catalog_file:
    catalog = json.load(catalog_file)
catalog["profiles"]["go"]["detect"]["signals"].append({"type": "file", "paths": ["go.work"]})
with open(path, "w", encoding="utf-8") as catalog_file:
    json.dump(catalog, catalog_file)
PY

  run python3 "$source_copy/scripts/agent-ready-state.py" status --project . --skill-dir "$source_copy" --check
  [ "$status" -eq 0 ]
  [[ "$output" == *"Source matches the lock"* ]]
  run env PATH="$fake_bin:$PATH" bash "$source_copy/scripts/bootstrap.sh" --skill-dir "$source_copy" --provider claude
  [ "$status" -eq 0 ]
  [ "$(cksum < .agents/agent-ready.lock.json)" = "$lock_before" ]
}

@test "a repository with a manifest and no signals keeps working without detection" {
  run_bootstrap --stack go
  [ "$status" -eq 0 ]
  before="$(cksum < .agents/agent-ready.json)"

  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(cksum < .agents/agent-ready.json)" = "$before" ]
  [[ "$output" != *"Detected stack"* ]]
}

@test "a Next.js App Router repository detects the most specific layer" {
  printf '%s\n' '{"dependencies": {"next": "15.0.0", "react": "19.0.0", "react-dom": "19.0.0"}}' > package.json
  mkdir -p src/app
  printf '%s\n' 'export default function RootLayout() {}' > src/app/layout.tsx

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: nextjs-app-router" ]]
  [[ "$output" == *"nextjs: package.json declares next in dependencies (superseded by nextjs-app-router)"* ]]
  [[ "$output" == *"react: package.json declares react in dependencies; package.json declares react-dom in dependencies (superseded by nextjs, nextjs-app-router)"* ]]
  # react supersedes node, and so do the layers that require it.
  [[ "$output" == *"node: package.json exists (superseded by nextjs, nextjs-app-router, react)"* ]]
}

@test "a Next.js repository without the App Router stops at the nextjs layer" {
  printf '%s\n' '{"dependencies": {"next": "15.0.0", "react": "19.0.0"}}' > package.json
  mkdir -p pages
  printf '%s\n' 'export default function Home() {}' > pages/index.tsx

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: nextjs" ]]
}

@test "a detected layer brings the layers it extends through requires, with no asset twice" {
  printf '%s\n' '{"dependencies": {"next": "15.0.0", "react": "19.0.0"}}' > package.json
  mkdir -p app
  printf '%s\n' 'export default function RootLayout() {}' > app/layout.tsx

  run python3 "$skill_dir/scripts/agent-ready-state.py" resolve --project . --skill-dir "$skill_dir" \
    --compose-dir "$test_root/compose"
  [ "$status" -eq 0 ]
  [[ "$output" == *$'profiles\treact,nextjs,nextjs-app-router,browser'* ]]
  [[ "$output" == *$'primary\tnextjs-app-router'* ]]
  stack_dir="$(printf '%s\n' "$output" | sed -n 's/^stack_dir\t//p' | tr -d '\r')"
  # Each layer publishes its own assets; the composed tree has all of them once.
  [ -f "$stack_dir/rules/react-style.md" ]
  [ -f "$stack_dir/rules/server-first-data-flow.md" ]
  [ -f "$stack_dir/rules/nextjs-app-router.md" ]
  [ -f "$stack_dir/skills/api-endpoint/SKILL.md" ]
  [ -f "$stack_dir/commands/react-review-pr.md" ]
}

@test "a layer that its own required layer supersedes is a cycle in the catalog" {
  before="$(tree_fingerprint)"
  copy_skill_with_catalog 'catalog["profiles"]["react"]["detect"]["supersedes"] = ["node", "android", "nextjs"]'
  run_detect "$source_copy"
  [ "$status" -eq 2 ]
  [[ "$output" == *"stack priorities form a cycle"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "an app/layout.tsx without the next dependency is not the App Router" {
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > package.json
  mkdir -p src/app
  printf '%s\n' 'export default function Layout() {}' > src/app/layout.tsx

  run_detect
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: react" ]]
  [[ "$output" != *"nextjs-app-router"* ]]
}

@test "a capability that requires a stack leaves that stack as the primary one" {
  copy_skill_with_catalog 'catalog["profiles"]["node-extras"] = {"kind": "capability", "description": "Extras.", "requires": ["node"]}'
  run python3 "$source_copy/scripts/agent-ready-state.py" resolve --project . --skill-dir "$source_copy" \
    --profiles node-extras --compose-dir "$test_root/compose"
  [ "$status" -eq 0 ]
  [[ "$output" == *$'primary\tnode'* ]]
}

run_resolve() {
  run python3 "$skill_dir/scripts/agent-ready-state.py" resolve --project . --skill-dir "${1:-$skill_dir}" \
    --compose-dir "$test_root/compose"
}

@test "the manifest keeps what was chosen and each resolution brings the defaults of the profiles" {
  mkdir -p .agents
  printf '%s\n' '{"profiles": ["node"]}' > .agents/agent-ready.json
  run_resolve
  [ "$status" -eq 0 ]
  [[ "$output" == *$'profiles\tnode,browser'* ]]
  [[ "$output" == *$'requested\tnode'* ]]

  # A layer brings the defaults of the layers it requires.
  printf '%s\n' '{"profiles": ["nextjs"]}' > .agents/agent-ready.json
  run_resolve
  [[ "$output" == *$'profiles\treact,nextjs,browser'* ]]

  # android declares no defaults.
  printf '%s\n' '{"profiles": ["android"]}' > .agents/agent-ready.json
  run_resolve
  [[ "$output" == *$'profiles\tandroid'* && "$output" != *$'profiles\tandroid,'* ]]
}

@test "excludedDefaults leaves a default out, and cannot leave out what the selection needs" {
  mkdir -p .agents
  printf '%s\n' '{"profiles": ["node"], "excludedDefaults": ["browser"]}' > .agents/agent-ready.json
  run_resolve
  [ "$status" -eq 0 ]
  [[ "$output" == *$'profiles\tnode'* && "$output" != *$'profiles\tnode,'* ]]

  printf '%s\n' '{"profiles": ["nextjs"], "excludedDefaults": ["react"]}' > .agents/agent-ready.json
  run_resolve
  [ "$status" -ne 0 ]
  [[ "$output" == *"excludedDefaults lists 'react', but the selection needs it (required by nextjs)"* ]]
}

@test "plan says which profile each added profile came from" {
  mkdir -p .agents
  printf '%s\n' '{"profiles": ["nextjs"]}' > .agents/agent-ready.json
  run python3 "$skill_dir/scripts/agent-ready-state.py" plan --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Profile added: react (required by nextjs)"* ]]
  [[ "$output" == *"Profile added: browser (default of react)"* ]]
}

@test "a bundle resolves the profiles it groups and publishes nothing of its own" {
  copy_skill_with_catalog 'catalog["profiles"]["web-team"] = {"kind": "bundle", "description": "What the web team selects.", "requires": ["nextjs-app-router", "business-flows"]}'
  mkdir -p .agents
  printf '%s\n' '{"profiles": ["web-team"]}' > .agents/agent-ready.json
  run_resolve "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *$'profiles\treact,nextjs,nextjs-app-router,business-flows,web-team,browser'* ]]
  [[ "$output" == *$'requested\tweb-team'* ]]
  [[ "$output" == *$'primary\tnextjs-app-router'* ]]
}

@test "a bundle that publishes something or groups nothing invalidates the catalog" {
  for expression in \
    'catalog["profiles"]["web-team"] = {"kind": "bundle", "requires": ["react"], "assets": "assets/stacks/react"}' \
    'catalog["profiles"]["web-team"] = {"kind": "bundle", "requires": ["react"], "defaults": ["browser"]}' \
    'catalog["profiles"]["web-team"] = {"kind": "bundle"}' \
    'catalog["profiles"]["node"]["defaults"] = "browser"'
  do
    rm -rf "$test_root/skill"
    copy_skill_with_catalog "$expression"
    run_detect "$source_copy"
    [ "$status" -eq 2 ]
    [[ "$output" == *"ERROR: agent-ready profiles:"* ]]
  done
}
