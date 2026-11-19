#!/usr/bin/env bash
# Recomputes the file-count marker of an open PR after a push and patches only that marker.
#
# Usage:
#   refresh-file-count.sh [<pr-number-or-url>]   # default: the PR of the current branch
#
# The PR body must already carry the marker written by the template (on the
# `## 📝 Descripción` heading, or the legacy right-aligned line above it, which is moved
# onto the heading). Every other byte of the body is preserved and the title is never touched.
#
# Prints one status line on stdout:
#   UPDATED: <old> -> <new> <url>     the body was patched and verified
#   UNCHANGED: <count> <url>          the marker already had the right count
#   SKIPPED: <reason>                 nothing to refresh (no PR, PR not open, no marker)
# Exits 1 with a message on stderr when the range cannot be fetched or the edit fails.
set -euo pipefail
# Byte semantics: the markers contain emoji outside the BMP, which grep and awk mishandle under
# some UTF-8 locales (Git Bash on Windows). Exact byte matching of UTF-8 literals is enough here.
export LC_ALL=C

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly COUNT_SCRIPT="${SCRIPT_DIR}/count-reviewable-files.sh"
readonly MARKER_LABEL='📄 Archivos de código modificados: '
readonly DESCRIPTION_HEADING='## 📝 Descripción'
readonly OPEN_STATE='OPEN'
readonly PR_FIELDS='number,url,state,baseRefName,headRefName,isCrossRepository'
readonly PR_FIELDS_TSV='[.number, .url, .state, .baseRefName, .headRefName, .isCrossRepository] | @tsv'
readonly PR_URL_REGEX='^https://([^/]+)/([^/]+)/([^/]+)/pull/[0-9]+$'
# Private ref namespace for the fetched range, deleted on exit, so the refresh never moves the
# user's remote-tracking refs.
readonly FETCH_REF_PREFIX='refs/pr-file-count'
# History added per round when a shallow clone has no merge base yet, before giving up and
# unshallowing the whole repository.
readonly DEEPEN_STEPS=(50 500 5000)

fail() {
  printf 'refresh-file-count: %s\n' "$1" >&2
  exit 1
}

pr_target=("$@")
if ! pr_fields="$(gh pr view ${pr_target[@]+"${pr_target[@]}"} --json "$PR_FIELDS" --jq "$PR_FIELDS_TSV" 2>/dev/null)"; then
  printf 'SKIPPED: no pull request for %s\n' "${1:-the current branch}"
  exit 0
fi
IFS=$'\t' read -r pr_number pr_url pr_state base_ref_name head_ref_name is_cross_repository <<<"$pr_fields"

if [[ "$pr_state" != "$OPEN_STATE" ]]; then
  printf 'SKIPPED: PR %s is %s\n' "$pr_url" "$pr_state"
  exit 0
fi

work_dir="$(mktemp -d)"
base_ref="${FETCH_REF_PREFIX}/${pr_number}/base"
head_ref="${FETCH_REF_PREFIX}/${pr_number}/head"
cleanup() {
  rm -rf "$work_dir"
  git update-ref -d "$base_ref" 2>/dev/null || true
  git update-ref -d "$head_ref" 2>/dev/null || true
}
trap cleanup EXIT

gh pr view "$pr_url" --json body --jq .body > "${work_dir}/current.md" ||
  fail "gh pr view ${pr_url} --json body failed while reading the PR body"
if ! grep -qF "$MARKER_LABEL" "${work_dir}/current.md"; then
  printf 'SKIPPED: PR %s has no file-count marker\n' "$pr_url"
  exit 0
fi

# The base repository owns the base branch and refs/pull/<n>/head, even when `origin` is the
# contributor's fork, so fetch from the remote that points to it (or from its URL).
[[ "$pr_url" =~ $PR_URL_REGEX ]] || fail "cannot read the base repository from PR URL ${pr_url}"
base_host="${BASH_REMATCH[1]}"
base_repository="${BASH_REMATCH[2]}/${BASH_REMATCH[3]}"
# tr instead of ${var,,}: macOS ships bash 3.2.
base_repository_lower="$(printf '%s' "$base_repository" | tr '[:upper:]' '[:lower:]')"
fetch_source=""
while read -r remote_name remote_url _; do
  remote_url="${remote_url%.git}"
  remote_url="$(printf '%s' "${remote_url%/}" | tr '[:upper:]' '[:lower:]')"
  if [[ "$remote_url" == *[:/]"$base_repository_lower" ]]; then
    fetch_source="$remote_name"
    break
  fi
