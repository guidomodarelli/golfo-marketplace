# The content every suite projects: the official content pack at the tag of content-pack.ref
# (prepare-content-pack.sh). The engine carries no content, and no test downloads it: they read a
# shared checkout through AGENT_READY_SETUP_CONTENT_DIR. A test that changes the content works on its
# own copy (copy_content_pack), never on the shared one.
#
# Load it from setup() with `load content-pack` and call use_content_pack once HOME and the caches
# of the test are set.

use_content_pack() {
  content_pack="$(bash "$BATS_TEST_DIRNAME/prepare-content-pack.sh")" || return 1
  export AGENT_READY_SETUP_CONTENT_DIR="$content_pack"
}

# A copy of the content pack in the test directory, which the test can change: the next run of the
# engine projects it as it is.
copy_content_pack() {
  content_dir="$test_root/content"
  rm -rf "$content_dir"
  mkdir -p "$content_dir"
  cp -R "$content_pack/." "$content_dir/"
  rm -rf "$content_dir/.git"
  content_dir="$(cd "$content_dir" && (pwd -W 2>/dev/null || pwd))"
  export AGENT_READY_SETUP_CONTENT_DIR="$content_dir"
}

# The content pack as a Git repository reached at its real URL through url.insteadOf, for the tests
# of sources.golfo itself: refs, pins and updates. Its copy can change, committed, like a release.
publish_content_pack_repository() {
  content_repository="$test_root/content-repository"
  rm -rf "$content_repository"
  mkdir -p "$content_repository"
  cp -R "$content_pack/." "$content_repository/"
  rm -rf "$content_repository/.git"
  git -C "$content_repository" init -q
  git -C "$content_repository" add -A
  git -C "$content_repository" commit -qm "content pack"
  content_revision="$(git -C "$content_repository" rev-parse HEAD)"
  git config --global "url.file:///$(cd "$content_repository" && (pwd -W 2>/dev/null || pwd) | sed 's#^/##').insteadOf" \
    "https://github.com/guidomodarelli/golfo-agent-profiles"
  unset AGENT_READY_SETUP_CONTENT_DIR
}
