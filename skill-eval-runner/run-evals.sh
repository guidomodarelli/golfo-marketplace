#!/bin/bash

# run-evals.sh — Central eval runner for the skill marketplace
# Runs with-skill evals (optionally against a no-skill baseline) using eval-config.json
#
# Usage:
#   run-evals [path/to/skill]        Run evals for a specific skill
#   run-evals                         Run evals for skill in current directory
#   run-evals --all                   Run evals for all skills with eval-config.json
#   run-evals --jobs N [...]          Run N cases in parallel (default: 4, env: EVAL_JOBS)
#   run-evals --provider codex [...]    Run evals with Codex instead of auto-detecting
#   run-evals --baseline [...]        Also run a no-skill baseline per case (env: EVAL_BASELINE=1)
#   run-evals --repeat N [...]        Run every case N times and report flaky cases (env: EVAL_REPEAT)
#
# Each skill only needs evals/eval-config.json — this script handles the rest.

set -e

# ── Colors ──────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# ── Defaults ────────────────────────────────────────────
# Each job fires 1 agent call (with-skill), or 2 concurrent calls when the
# baseline is enabled. Lower EVAL_JOBS if rate-limited.
EVAL_JOBS="${EVAL_JOBS:-4}"
# The no-skill baseline is opt-in: assertions only score the with-skill
# response, so the baseline is a manual comparison artifact that doubles cost.
EVAL_BASELINE="${EVAL_BASELINE:-0}"
# Runs per case: with more than one, a case passes only when every run passes, and one that
# passes some runs is reported as flaky, so a variable eval is not mistaken for a broken one. The case
# line then shows the first failing run and lists every run in run_results, each with its own artifacts.
EVAL_REPEAT="${EVAL_REPEAT:-1}"
GOLFO_MARKETPLACE_EVAL_MODEL="${GOLFO_MARKETPLACE_EVAL_MODEL:-}"
GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT="${GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT:-}"
# Machine-readable JSONL is the default so CI, tests, and real eval runs are
# reproducible and easy to parse. Use --pretty for the human-readable report.
EVAL_JSONL="${EVAL_JSONL:-1}"
GOLFO_MARKETPLACE_EVAL_PROVIDER="${GOLFO_MARKETPLACE_EVAL_PROVIDER:-auto}"
RESOLVED_EVAL_PROVIDER=""

# ── Resolve paths ──────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Functions ──────────────────────────────────────────

usage() {
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Skill Eval Runner${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo "Usage:"
    echo "  run-evals [path/to/skill]    Run evals for a specific skill"
    echo "  run-evals                    Run evals for skill in current directory"
    echo "  run-evals --all              Run evals for all skills with evals/"
    echo ""
    echo "Options:"
    echo "  --jobs N, -j N               Run N cases in parallel (default: 4)"
    echo "                               Each case runs 1 agent call (2 concurrent calls"
    echo "                               with --baseline). Lower if rate-limited."
    echo "  --model M, -m M              Agent model to use (defaults: claude-sonnet-5-5:medium"
    echo "                               for Claude, gpt-6-luna:high for Codex)"
    echo "                               Accepts aliases (haiku, sonnet, opus) or full model IDs."
    echo "                               Also configurable via GOLFO_MARKETPLACE_EVAL_MODEL env var."
    echo "  --reasoning-effort E, -e E   Reasoning effort: low, medium, high, max (default: medium"
    echo "                               for Claude, high for Codex)."
    echo "                               Also configurable via GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT."
    echo "  --provider P                 Agent provider: auto, codex, or claude (default: auto,"
    echo "                               prefers codex > claude)."
    echo "                               Also configurable via GOLFO_MARKETPLACE_EVAL_PROVIDER env var."
    echo "  --jsonl, -J                  Emit machine-readable JSONL on stdout. This is"
    echo "                               the default and can also be set with EVAL_JSONL=1."
    echo "  --pretty, -P                 Emit the human-readable colored report instead"
    echo "                               of JSONL. Equivalent to EVAL_JSONL=0."
    echo "  --baseline, -B               Also run each case without the skill for manual"
    echo "                               comparison. Not scored; doubles agent calls."
    echo "                               Equivalent to EVAL_BASELINE=1."
    echo "  --repeat N, -r N             Run every case N times (default: 1). A case passes"
    echo "                               only when every run passes; mixed runs are reported"
    echo "                               as flaky. Equivalent to EVAL_REPEAT=N."
    echo ""
}

check_dependencies() {
    local missing=0

    resolve_eval_provider

    if ! command -v "$RESOLVED_EVAL_PROVIDER" &> /dev/null; then
        echo -e "${RED}ERROR: $RESOLVED_EVAL_PROVIDER CLI not found.${NC}"
        missing=1
    fi
    if ! command -v jq &> /dev/null; then
        echo -e "${RED}ERROR: jq not found. Install with: brew install jq${NC}"
        missing=1
    fi
    if [ "$missing" -eq 1 ]; then
        exit 1
    fi
}

resolve_eval_provider() {
    case "$GOLFO_MARKETPLACE_EVAL_PROVIDER" in
        claude|codex)
            RESOLVED_EVAL_PROVIDER="$GOLFO_MARKETPLACE_EVAL_PROVIDER"
            ;;
        auto)
            if command -v codex &> /dev/null; then
                RESOLVED_EVAL_PROVIDER="codex"
            elif command -v claude &> /dev/null; then
                RESOLVED_EVAL_PROVIDER="claude"
            else
                echo -e "${RED}ERROR: No supported provider CLI found. Install Codex or Claude Code.${NC}" >&2
                exit 1
            fi
            ;;
        *)
            echo -e "${RED}ERROR: Invalid provider '$GOLFO_MARKETPLACE_EVAL_PROVIDER'. Use auto, codex, or claude.${NC}" >&2
            exit 1
            ;;
    esac

    if [ -z "$GOLFO_MARKETPLACE_EVAL_MODEL" ]; then
        case "$RESOLVED_EVAL_PROVIDER" in
            codex) GOLFO_MARKETPLACE_EVAL_MODEL="gpt-6-luna" ;;
            *)     GOLFO_MARKETPLACE_EVAL_MODEL="claude-sonnet-5-5" ;;
        esac
    fi

    if [ -z "$GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT" ]; then
        case "$RESOLVED_EVAL_PROVIDER" in
            codex) GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT="high" ;;
            *)     GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT="medium" ;;
        esac
    fi
}