done < <(git remote -v | awk '$3 == "(fetch)"')
[[ -n "$fetch_source" ]] || fetch_source="https://${base_host}/${base_repository}.git"

# A same-repository branch ref is updated by the push itself; refs/pull/<n>/head can lag
# behind it for a few seconds, so it is used only for PRs opened from a fork.
if [[ "$is_cross_repository" == "true" ]]; then
  head_source_ref="refs/pull/${pr_number}/head"
else
  head_source_ref="refs/heads/${head_ref_name}"
fi
refspecs=("+refs/heads/${base_ref_name}:${base_ref}" "+${head_source_ref}:${head_ref}")
git fetch --quiet --no-tags "$fetch_source" "${refspecs[@]}" ||
  fail "git fetch ${fetch_source} ${base_ref_name} ${head_source_ref} failed for PR ${pr_url}"

# A depth-1 clone (fix-in-ephemeral-clone) has no merge base for base...head: deepen it step
# by step, and unshallow as the last resort.
if [[ "$(git rev-parse --is-shallow-repository)" == "true" ]]; then
  for deepen_step in "${DEEPEN_STEPS[@]}"; do
    git merge-base "$base_ref" "$head_ref" >/dev/null 2>&1 && break
    git fetch --quiet --no-tags --deepen="$deepen_step" "$fetch_source" "${refspecs[@]}" ||
      fail "git fetch --deepen=${deepen_step} ${fetch_source} failed for PR ${pr_url}"
  done
  if ! git merge-base "$base_ref" "$head_ref" >/dev/null 2>&1; then
    git fetch --quiet --no-tags --unshallow "$fetch_source" "${refspecs[@]}" ||
      fail "git fetch --unshallow ${fetch_source} failed for PR ${pr_url}"
  fi
fi
git merge-base "$base_ref" "$head_ref" >/dev/null 2>&1 ||
  fail "no merge base between ${base_ref_name} and ${head_source_ref} for PR ${pr_url}"

new_count="$(bash "$COUNT_SCRIPT" "${base_ref}...${head_ref}")" ||
  fail "count-reviewable-files.sh failed for ${base_ref_name}...${head_source_ref} (PR ${pr_url})"

old_count="$(grep -oE "${MARKER_LABEL}[0-9]+" "${work_dir}/current.md" | head -n 1 | grep -oE '[0-9]+$' || true)"
has_heading=0
grep -qE "^${DESCRIPTION_HEADING}( |$|"$'\r'")" "${work_dir}/current.md" && has_heading=1

awk -v count="$new_count" -v label="$MARKER_LABEL" -v heading="$DESCRIPTION_HEADING" -v has_heading="$has_heading" '
  BEGIN { legacy_prefix = "<div align=\"right\"><sup>" label }
  {
    carriage_return = sub(/\r$/, "") ? "\r" : ""
    line = $0
    if (skip_blank_line && line == "") { skip_blank_line = 0; next }
    skip_blank_line = 0
    is_legacy_line = index(line, legacy_prefix) == 1 && line ~ /[0-9]+<\/sup><\/div>$/
    if (is_legacy_line && has_heading == 1) { skip_blank_line = 1; next }
    if (is_legacy_line) { print legacy_prefix count "</sup></div>" carriage_return; next }
    if (!heading_done && (line == heading || index(line, heading " ") == 1)) {
      print heading " <sup>" label count "</sup>" carriage_return
      heading_done = 1
      next
    }
    print line carriage_return
  }
' "${work_dir}/current.md" > "${work_dir}/updated.md"

if cmp -s "${work_dir}/current.md" "${work_dir}/updated.md"; then
  printf 'UNCHANGED: %s %s\n' "$new_count" "$pr_url"
  exit 0
fi

gh pr edit "$pr_url" --body-file "${work_dir}/updated.md" >/dev/null ||
  fail "gh pr edit ${pr_url} --body-file failed while refreshing the file count to ${new_count}"

published_body="$(gh pr view "$pr_url" --json body --jq .body)" ||
  fail "gh pr view ${pr_url} failed while verifying the refreshed file count"
grep -qF "${MARKER_LABEL}${new_count}</sup>" <<<"$published_body" ||
  fail "PR ${pr_url} does not show '${MARKER_LABEL}${new_count}' after gh pr edit"

printf 'UPDATED: %s -> %s %s\n' "${old_count:-?}" "$new_count" "$pr_url"
