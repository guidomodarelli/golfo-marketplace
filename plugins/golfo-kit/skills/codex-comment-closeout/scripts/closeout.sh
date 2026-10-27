#!/usr/bin/env bash
# Closes one Codex comment with the template of codex-comment-closeout/SKILL.md: reaction, reply with
# the variant's template, check of the published body, and resolution of the inline thread.
#
# Usage:
#   closeout.sh --repo OWNER/REPO --pr N --comment ID --kind inline|general|review
#               --variant resolved|no-change|failed [--sha SHA] [--summary TEXT] [--reason TEXT]
#               [--review-node-id NODE_ID]
#
#   --variant resolved   needs --sha (full commit sha) and --summary; waits until that commit is in the
#                        PR head before publishing, so the link never points to a commit GitHub hides.
#   --variant no-change  takes --reason (one line); reacts 👎 and resolves an inline thread.
#   --variant failed     no reaction and no resolution.
#   --kind review        a review body: needs --review-node-id; the reply quotes the review body.
#
# Environment: CLOSEOUT_WAIT_ATTEMPTS (default 12) and CLOSEOUT_WAIT_SECONDS (default 5) bound the wait
# for the commit. Exit code: 0 closed, 1 GitHub or verification failure, 2 bad usage.
set -euo pipefail

readonly EXIT_FAILURE=1
readonly EXIT_USAGE=2
readonly SHORT_SHA_LENGTH=7
readonly FOOTER_RESOLVED='<sub>🤖 Fix automático en respuesta a este comentario de Codex</sub>'
readonly FOOTER_REVIEW='<sub>🤖 Fix automático en respuesta a esta review de Codex</sub>'
readonly FOOTER_OTHER='<sub>🤖 Auto-fix de Codex</sub>'
wait_attempts="${CLOSEOUT_WAIT_ATTEMPTS:-12}"
wait_seconds="${CLOSEOUT_WAIT_SECONDS:-5}"

repo="" pr="" comment="" kind="" variant="" sha="" summary="" reason="" review_node_id=""

fail() { printf 'closeout: %s\n' "$1" >&2; exit "${2:-$EXIT_FAILURE}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) repo="${2:-}"; shift 2 ;;
    --pr) pr="${2:-}"; shift 2 ;;
    --comment) comment="${2:-}"; shift 2 ;;
    --kind) kind="${2:-}"; shift 2 ;;
    --variant) variant="${2:-}"; shift 2 ;;
    --sha) sha="${2:-}"; shift 2 ;;
    --summary) summary="${2:-}"; shift 2 ;;
    --reason) reason="${2:-}"; shift 2 ;;
    --review-node-id) review_node_id="${2:-}"; shift 2 ;;
    *) fail "unexpected argument $1" "$EXIT_USAGE" ;;
  esac
done

[ -n "$repo" ] && [ -n "$pr" ] && [ -n "$comment" ] || fail "--repo, --pr and --comment are required" "$EXIT_USAGE"
case "$kind" in inline|general|review) ;; *) fail "--kind must be inline, general or review" "$EXIT_USAGE" ;; esac
case "$variant" in resolved|no-change|failed) ;; *) fail "--variant must be resolved, no-change or failed" "$EXIT_USAGE" ;; esac
if [ "$variant" = "resolved" ]; then
  [ -n "$sha" ] && [ -n "$summary" ] || fail "--variant resolved needs --sha and --summary" "$EXIT_USAGE"
fi
if [ "$kind" = "review" ] && [ -z "$review_node_id" ]; then fail "--kind review needs --review-node-id" "$EXIT_USAGE"; fi

# The commit must be in the PR head (identical to it or behind it) before the reply links it.
wait_for_commit_in_head() {
  local attempt head status
  for attempt in $(seq 1 "$wait_attempts"); do
    head=$(gh pr view "$pr" --repo "$repo" --json headRefOid -q .headRefOid 2>/dev/null || true)
    if [ -n "$head" ]; then
      status=$(gh api "repos/$repo/compare/$sha...$head" --jq .status 2>/dev/null || true)
      case "$status" in identical|ahead) return 0 ;; esac
    fi
    [ "$attempt" -lt "$wait_attempts" ] && sleep "$wait_seconds"
  done
  fail "commit ${sha:0:$SHORT_SHA_LENGTH} is not in the head of PR #$pr after $wait_attempts attempts (repo $repo)"
}