run_agent_prompt() {
    local cwd="$1"
    local input="$2"
    local output_file="$3"
    local codex_home="${4:-}"
    local stderr_file="${output_file}.stderr"
    # Drop usage left by a previous run so it is never reported for this one.
    rm -f "${output_file}.usage.json"

    case "$RESOLVED_EVAL_PROVIDER" in
        claude)
            # Restricting --tools (not only --allowedTools) and skipping user MCP
            # servers keeps unused tool schemas out of every eval prompt.
            local claude_json_file="${output_file}.json"
            local claude_status=0
            (cd "$cwd" && env -u CLAUDECODE claude -p "$input" \
                --model "$GOLFO_MARKETPLACE_EVAL_MODEL" \
                --effort "$GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT" \
                --setting-sources project \
                --tools "Read,Glob,Grep" \
                --allowedTools "Read,Glob,Grep" \
                --strict-mcp-config \
                --no-session-persistence \
                --output-format json) \
                > "$claude_json_file" 2> "$stderr_file" || claude_status=$?

            # Keep the plain response for assertions and record usage separately;
            # fall back to the raw output when it is not the expected JSON result.
            if jq -e 'type == "object" and has("result")' "$claude_json_file" > /dev/null 2>&1; then
                jq -r '.result // ""' "$claude_json_file" > "$output_file"
                jq -c '{
                    cost_usd: (.total_cost_usd // null),
                    num_turns: (.num_turns // null),
                    input_tokens: (.usage.input_tokens // null),
                    cache_creation_input_tokens: (.usage.cache_creation_input_tokens // null),
                    cache_read_input_tokens: (.usage.cache_read_input_tokens // null),
                    output_tokens: (.usage.output_tokens // null)
                }' "$claude_json_file" > "${output_file}.usage.json"
            else
                cp "$claude_json_file" "$output_file"
            fi
            rm -f "$claude_json_file"
            return "$claude_status"
            ;;
        codex)
            local event_stream_file
            event_stream_file=$(mktemp)

            local reasoning_effort_flag=()
            if [ -n "${GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT:-}" ]; then
                reasoning_effort_flag=(-c "model_reasoning_effort=\"$GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT\"")
            fi

            CODEX_HOME="$codex_home" codex exec \
                --model "$GOLFO_MARKETPLACE_EVAL_MODEL" \
                "${reasoning_effort_flag[@]}" \
                --cd "$cwd" \
                --skip-git-repo-check \
                --ephemeral \
                --ignore-rules \
                --sandbox read-only \
                --color never \
                --json \
                "$input" \
                < /dev/null \
                > "$event_stream_file" 2> "$stderr_file"

            jq -Rsr '
                split("\n")
                | map(
                    fromjson?
                    | select(.type == "item.completed" and .item.type == "agent_message")
                    | .item.text
                )
                | last // ""
            ' "$event_stream_file" > "$output_file"

            if [ ! -s "$output_file" ] || ! grep -q '[^[:space:]]' "$output_file"; then
                cp "$event_stream_file" "$output_file"
            fi

            rm -f "$event_stream_file"
            ;;
    esac
}

create_codex_eval_home() {
    local target_home="$1"
    local source_config="${CODEX_HOME:-$HOME/.codex}/config.toml"
    local source_home
    source_home="$(cd "$(dirname "$source_config")" 2>/dev/null && pwd || dirname "$source_config")"

    mkdir -p "$target_home/skills" "$target_home/plugins" "$target_home/marketplaces"

    if [ -f "$source_config" ]; then
        awk '
            BEGIN { keep = 0 }
            /^model[[:space:]]*=/ || /^model_provider[[:space:]]*=/ || /^model_reasoning_effort[[:space:]]*=/ {
                print
                next
            }
            /^\[model_providers\./ {
                keep = 1
                print
                next
            }
            /^\[/ {
                keep = 0
            }
            keep {
                print
            }
        ' "$source_config" > "$target_home/config.toml"
    fi

    local auth_file
    for auth_file in \
        "$source_home"/auth.json \
        "$source_home"/credentials.json \
        "$source_home"/.codex-auth.json \
        "$source_home"/state_*.sqlite \
        "$source_home"/state_*.sqlite-shm \
        "$source_home"/state_*.sqlite-wal; do
        if [ -e "$auth_file" ]; then
            cp -p "$auth_file" "$target_home/" 2>/dev/null || true
        fi
    done
}

preflight_eval_provider() {
    local check_cwd
    local output_file
    check_cwd=$(mktemp -d)
    output_file=$(mktemp)

    local codex_home=""
    if [ "$RESOLVED_EVAL_PROVIDER" = "codex" ]; then
        codex_home=$(mktemp -d)
        create_codex_eval_home "$codex_home"
    fi

    if ! run_agent_prompt "$check_cwd" "Reply exactly: eval-provider-ready" "$output_file" "$codex_home"; then
        echo -e "${RED}ERROR: $RESOLVED_EVAL_PROVIDER provider preflight failed.${NC}" >&2
        echo "The selected provider did not complete a minimal eval prompt." >&2
        echo "Check authentication and provider configuration before running evals." >&2
        if [ "$RESOLVED_EVAL_PROVIDER" = "codex" ]; then
            echo "For Codex, verify $HOME/.codex/config.toml, auth, and proxy settings." >&2
        fi
        echo "No fallback provider was used; set --provider claude or GOLFO_MARKETPLACE_EVAL_PROVIDER=claude explicitly if that is intended." >&2
        echo "Preflight output:" >&2
        sed -n '1,40p' "$output_file" >&2
        rm -rf "$check_cwd" "$output_file" "$codex_home"
        return 1
    fi

    if ! grep -qi 'eval-provider-ready' "$output_file"; then
        echo -e "${RED}ERROR: $RESOLVED_EVAL_PROVIDER provider preflight returned an unexpected response.${NC}" >&2
        echo "No eval cases were run. Check provider configuration and model availability." >&2
        echo "Preflight output:" >&2
        sed -n '1,40p' "$output_file" >&2
        rm -rf "$check_cwd" "$output_file" "$codex_home"
        return 1
    fi

    rm -rf "$check_cwd" "$output_file" "$codex_home"
    return 0
}

find_eval_config() {
    local skill_path="$1"

    # Check evals/eval-config.json
    if [ -f "$skill_path/evals/eval-config.json" ]; then
        echo "$skill_path/evals/eval-config.json"
        return 0
    fi

    echo ""
    return 1
}

validate_eval_config() {
    local config_file="$1"

    jq -e '
        (.schema_version // 1) as $schema_version
        | ($schema_version == 1 or $schema_version == 2)
        and (.skill | type == "string" and length > 0)
        and (.test_cases | type == "array" and length > 0)
        and ([.test_cases[].id] | all(type == "string" and length > 0) and length == (unique | length))
        and all(.test_cases[]; .input | type == "string")
        and all(.test_cases[];
            (.assertions | type == "array")
            and all(.assertions[]; .type | type == "string")
        )
    ' "$config_file" >/dev/null 2>&1
}

# One line per paragraph, list item or heading: consecutive lines join, and a blank line, a new list item
# or a heading starts a new one. Stricter than normalize_response_continuations, which also carries text
# past blank lines (useful to catch mixed steps, wrong for a positive match).
join_wrapped_lines() {
    awk '
        function flush() { if (buffer != "") print buffer; buffer = "" }
        /^[[:space:]]*$/ { flush(); next }
        /^[[:space:]]*#/ { flush(); print; next }
        /^[[:space:]]*([0-9]+[.)]|[-*])[[:space:]]/ { flush(); buffer = $0; next }
        { buffer = (buffer == "") ? $0 : buffer " " $0 }
        END { flush() }
    ' <<< "$1"
}

# Positive assertions match the raw response or the same text with each paragraph and list item on one
# line: a model often wraps a sentence, and a line-based grep would miss a phrase split across lines.
response_matches() {
    local response="$1"
    shift
    printf '%s\n' "$response" | grep -qi "$@" && return 0
    join_wrapped_lines "$response" | grep -qi "$@"
}

validate_assertion_contains() {
    local response="$1"
    local value="$2"
    response_matches "$response" -- "$value"
}

validate_assertion_contains_any() {
    local response="$1"
    local config_file="$2"
    local case_idx="$3"
    local assert_idx="$4"

    local values_count
    values_count=$(jq ".test_cases[$case_idx].assertions[$assert_idx].values | length" "$config_file")

    for k in $(seq 0 $((values_count - 1))); do
        local v
        v=$(jq -r ".test_cases[$case_idx].assertions[$assert_idx].values[$k]" "$config_file")
        if response_matches "$response" -- "$v"; then
            return 0
        fi
    done
    return 1
}

normalize_response_continuations() {
    local response="$1"

    awk '
        function flush_step() {
            if (logical_step != "") {
                print logical_step
                logical_step = ""
            }
        }
        function indentation(line) {
            match(line, /^[[:space:]]*/)
            return RLENGTH
        }
        function starts_list_item(line) {
            return line ~ /^[[:space:]]*([0-9]+[.)]|[-*])[[:space:]]/
        }
        BEGIN {
            step_indent = -1
        }
        /^[[:space:]]*$/ {
            print ""
            after_blank = 1
            next
        }
        {
            line_indent = indentation($0)
            if (starts_list_item($0) && (step_indent < 0 || line_indent <= step_indent)) {
                flush_step()
                logical_step = $0
                step_indent = line_indent
            } else if (after_blank && step_indent >= 0 && line_indent <= step_indent) {
                # As in Markdown, an unindented paragraph after a blank line ends the
                # list, so commentary after the steps never joins the last step.
                flush_step()
                logical_step = $0
                step_indent = -1
            } else if (logical_step == "") {
                logical_step = $0
            } else {
                logical_step = logical_step " " $0
            }
            after_blank = 0
        }
        END {
            flush_step()
        }
    ' <<< "$response"
}

validate_assertion_not_contains_any() {
    local response="$1"
    local config_file="$2"
    local case_idx="$3"
    local assert_idx="$4"

    local values_count normalized_response
    values_count=$(jq ".test_cases[$case_idx].assertions[$assert_idx].values | length" "$config_file")
    normalized_response=$(normalize_response_continuations "$response")

    for k in $(seq 0 $((values_count - 1))); do
        local v
        v=$(jq -r ".test_cases[$case_idx].assertions[$assert_idx].values[$k]" "$config_file")
        if printf '%s\n' "$response" | grep -qi -- "$v" ||
            printf '%s\n' "$normalized_response" | grep -qi -- "$v"; then
            return 1
        fi
    done
    return 0
}

validate_assertion_regex() {
    local response="$1"
    local pattern="$2"
    response_matches "$response" -E -- "$pattern"
}

# Records a failed assertion as one JSON object into the failures file (if set),
# so the JSONL report can list exactly which assertions broke and why.
record_failure() {
    local failures_file="$1"
    local type="$2"
    local desc="$3"
    local detail="$4"
    [ -n "$failures_file" ] || return 0
    jq -nc --arg type "$type" --arg description "$desc" --arg detail "$detail" \
        '{type: $type, description: $description, detail: $detail}' >> "$failures_file"
}

read_failures_json() {
    local failures_file="$1"

    if [ -f "$failures_file" ] && [ -s "$failures_file" ]; then
        jq -cs '.' "$failures_file" 2>/dev/null || printf '[]'
        return 0
    fi

    printf '[]'
}

write_case_result_jsonl() {
    local result_dir="$1"
    local case_idx="$2"
    local skill_name="$3"
    local id="$4"
    local description="$5"
    local input="$6"
    local total="$7"
    local status_str="$8"
    local elapsed="$9"
    local failed_json="${10}"
    local workspace="${11}"

    local baseline_artifact=""
    [ "$EVAL_BASELINE" = "1" ] && baseline_artifact="$workspace/without-skill/$id.txt"
    # Provider usage (Claude only) for the with-skill call; null when unavailable.
    local usage_json="null"
    local usage_file="$workspace/with-skill/$id.txt.usage.json"
    if [ -s "$usage_file" ] && jq -e . "$usage_file" > /dev/null 2>&1; then
        usage_json=$(jq -c . "$usage_file")
    fi

    jq -nc \
        --arg skill "$skill_name" \
        --arg provider "$RESOLVED_EVAL_PROVIDER" \
        --arg id "$id" \
        --arg description "$description" \
        --arg input "$input" \
        --argjson index "$((case_idx + 1))" \
        --argjson total "$total" \
        --arg status "$status_str" \
        --argjson duration "$elapsed" \
        --argjson failed "$failed_json" \
        --arg with_skill "$workspace/with-skill/$id.txt" \
        --arg baseline "$baseline_artifact" \
        --argjson usage "$usage_json" \
        '{event: "case", provider: $provider, skill: $skill, id: $id, description: $description, input: $input, index: $index, total: $total, status: $status, duration_seconds: $duration, failed_assertions: $failed, usage: $usage, artifacts: {with_skill: $with_skill, baseline: (if $baseline == "" then null else $baseline end)}}' \
        > "$result_dir/$case_idx.jsonl"
}

# Every repetition writes the same response files, so with --repeat each run's responses are copied to
# run-N/ and that run's results point to the copies: a failing run keeps its own evidence.
preserve_run_artifacts() {
    local workspace="$1"
    local run="$2"
    local run_result_dir="$3"
    local total="$4"
    local i id variant result_file
    for i in $(seq 0 $((total - 1))); do
        result_file="$run_result_dir/$i.jsonl"
        [ -f "$result_file" ] || continue
        id=$(jq -r '.id' "$result_file")
        for variant in with-skill without-skill; do
            [ -f "$workspace/$variant/$id.txt" ] || continue
            mkdir -p "$workspace/run-$run/$variant"
            cp "$workspace/$variant/$id.txt"* "$workspace/run-$run/$variant/"
        done
        jq -c --arg from "$workspace/" --arg to "$workspace/run-$run/" \
            '.artifacts |= with_entries(if (.value | type) == "string" and (.value | startswith($from)) then .value = $to + (.value | ltrimstr($from)) else . end)' \
            "$result_file" > "$result_file.tmp" && mv "$result_file.tmp" "$result_file"
    done
}

record_case_setup_failure() {
    local result_dir="$1"
    local case_idx="$2"
    local skill_name="$3"
    local id="$4"
    local description="$5"
    local input="$6"
    local total="$7"
    local workspace="$8"
    local detail="$9"
    local elapsed="${10}"
    local output_dir="${11}"
    local failed_json

    failed_json=$(jq -nc --arg detail "$detail" \
        '[{type: "infrastructure", description: "Eval runner failed before executing case", detail: $detail}]')
    printf '1\n' > "$result_dir/$case_idx.txt"
    write_case_result_jsonl "$result_dir" "$case_idx" "$skill_name" "$id" "$description" "$input" "$total" "failed" "$elapsed" "$failed_json" "$workspace"

    # Write a minimal case-output artifact so the pretty print phase doesn't abort.
    if [ -n "$output_dir" ]; then
        {
            echo "─────────────────────────────────────────"
            echo -e "${BOLD}CASE [$((case_idx + 1))/$total]: $id${NC}"
            echo "DESC: $description"
            echo "INPUT: $input"
            echo ""
            echo -e "  ${RED}⚠ INFRASTRUCTURE FAILURE: $detail${NC}"
            echo ""
            echo -e "  ${RED}RESULT: ❌ FAILED${NC}"
            echo ""
        } > "$output_dir/$case_idx.txt" 2>/dev/null || true
    fi
}

run_assertions() {
    local response="$1"
    local config_file="$2"
    local case_idx="$3"
    local failures_file="$4"
    local case_passed=true

    local assertion_count
    assertion_count=$(jq ".test_cases[$case_idx].assertions | length" "$config_file")

    for j in $(seq 0 $((assertion_count - 1))); do
        local type desc
        type=$(jq -r ".test_cases[$case_idx].assertions[$j].type" "$config_file")
        desc=$(jq -r ".test_cases[$case_idx].assertions[$j].description // \"\"" "$config_file")

        case "$type" in
            contains)
                local value
                value=$(jq -r ".test_cases[$case_idx].assertions[$j].value" "$config_file")
                if validate_assertion_contains "$response" "$value"; then
                    echo -e "  ${GREEN}✅ $desc${NC}"
                else
                    echo -e "  ${RED}❌ $desc${NC} (expected: '$value')"
                    case_passed=false
                    record_failure "$failures_file" "$type" "$desc" "expected to contain: $value"
                fi
                ;;

            contains_any)
                if validate_assertion_contains_any "$response" "$config_file" "$case_idx" "$j"; then
                    echo -e "  ${GREEN}✅ $desc${NC}"
                else
                    echo -e "  ${RED}❌ $desc${NC}"
                    case_passed=false
                    local values
                    values=$(jq -c ".test_cases[$case_idx].assertions[$j].values" "$config_file")
                    record_failure "$failures_file" "$type" "$desc" "expected to contain any of: $values"
                fi
                ;;

            not_contains_any)
                if validate_assertion_not_contains_any "$response" "$config_file" "$case_idx" "$j"; then
                    echo -e "  ${GREEN}✅ $desc${NC}"
                else
                    echo -e "  ${RED}❌ $desc${NC} (found unwanted content)"
                    case_passed=false
                    local values
                    values=$(jq -c ".test_cases[$case_idx].assertions[$j].values" "$config_file")
                    record_failure "$failures_file" "$type" "$desc" "found unwanted content from: $values"
                fi
                ;;

            regex)
                local pattern
                pattern=$(jq -r ".test_cases[$case_idx].assertions[$j].pattern" "$config_file")
                if validate_assertion_regex "$response" "$pattern"; then
                    echo -e "  ${GREEN}✅ $desc${NC}"
                else
                    echo -e "  ${RED}❌ $desc${NC} (pattern: '$pattern')"
                    case_passed=false
                    record_failure "$failures_file" "$type" "$desc" "did not match pattern: $pattern"
                fi
                ;;

            *)
                echo -e "  ${YELLOW}⚠ Unknown assertion type: $type${NC}"
                ;;
        esac
    done

    if [ "$case_passed" = true ]; then
        return 0
    fi
    return 1
}

