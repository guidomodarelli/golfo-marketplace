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
readonly REMOTE_NAME="${PR_FILE_COUNT_REMOTE:-origin}"
readonly MARKER_LABEL='📄 Archivos de código modificados: '
readonly DESCRIPTION_HEADING='## 📝 Descripción'
readonly OPEN_STATE='OPEN'

fail() {
  printf 'refresh-file-count: %s\n' "$1" >&2
  exit 1
}

readonly PR_FIELDS='number,url,state,baseRefName,headRefName,isCrossRepository'
readonly PR_FIELDS_TSV='[.number, .url, .state, .baseRefName, .headRefName, .isCrossRepository] | @tsv'

pr_target=("$@")
if ! pr_fields="$(gh pr view ${pr_target[@]+"${pr_target[@]}"} --json "$PR_FIELDS" --jq "$PR_FIELDS_TSV" 2>/dev/null)"; then
  printf 'SKIPPED: no pull request for %s
' "${1:-the current branch}"
  exit 0
fi
IFS=$'	' read -r pr_number pr_url pr_state base_ref_name head_ref_name is_cross_repository <<<"$pr_fields"

if [[ "$pr_state" != "$OPEN_STATE" ]]; then
  printf 'SKIPPED: PR %s is %s\n' "$pr_url" "$pr_state"
  exit 0
fi

work_dir="$(mktemp -d)"
pull_head_ref="refs/remotes/${REMOTE_NAME}/pr/${pr_number}"
cleanup() {
  rm -rf "$work_dir"
  git update-ref -d "$pull_head_ref" 2>/dev/null || true
}
trap cleanup EXIT

gh pr view "$pr_url" --json body --jq .body > "${work_dir}/current.md" ||
  fail "gh pr view ${pr_url} --json body failed while reading the PR body"
if ! grep -qF "$MARKER_LABEL" "${work_dir}/current.md"; then
  printf 'SKIPPED: PR %s has no file-count marker\n' "$pr_url"
  exit 0
fi

# A same-repository branch ref is updated by the push itself; refs/pull/<n>/head can lag
# behind it for a few seconds, so it is used only for PRs opened from a fork.
if [[ "$is_cross_repository" == "true" ]]; then
  head_ref="$pull_head_ref"
  head_refspec="+refs/pull/${pr_number}/head:${pull_head_ref}"
else
  head_ref="refs/remotes/${REMOTE_NAME}/${head_ref_name}"
  head_refspec="+refs/heads/${head_ref_name}:${head_ref}"
fi
base_ref="refs/remotes/${REMOTE_NAME}/${base_ref_name}"
git fetch --quiet "$REMOTE_NAME" "+refs/heads/${base_ref_name}:${base_ref}" "$head_refspec" ||
  fail "git fetch ${REMOTE_NAME} ${base_ref_name} ${head_ref_name} failed for PR ${pr_url}"

new_count="$(bash "$COUNT_SCRIPT" "${base_ref}...${head_ref}")" ||
  fail "count-reviewable-files.sh failed for ${base_ref}...${head_ref} (PR ${pr_url})"

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