build_body() {
  local short_sha commit_url footer quote=""
  case "$variant" in
    resolved)
      short_sha="${sha:0:$SHORT_SHA_LENGTH}"
      commit_url="https://github.com/$repo/commit/$sha"
      footer="$FOOTER_RESOLVED"
      if [ "$kind" = "review" ]; then
        quote=$(gh api "repos/$repo/pulls/$pr/reviews/$comment" --jq .body | sed 's/^/> /')
        printf '%s\n\n✅ **Resuelto** en [`%s`](%s) (en respuesta a esta review).\n\n**Qué cambió:** %s\n\n%s' "$quote" "$short_sha" "$commit_url" "$summary" "$FOOTER_REVIEW"
        return
      fi
      printf '✅ **Resuelto** en [`%s`](%s).\n\n**Qué cambió:** %s\n\n%s' "$short_sha" "$commit_url" "$summary" "$footer"
      ;;
    no-change)
      printf 'ℹ️ **Sin cambios.** Revisé la sugerencia pero no requería cambios de código.\n\n'
      if [ -n "$reason" ]; then printf '**Motivo:** %s\n\n' "$reason"; fi
      printf '%s' "$FOOTER_OTHER"
      ;;
    failed)
      printf '⚠️ **No pude aplicar el fix** (falla del Action, no de la sugerencia).\n\n%s' "$FOOTER_OTHER"
      ;;
  esac
}

expected_header() {
  case "$variant" in
    resolved) printf '✅ **Resuelto** en [`%s`]' "${sha:0:$SHORT_SHA_LENGTH}" ;;
    no-change) printf 'ℹ️ **Sin cambios.**' ;;
    failed) printf '⚠️ **No pude aplicar el fix**' ;;
  esac
}

react() {
  local content
  case "$variant" in resolved) content="+1" ;; no-change) content="-1" ;; failed) return 0 ;; esac
  case "$kind" in
    inline) gh api -X POST "repos/$repo/pulls/comments/$comment/reactions" -f content="$content" >/dev/null ;;
    general) gh api -X POST "repos/$repo/issues/comments/$comment/reactions" -f content="$content" >/dev/null ;;
    review)
      local graphql_content="THUMBS_UP"
      [ "$content" = "-1" ] && graphql_content="THUMBS_DOWN"
      gh api graphql -f query='mutation($id:ID!,$content:ReactionContent!){addReaction(input:{subjectId:$id,content:$content}){reaction{content}}}' -F id="$review_node_id" -F content="$graphql_content" >/dev/null
      ;;
  esac
}

publish_reply() {
  local body="$1"
  case "$kind" in
    inline) gh api -X POST "repos/$repo/pulls/$pr/comments/$comment/replies" -f body="$body" --jq .id ;;
    general|review) gh api -X POST "repos/$repo/issues/$pr/comments" -f body="$body" --jq .id ;;
  esac
}

# Re-reads the published reply; if the header or footer did not survive, it is edited, never re-posted.
verify_reply() {
  local reply_id="$1" body="$2" endpoint published header
  case "$kind" in inline) endpoint="repos/$repo/pulls/comments/$reply_id" ;; *) endpoint="repos/$repo/issues/comments/$reply_id" ;; esac
  published=$(gh api "$endpoint" --jq .body)
  header=$(expected_header)
  if [[ "$published" != *"$header"* ]] || [[ "$published" != *"<sub>🤖 "* ]]; then
    gh api -X PATCH "$endpoint" -f body="$body" >/dev/null
    published=$(gh api "$endpoint" --jq .body)
    [[ "$published" == *"$header"* ]] || fail "reply $reply_id on comment $comment does not hold the template after editing it"
  fi
}

resolve_thread() {
  [ "$kind" = "inline" ] && [ "$variant" != "failed" ] || { printf 'false'; return 0; }
  local owner="${repo%%/*}" name="${repo#*/}" thread_id
  thread_id=$(gh api graphql -f query='query($owner:String!,$repo:String!,$pr:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$pr){reviewThreads(first:100){nodes{id comments(first:100){nodes{databaseId}}}}}}}' -F owner="$owner" -F repo="$name" -F pr="$pr" --jq "[.data.repository.pullRequest.reviewThreads.nodes[] | select(any(.comments.nodes[]; .databaseId == $comment)) | .id] | first // empty")
  [ -n "$thread_id" ] || fail "no review thread holds comment $comment in PR #$pr (repo $repo)"
  gh api graphql -f query='mutation($threadId:ID!){resolveReviewThread(input:{threadId:$threadId}){thread{isResolved}}}' -F threadId="$thread_id" --jq .data.resolveReviewThread.thread.isResolved
}

[ "$variant" = "resolved" ] && wait_for_commit_in_head
body=$(build_body)
react
reply_id=$(publish_reply "$body")
[ -n "$reply_id" ] || fail "GitHub did not return the reply id for comment $comment in PR #$pr"
verify_reply "$reply_id" "$body"
resolved=$(resolve_thread)
printf 'closeout: comment %s %s reply=%s resolved=%s\n' "$comment" "$variant" "$reply_id" "$resolved"