# Runs a single eval case in isolation; all output buffered to a file.
# Called as a background job by run_skill_evals.
# output_dir and result_dir are passed explicitly so stale jobs from interrupted
# runs hold their old paths — if those dirs were cleaned up, the guard below exits early.
run_single_case() {
    local i="$1"
    local config_file="$2"
    local workspace="$3"
    local total="$4"
    local output_dir="$5"
    local result_dir="$6"
    local skill_cwd="$7"
    local baseline_cwd="$8"
    local skill_codex_home="$9"
    local baseline_codex_home="${10}"
    local canonical_skill_path="${11}"

    local id input description skill_name
    id=$(jq -r ".test_cases[$i].id" "$config_file")
    input=$(jq -r ".test_cases[$i].input" "$config_file")
    description=$(jq -r ".test_cases[$i].description" "$config_file")
    skill_name=$(jq -r '.skill' "$config_file")
    local start_time=$SECONDS

    # Per-case file collecting failed-assertion JSON objects (one per line).
    local failures_file="$result_dir/$i.failures"
    mkdir -p "$result_dir" || {
        echo "ERROR: Case setup failed: could not create result directory: $result_dir" >&2
        return 1
    }
    touch "$failures_file" || {
        local setup_elapsed=$(( SECONDS - start_time ))
        echo "ERROR: Case setup failed: could not create failures file: $failures_file" >&2
        record_case_setup_failure "$result_dir" "$i" "$skill_name" "$id" "$description" "$input" "$total" "$workspace" "could not create failures file: $failures_file" "$setup_elapsed" "$output_dir"
        echo -e "  ${RED}❌ [$((i + 1))/$total] $id${NC}  ${setup_elapsed}s (infrastructure failure)" >&2
        return 0
    }

    {
        echo "─────────────────────────────────────────"
        echo -e "${BOLD}CASE [$((i + 1))/$total]: $id${NC}"
        echo "DESC: $description"
        echo "INPUT: $input"
        echo ""

        # Fire agent calls in parallel (baseline only when enabled); responses
        # land in workspace files.
        # Contract evals must read the full skill before answering so behavior does
        # not depend on provider-specific lazy skill activation.
        local contract_input
        contract_input=$(printf '%s\n\n%s\n' \
            "This is a contract evaluation. Read and apply $canonical_skill_path/SKILL.md and every reference it directs you to for this task. Do not use external services or Bash; answer only from those bundled contracts." \
            "$input")
        run_agent_prompt "$skill_cwd" "$contract_input" "$workspace/with-skill/$id.txt" "$skill_codex_home" &
        local pid_with=$!

        local pid_base=""
        if [ "$EVAL_BASELINE" = "1" ]; then
            run_agent_prompt "$baseline_cwd" "$input" "$workspace/without-skill/$id.txt" "$baseline_codex_home" &
            pid_base=$!
        fi

        local with_status=0
        wait "$pid_with" || with_status=$?
        if [ -n "$pid_base" ]; then
            wait "$pid_base" || true
        fi

        local response_with
        response_with=$(cat "$workspace/with-skill/$id.txt" 2>/dev/null || true)

        local with_infrastructure_failure=false
        if [ "$with_status" -ne 0 ] || [ -z "${response_with//[[:space:]]/}" ]; then
            local provider_error
            provider_error=$(head -40 "$workspace/with-skill/$id.txt.stderr" 2>/dev/null || true)
            record_failure "$failures_file" "infrastructure" "with-skill provider execution failed" "${provider_error:-exit status $with_status}"
            with_infrastructure_failure=true
        fi

        # With skill
        echo -e "→ ${BLUE}[WITH SKILL]${NC}"
        echo "$response_with" | head -30
        echo ""

        if [ "$EVAL_BASELINE" = "1" ]; then
            echo -e "→ ${BLUE}[BASELINE]${NC}"
            head -30 "$workspace/without-skill/$id.txt" 2>/dev/null || true
            echo ""
        fi

        # Assertions only run when the with-skill provider completed normally.
        if [ "$with_infrastructure_failure" = true ]; then
            echo ""
            echo -e "  ${RED}RESULT: ❌ INFRASTRUCTURE FAILURE${NC}"
            echo "1" > "$result_dir/$i.txt"
        elif run_assertions "$response_with" "$config_file" "$i" "$failures_file"; then
            echo ""
            echo -e "  ${GREEN}RESULT: ✅ PASSED${NC}"
            echo "0" > "$result_dir/$i.txt"
        else
            echo ""
            echo -e "  ${RED}RESULT: ❌ FAILED${NC}"
            echo "1" > "$result_dir/$i.txt"
        fi
        echo ""
    } > "$output_dir/$i.txt" 2>&1

    # Guard: if our output file doesn't exist, this is a stale job from a previous
    # interrupted run whose dirs were already cleaned up — suppress the completion notice.
    [ -f "$output_dir/$i.txt" ] || return 0

    # Completion count = number of result files written so far (including this one)
    local done_count
    done_count=$(ls "$result_dir"/*.txt 2>/dev/null | wc -l | tr -d ' ')

    local elapsed=$(( SECONDS - start_time ))
    local duration
    if [ "$elapsed" -ge 60 ]; then
        duration="${elapsed}s ($(( elapsed / 60 ))m $(( elapsed % 60 ))s)"
    else
        duration="${elapsed}s"
    fi

    local result
    result=$(cat "$result_dir/$i.txt" 2>/dev/null || echo "1")

    # Build the per-case JSONL line (consumed in the print phase when --jsonl is set).
    local status_str="passed"
    [ "$result" -eq 0 ] || status_str="failed"
    local failed_json
    failed_json=$(read_failures_json "$failures_file")
    write_case_result_jsonl "$result_dir" "$i" "$skill_name" "$id" "$description" "$input" "$total" "$status_str" "$elapsed" "$failed_json" "$workspace"

    if [ "$result" -eq 0 ]; then
        echo -e "  ${GREEN}✅ [$done_count/$total] $id${NC}  ${duration}" >&2
    else
        echo -e "  ${RED}❌ [$done_count/$total] $id${NC}  ${duration}" >&2
    fi
}

run_skill_evals() {
    local skill_path="$1"
    local config_file
    config_file=$(find_eval_config "$skill_path")

    if [ -z "$config_file" ]; then
        echo -e "${YELLOW}⚠ No eval-config.json found in $skill_path/evals/${NC}"
        return 1
    fi

    if ! validate_eval_config "$config_file"; then
        echo -e "${RED}ERROR: Invalid eval-config.json: $config_file${NC}" >&2
        return 1
    fi

    local skill_name
    skill_name=$(jq -r '.skill' "$config_file")
    local canonical_skill_path
    canonical_skill_path=$(cd "$skill_path" && pwd)
    local total
    total=$(jq '.test_cases | length' "$config_file")

    # Persistent workspace for reviewable artifacts; ephemeral subdirs are per-invocation
    # (named by $$) so stale background jobs from interrupted runs write to their own
    # old dirs, not ours. All previous run dirs are wiped at start.
    local workspace="$REPO_ROOT/.eval-results/$skill_name"
    local output_dir="$workspace/case-output-$$"
    local result_dir="$workspace/case-results-$$"
    mkdir -p "$workspace/with-skill" "$workspace/without-skill"
    rm -rf "$workspace"/case-output-* "$workspace"/case-results-*
    mkdir -p "$output_dir" "$result_dir"

    # Shared temp dirs: with-skill has the skill symlinked for all supported
    # providers; baseline is a plain empty dir with no project-local skills.
    local skill_cwd baseline_cwd skill_codex_home baseline_codex_home
    skill_cwd=$(mktemp -d)
    baseline_cwd=$(mktemp -d)
    mkdir -p "$skill_cwd/.claude/skills"
    ln -s "$canonical_skill_path" "$skill_cwd/.claude/skills/$skill_name"
    mkdir -p "$skill_cwd/.codex/skills"
    ln -s "$canonical_skill_path" "$skill_cwd/.codex/skills/$skill_name"
    skill_codex_home=""
    baseline_codex_home=""
    if [ "$RESOLVED_EVAL_PROVIDER" = "codex" ]; then
        skill_codex_home=$(mktemp -d)
        baseline_codex_home=$(mktemp -d)
        create_codex_eval_home "$skill_codex_home"
        create_codex_eval_home "$baseline_codex_home"
        ln -s "$canonical_skill_path" "$skill_codex_home/skills/$skill_name"
    fi
    trap "rm -rf '$skill_cwd' '$baseline_cwd' '$skill_codex_home' '$baseline_codex_home'" RETURN

    local suite_start=$SECONDS

    # In JSONL mode keep stdout pure (data only): send the human header to stderr.
    local header_fd=1
    [ "$EVAL_JSONL" = "1" ] && header_fd=2
    {
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo -e "${BLUE}  Evaluations: ${BOLD}$skill_name${NC}"
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo ""
        echo -e "  Config:    $config_file"
        echo -e "  Skill:     $skill_path"
        echo -e "  Cases:     $total"
        echo -e "  Jobs:      $EVAL_JOBS (parallel)"
        echo -e "  Model:     $GOLFO_MARKETPLACE_EVAL_MODEL"
        if [ -n "${GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT:-}" ]; then
            echo -e "  Effort:    $GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT"
        fi
        echo -e "  Provider:  $RESOLVED_EVAL_PROVIDER"
        if [ "$EVAL_BASELINE" = "1" ]; then
            echo -e "  Baseline:  on"
        else
            echo -e "  Baseline:  off (use --baseline to compare)"
        fi
        echo -e "  Runs:      $EVAL_REPEAT per case"
        echo -e "  Results:   $workspace"
        echo ""
    } >&"$header_fd"

    # ── Dispatch phase: spawn cases in parallel, pool-limited; once per run with --repeat ──
    # Runs go one after another (each in its own result dir), so a case never races itself
    # for its response file; the last run's responses stay as the reviewable artifacts.
    local run
    for run in $(seq 1 "$EVAL_REPEAT"); do
        local run_output_dir="$output_dir/run-$run" run_result_dir="$result_dir/run-$run"
        mkdir -p "$run_output_dir" "$run_result_dir"
        [ "$EVAL_REPEAT" -gt 1 ] && echo -e "  ${BLUE}Run $run/$EVAL_REPEAT${NC}" >&2
        local pids=()
        for i in $(seq 0 $((total - 1))); do
            # Drain finished PIDs until pool has room
            while [ ${#pids[@]} -ge "$EVAL_JOBS" ]; do
                local running=()
                for pid in "${pids[@]}"; do
                    kill -0 "$pid" 2>/dev/null && running+=("$pid")
                done
                pids=("${running[@]}")
                [ ${#pids[@]} -ge "$EVAL_JOBS" ] && sleep 0.2
            done

            run_single_case "$i" "$config_file" "$workspace" "$total" "$run_output_dir" "$run_result_dir" "$skill_cwd" "$baseline_cwd" "$skill_codex_home" "$baseline_codex_home" "$canonical_skill_path" &
            pids+=($!)
        done

        # Wait for all remaining jobs (|| true: pass/fail handled via result files)
        wait || true
        [ "$EVAL_REPEAT" -gt 1 ] && preserve_run_artifacts "$workspace" "$run" "$run_result_dir" "$total"
    done
    local last_output_dir="$output_dir/run-$EVAL_REPEAT" last_result_dir="$result_dir/run-$EVAL_REPEAT"

    # ── Print phase: output in original order, aggregate counts ──
    if [ "$EVAL_JSONL" != "1" ]; then
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo -e "${BLUE}  Case Results: ${BOLD}$skill_name${NC}"
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo ""
    fi
    local passed=0
    local failed=0
    local flaky=0
    for i in $(seq 0 $((total - 1))); do
        # Every run whose worker died before writing its result gets an infrastructure failure, so the
        # run picked for the report below always has a case line.
        local missing_run_dir
        for run in $(seq 1 "$EVAL_REPEAT"); do
            missing_run_dir="$result_dir/run-$run"
            if [ ! -f "$missing_run_dir/$i.txt" ] || [ ! -f "$missing_run_dir/$i.jsonl" ]; then
                mkdir -p "$missing_run_dir" 2>/dev/null || true
                local missing_id missing_input missing_description missing_elapsed missing_failed_json
                missing_id=$(jq -r ".test_cases[$i].id" "$config_file")
                missing_input=$(jq -r ".test_cases[$i].input" "$config_file")
                missing_description=$(jq -r ".test_cases[$i].description" "$config_file")
                missing_elapsed=$(( SECONDS - suite_start ))
                missing_failed_json=$(jq -nc --argjson run "$run" \
                    '[{type: "infrastructure", description: "Eval runner did not write a case result", detail: "run \($run) finished before writing result files"}]')
                printf '1\n' > "$missing_run_dir/$i.txt" 2>/dev/null || true
                write_case_result_jsonl "$missing_run_dir" "$i" "$skill_name" "$missing_id" "$missing_description" "$missing_input" "$total" "failed" "$missing_elapsed" "$missing_failed_json" "$workspace" 2>/dev/null || true
            fi
        done
        # A case passes only when every run passes; mixed runs are flaky (and still count as failed).
        # The report shows the first failing run, so a flaky case keeps the evidence of its failure.
        local passes=0 run_result report_run=""
        for run in $(seq 1 "$EVAL_REPEAT"); do
            run_result=$(cat "$result_dir/run-$run/$i.txt" 2>/dev/null || echo "1")
            if [ "$run_result" -eq 0 ]; then passes=$((passes + 1)); elif [ -z "$report_run" ]; then report_run="$run"; fi
        done
        report_run="${report_run:-$EVAL_REPEAT}"
        local case_status="passed"
        if [ "$passes" -eq "$EVAL_REPEAT" ]; then
            passed=$((passed + 1))
        else
            failed=$((failed + 1))
            case_status="failed"
            if [ "$passes" -gt 0 ]; then
                case_status="flaky"
                flaky=$((flaky + 1))
            fi
        fi
        if [ "$EVAL_JSONL" = "1" ]; then
            local run_results="[]"
            if [ "$EVAL_REPEAT" -gt 1 ]; then
                run_results=$(for run in $(seq 1 "$EVAL_REPEAT"); do
                    jq -c --argjson run "$run" '{run: $run, status, failed_assertions, artifacts}' "$result_dir/run-$run/$i.jsonl" 2>/dev/null \
                        || jq -nc --argjson run "$run" '{run: $run, status: "failed", failed_assertions: [{type: "infrastructure", description: "Eval runner did not write a case result"}], artifacts: null}'
                done | jq -cs '.')
            fi
            jq -c --argjson runs "$EVAL_REPEAT" --argjson passes "$passes" --arg status "$case_status" --argjson run_results "$run_results" \
                '. + {status: $status, runs: $runs, passes: $passes} + (if $runs > 1 then {run_results: $run_results} else {} end)' \
                "$result_dir/run-$report_run/$i.jsonl" 2>/dev/null || true
        else
            cat "$output_dir/run-$report_run/$i.txt" 2>/dev/null || cat "$last_output_dir/$i.txt"
            [ "$EVAL_REPEAT" -gt 1 ] && echo -e "  Runs: $passes/$EVAL_REPEAT passed ($case_status)" && echo ""
        fi
    done

    # Summary
    local suite_elapsed=$(( SECONDS - suite_start ))
    local suite_duration
    if [ "$suite_elapsed" -ge 60 ]; then
        suite_duration="${suite_elapsed}s ($(( suite_elapsed / 60 ))m $(( suite_elapsed % 60 ))s)"
    else
        suite_duration="${suite_elapsed}s"
    fi

    if [ "$EVAL_JSONL" = "1" ]; then
        jq -nc \
            --arg skill "$skill_name" \
            --arg provider "$RESOLVED_EVAL_PROVIDER" \
            --argjson total "$total" \
            --argjson passed "$passed" \
            --argjson failed "$failed" \
            --argjson duration "$suite_elapsed" \
            --argjson runs "$EVAL_REPEAT" \
            --argjson flaky "$flaky" \
            '{event: "summary", provider: $provider, skill: $skill, total: $total, passed: $passed, failed: $failed, flaky: $flaky, runs: $runs, duration_seconds: $duration}'
    else
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo -e "${BLUE}  Summary: ${BOLD}$skill_name${NC}"
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo ""
        echo -e "  Total:   $total"
        echo -e "  Passed:  ${GREEN}$passed ✅${NC}"
        echo -e "  Failed:  ${RED}$failed ❌${NC}"
        if [ "$EVAL_REPEAT" -gt 1 ]; then
            echo -e "  Flaky:   ${YELLOW}$flaky${NC} (of the failed: passed some of the $EVAL_REPEAT runs)"
        fi
        echo -e "  Time:    $suite_duration"
        echo ""

        if [ "$failed" -gt 0 ]; then
            echo -e "  ${YELLOW}Review failed cases in: $workspace/with-skill/${NC}"
        fi
    fi

    if [ "$failed" -gt 0 ]; then
        return 1
    fi
    return 0
}

run_all_evals() {
    # In JSONL mode keep stdout pure: decorative banners go to stderr.
    local banner_fd=1
    [ "$EVAL_JSONL" = "1" ] && banner_fd=2
    {
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo -e "${BLUE}  Running ALL skill evals${NC}"
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo ""
    } >&"$banner_fd"

    local total_skills=0
    local passed_skills=0
    local failed_skills=0

    # Search in skills/ and plugins/
    for dir in "$REPO_ROOT"/skills/*/evals "$REPO_ROOT"/plugins/*/skills/*/evals; do
        [ -d "$dir" ] || continue
        [ -f "$dir/eval-config.json" ] || continue

        local skill_path
        skill_path=$(dirname "$dir")
        total_skills=$((total_skills + 1))

        if run_skill_evals "$skill_path"; then
            passed_skills=$((passed_skills + 1))
        else
            failed_skills=$((failed_skills + 1))
        fi
        [ "$EVAL_JSONL" = "1" ] || echo ""
    done

    if [ "$total_skills" -eq 0 ]; then
        echo -e "${YELLOW}No skills with evals/eval-config.json found.${NC}" >&"$banner_fd"
        return 0
    fi

    if [ "$EVAL_JSONL" = "1" ]; then
        jq -nc \
            --argjson skills "$total_skills" \
            --argjson all_passed "$passed_skills" \
            --argjson with_failures "$failed_skills" \
            '{event: "global_summary", skills_evaluated: $skills, all_passed: $all_passed, with_failures: $with_failures}'
    else
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo -e "${BLUE}  Global Summary${NC}"
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo ""
        echo -e "  Skills evaluated: $total_skills"
        echo -e "  All passed:       ${GREEN}$passed_skills ✅${NC}"
        echo -e "  With failures:    ${RED}$failed_skills ❌${NC}"
        echo ""
    fi

    if [ "$failed_skills" -gt 0 ]; then
        return 1
    fi
    return 0
}

has_eval_targets() {
    local dir
    for dir in "$REPO_ROOT"/skills/*/evals "$REPO_ROOT"/plugins/*/skills/*/evals; do
        [ -d "$dir" ] || continue
        [ -f "$dir/eval-config.json" ] || continue
        return 0
    done
    return 1
}

target_requires_provider() {
    case "${1:-}" in
        --all)
            has_eval_targets
            ;;
        "")
            if [ -f "SKILL.md" ] || [ -f "../SKILL.md" ]; then
                return 0
            fi
            echo -e "${RED}ERROR: No SKILL.md found in current directory.${NC}"
            echo "Run from a skill directory or pass the path: run-evals path/to/skill"
            exit 1
            ;;
        *)
            if [ -d "$1" ]; then
                return 0
            fi
            echo -e "${RED}ERROR: Directory not found: $1${NC}"
            exit 1
            ;;
    esac
}

# ── Main ───────────────────────────────────────────────

# Help doesn't need dependencies
case "${1:-}" in
    --help|-h)
        usage
        exit 0
        ;;
esac

# Pre-parse --jobs / -j (may appear anywhere in args)
args=()
while [ $# -gt 0 ]; do
    case "$1" in
        --jobs|-j)
            EVAL_JOBS="$2"
            shift 2
            ;;
        --model|-m)
            GOLFO_MARKETPLACE_EVAL_MODEL="$2"
            shift 2
            ;;
        --reasoning-effort|-e)
            GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT="$2"
            shift 2
            ;;
        --provider)
            GOLFO_MARKETPLACE_EVAL_PROVIDER="$2"
            shift 2
            ;;
        --jsonl|-J)
            EVAL_JSONL=1
            shift
            ;;
        --pretty|-P)
            EVAL_JSONL=0
            shift
            ;;
        --baseline|-B)
            EVAL_BASELINE=1
            shift
            ;;
        --repeat|-r)
            EVAL_REPEAT="${2:-}"
            shift 2 || shift
            ;;
        *)
            args+=("$1")
            shift
            ;;
    esac
done
set -- "${args[@]+"${args[@]}"}"

if ! [[ "$EVAL_REPEAT" =~ ^[1-9][0-9]*$ ]]; then
    echo -e "${RED}ERROR: --repeat needs a positive integer (got \"$EVAL_REPEAT\")${NC}" >&2
    exit 2
fi

if target_requires_provider "$@"; then
    check_dependencies
    preflight_eval_provider
fi

case "${1:-}" in
    --all)
        run_all_evals
        ;;
    "")
        # No args — look for skill in current directory
        if [ -f "SKILL.md" ]; then
            run_skill_evals "$(pwd)"
        elif [ -f "../SKILL.md" ]; then
            # Inside evals/ directory
            run_skill_evals "$(cd .. && pwd)"
        else
            echo -e "${RED}ERROR: No SKILL.md found in current directory.${NC}"
            echo "Run from a skill directory or pass the path: run-evals path/to/skill"
            exit 1
        fi
        ;;
    *)
        # Path to skill provided
        if [ -d "$1" ]; then
            run_skill_evals "$1"
        else
            echo -e "${RED}ERROR: Directory not found: $1${NC}"
            exit 1
        fi
        ;;
esac
