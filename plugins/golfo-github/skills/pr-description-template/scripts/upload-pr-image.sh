#!/usr/bin/env bash
# Uploads PR screenshots to the repository's orphan `pr-assets` branch through the GitHub API
# and prints the URL of each file, one per line, for the <img> tags of the PR body.
#
# Usage:
#   upload-pr-image.sh <owner/repo> <folder> <image-path> [<image-path>...]
#
# <folder> groups the images of one PR inside the branch; use the PR head branch name so the
# links exist before the PR does. Each file keeps its basename, so name captures by what they
# show (`before-dark.png`, `after-dark.png`). Uploading a name that already exists replaces it.
#
# The local checkout is never touched: no branch switch, no stash, no working-tree writes. Every
# commit message carries `[skip ci]` so branch-wide push workflows do not run on the asset branch.
# The branch also carries deploy opt-outs (`vercel.json`, `netlify.toml`) so hosting integrations
# that deploy every branch skip it. Images are served with the repository's own visibility
# (`blob/...?raw=true`), so a private repository keeps them private.
set -euo pipefail

readonly ASSET_BRANCH="pr-assets"
readonly SKIP_CI_MARKER="[skip ci]"
readonly ASSET_README="Imágenes de pull requests subidas por pr-description-template. No mergear esta rama."
# Files every commit of the asset branch carries, as "path|content" pairs: deploy integrations read
# their configuration from the commit they would deploy, so these keep them from building the branch.
readonly ASSET_BRANCH_FILES=(
  "README.md|$ASSET_README"
  'vercel.json|{ "git": { "deploymentEnabled": false } }'
  $'netlify.toml|[build]\n  ignore = "exit 0"\n'
)

if [[ $# -lt 3 ]]; then
  echo "upload-pr-image: usage: upload-pr-image.sh <owner/repo> <folder> <image-path>..." >&2
  exit 2
fi

repository="$1"
folder="${2//[^A-Za-z0-9._\/-]/-}"
shift 2

for image_path in "$@"; do
  if [[ ! -f "$image_path" ]]; then
    echo "upload-pr-image: image not found: $image_path" >&2
    exit 1
  fi
done

payload_file="$(mktemp)"
trap 'rm -f "$payload_file"' EXIT

# Uploads one text file to the asset branch when it is missing there.
put_branch_file_if_missing() {
  local file_path="$1" file_content="$2"
  if gh api "repos/$repository/contents/$file_path?ref=$ASSET_BRANCH" --silent 2>/dev/null; then
    return
  fi
  jq -n --arg message "Add $file_path $SKIP_CI_MARKER" --arg branch "$ASSET_BRANCH" --arg content "$file_content" \
    '{message: $message, branch: $branch, content: ($content | @base64)}' |
    gh api -X PUT "repos/$repository/contents/$file_path" --input - --silent
}

# Creates the orphan asset branch with its fixed files in a single first commit, or adds the ones an
# older asset branch is missing.
ensure_asset_branch() {
  local entry
  if gh api "repos/$repository/branches/$ASSET_BRANCH" --silent 2>/dev/null; then
    for entry in "${ASSET_BRANCH_FILES[@]}"; do
      put_branch_file_if_missing "${entry%%|*}" "${entry#*|}"
    done
    return
  fi
  local tree_entries="[]" blob_sha tree_sha commit_sha
  for entry in "${ASSET_BRANCH_FILES[@]}"; do
    blob_sha=$(jq -n --arg content "${entry#*|}" '{content: $content, encoding: "utf-8"}' |
      gh api "repos/$repository/git/blobs" --input - --jq .sha)
    tree_entries=$(jq -c --arg path "${entry%%|*}" --arg sha "$blob_sha" \
      '. + [{path: $path, mode: "100644", type: "blob", sha: $sha}]' <<< "$tree_entries")
  done
  tree_sha=$(jq -n --argjson tree "$tree_entries" '{tree: $tree}' |
    gh api "repos/$repository/git/trees" --input - --jq .sha)
  commit_sha=$(jq -n --arg tree "$tree_sha" --arg message "Create PR asset branch $SKIP_CI_MARKER" \
    '{message: $message, tree: $tree, parents: []}' |
    gh api "repos/$repository/git/commits" --input - --jq .sha)
  jq -n --arg sha "$commit_sha" --arg ref "refs/heads/$ASSET_BRANCH" '{ref: $ref, sha: $sha}' |
    gh api "repos/$repository/git/refs" --input - --silent
}

ensure_asset_branch

for image_path in "$@"; do
  file_name="$(basename "$image_path")"
  asset_path="$folder/$file_name"
  # On a 404 gh still prints the error body to stdout, so keep the output only when the call succeeds.
  existing_sha=$(gh api "repos/$repository/contents/$asset_path?ref=$ASSET_BRANCH" --jq .sha 2>/dev/null) || existing_sha=""
  {
    printf '{"message":"Add %s %s","branch":"%s","content":"' "$asset_path" "$SKIP_CI_MARKER" "$ASSET_BRANCH"
    base64 < "$image_path" | tr -d '\n'
    if [[ -n "$existing_sha" ]]; then
      printf '","sha":"%s"}' "$existing_sha"
    else
      printf '"}'
    fi
  } > "$payload_file"
  gh api -X PUT "repos/$repository/contents/$asset_path" --input "$payload_file" --silent
  printf 'https://github.com/%s/blob/%s/%s?raw=true\n' "$repository" "$ASSET_BRANCH" "$asset_path"
done
