#!/bin/sh
# Relinks the .claude hard-link views that git detached by recreating their .agents asset.
#
# Views are hard links only where the platform cannot create symlinks without privileges
# (Windows without Developer Mode). Git runs this script after every index write (a git
# post-index-change hook registered by agent-ready), and Claude Code runs it on every
# prompt, which also covers `git apply` without --index: that rewrites files without
# firing any git hook. Only the views agent-ready created (listed in the manifest) are
# relinked. It prints nothing on success because Claude adds hook output to the prompt.
CLAUDE_DIR=".claude"
SHARED_DIR=".agents"
MANIFEST_NAME=".agent-ready-hard-link-views"

project_root=$(git rev-parse --show-toplevel 2>/dev/null) || project_root=$(pwd)
cd "$project_root" || exit 0
manifest="$CLAUDE_DIR/$MANIFEST_NAME"
[ -f "$manifest" ] && [ ! -L "$manifest" ] || exit 0

while IFS= read -r relative; do
  case "$relative" in
    "" | /* | ../* | */../* | */..) continue ;;
  esac
  source_path="$SHARED_DIR/$relative"
  view_path="$CLAUDE_DIR/$relative"
  [ -f "$source_path" ] && [ ! -L "$source_path" ] || continue
  [ ! -L "$view_path" ] || continue
  [ "$view_path" -ef "$source_path" ] && continue
  if ! ln -f "$source_path" "$view_path" 2>/dev/null; then
    printf '[agent-ready] Aviso: no se pudo reenlazar %s; corré el sync de agent-ready.\n' "$view_path" >&2
  fi
done < "$manifest"
exit 0
