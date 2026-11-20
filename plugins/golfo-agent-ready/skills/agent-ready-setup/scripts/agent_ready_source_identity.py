"""Source identity: which content and profile sources the selection comes from, the identity the lock records for
them, and the policies that keep a sync or a reproduction of the lock on those sources.
"""

import os
import sys

import agent_ready_compatibility as compatibility
import agent_ready_content as content_source
import agent_ready_nested as nested
import agent_ready_workspaces as workspace_selection
from agent_ready_common import (
    IncompleteEvaluationError,
    ProfileError,
    StateError,
    has_linked_parent,
    read_json_file,
    sha256_of_file,
    sha256_of_text,
)
from agent_ready_desired_assets import WORKSPACE_ORIGIN_PREFIX, desired_assets, desired_blocks, nested_contents
from agent_ready_layout import (
    AGENTS_TEMPLATE_NAME,
    CLAUDE_SETTINGS_TEMPLATE_RELATIVE_PATH,
    CODEX_HOOKS_TEMPLATE_RELATIVE_PATH,
    PROFILE_CATALOG_RELATIVE_PATH,
    RENDERED_INSTRUCTION_INPUTS,
    RENDERER_RELATIVE_PATH,
    claude_view_of,
)
from agent_ready_lockfile import STATE_APPLIED, STATE_RETIRED_PRESERVED, read_lock
from agent_ready_manifest import configuration_of
from agent_ready_options import UPDATES_AUTO, UPDATES_PINNED
from agent_ready_output import write_line
from agent_ready_packs import SOURCE_AVAILABLE, is_pack_profile, source_of_profile
from agent_ready_rule_overrides import rule_override_texts


def validate_pack_destinations(project_root, assets):
    """A pack asset cannot reach outside the project through a symlink in its path."""
    for destination, entry in sorted(assets.items()):
        if not is_pack_profile(entry["profile"]):
            continue
        for path in (destination, claude_view_of(destination, entry["source"])):
            if path and has_linked_parent(project_root, path):
                raise ProfileError(
                    f"profile '{entry['profile']}' would write {path} through a symlink, "
                    "which can leave the project; nothing was written"
                )


def source_entries(catalog, resolved, digests, locked_sources):
    """Lockfile entry of each declared source; a source without selected profiles has none."""
    entries = {}
    for name, source in sorted(catalog.get("sources", {}).items()):
        if source["state"] != SOURCE_AVAILABLE:
            # Unused by this selection and not on this machine: its last record stays.
            if name in locked_sources:
                entries[name] = locked_sources[name]
            continue
        selected = sorted(profile for profile in resolved if is_pack_profile(profile) and source_of_profile(profile) == name)
        entries[name] = {
            "type": source["type"],
            "origin": source["origin"],
            "requestedRef": source["requestedRef"],
            "resolvedCommit": source["resolvedCommit"],
            "catalogDigest": source["catalogDigest"],
            "contentDigest": sha256_of_text("\n".join(f"{profile}\t{digests[profile]['digest']}" for profile in selected)),
            "profiles": selected,
        }
        if source.get("version"):
            entries[name]["version"] = source["version"]
    return entries


def version_changes(catalog, plan_source, lock):
    """Each source whose version moves from the lock, with its declared changelog, newest first."""
    if not lock:
        return []
    changes = []
    golfo_change = compatibility.version_change(content_source.CONTENT_SOURCE_NAME, (lock.get("source") or {}).get("version"),
                                                plan_source.get("version"), catalog.get("changes", []))
    if golfo_change:
        changes.append(golfo_change)
    locked_sources = lock.get("profileSources", {})
    for name, source in sorted(catalog.get("sources", {}).items()):
        if source["state"] != SOURCE_AVAILABLE:
            continue
        change = compatibility.version_change(name, (locked_sources.get(name) or {}).get("version"),
                                              source.get("version"), source.get("changes", []))
        if change:
            changes.append(change)
    return changes


def declaration_differences(declaration, locked_entry):
    """What the manifest changed in a source; it needs neither the network nor its content."""
    if not locked_entry:
        return ["not adopted yet"]
    differences = []
    if declaration.get("origin") != locked_entry.get("origin"):
        differences.append(f"origin changed to {declaration.get('origin')}")
    if declaration.get("requestedRef") != locked_entry.get("requestedRef"):
        differences.append(f"requested revision changed to {declaration.get('requestedRef')}")
    return differences


def source_differences(name, entry, lock):
    """What changed in a source since the last apply, in words.

    A digest of a selected profile counts only if the lock has that profile too, so
    selecting one more profile of the same revision is a selection change, not an update.
    """
    locked_sources = (lock or {}).get("profileSources", {})
    locked_entry = locked_sources.get(name)
    if not locked_entry:
        return ["not adopted yet"]
    differences = declaration_differences(entry, locked_entry)
    if entry.get("resolvedCommit") != locked_entry.get("resolvedCommit"):
        locked_commit = (locked_entry.get("resolvedCommit") or "none")[:12]
        differences.append(f"revision {locked_commit} -> {(entry.get('resolvedCommit') or 'none')[:12]}")
    if entry.get("catalogDigest") != locked_entry.get("catalogDigest"):
        differences.append("catalog changed")
    return differences


def changed_selected_profiles(digests, lock):
    """Selected pack profiles whose content differs from the digest in the lock."""
    locked_profiles = (lock or {}).get("profiles", {})
    return sorted(
        profile for profile, entry in digests.items()
        if is_pack_profile(profile) and profile in locked_profiles and locked_profiles[profile].get("digest") != entry["digest"]
    )


def source_report(catalog, resolved, digests, lock):
    """State of each declared source for plan and status, with its differences from the lock."""
    locked_sources = (lock or {}).get("profileSources", {})
    entries = source_entries(catalog, resolved, digests, locked_sources)
    changed_profiles = changed_selected_profiles(digests, lock)
    report = {}
    for name, source in sorted(catalog.get("sources", {}).items()):
        selected = sorted(profile for profile in resolved if is_pack_profile(profile) and source_of_profile(profile) == name)
        item = {
            "type": source["type"],
            "origin": source["origin"],
            "requestedRef": source["requestedRef"],
            "resolvedCommit": source["resolvedCommit"],
            "state": source["state"],
            "reason": source["reason"],
            "selected": selected,
            "updates": source["updates"],
            "differences": [],
            "pendingUpdate": None,
        }
        latest = source.get("latestCommit")
        if latest and source["resolvedCommit"] and latest != source["resolvedCommit"]:
            item["pendingUpdate"] = (
                f"ref {source['requestedRef']} is at {latest[:12]} and this source is pinned at "
                f"{source['resolvedCommit'][:12]}; adopt it with --update-source {name}"
            )
        if source["state"] == SOURCE_AVAILABLE:
            entry = entries[name]
            item["catalogDigest"] = entry["catalogDigest"]
            item["contentDigest"] = entry["contentDigest"]
            item["differences"] = source_differences(name, entry, lock)
            item["differences"] += [f"content of {profile} changed" for profile in changed_profiles if source_of_profile(profile) == name]
        else:
            item["differences"] = declaration_differences(source, locked_sources.get(name))
        report[name] = item
    return report


def enforce_sync_policy(project_root, skill_dir, catalog, resolved, digests, selected=None, workspace_origins=None):
    """An unattended sync only adopts what is in ``auto``.

    A pinned source that differs from the lock stops it, the content included: its mode is
    ``sources.golfo.updates``, then ``updates.mode``. Pinned content projects the revision of the lock,
    so it only differs when the composition does (a new engine with other engine files does not count);
    then a pack in ``auto`` waits too, because an apply writes the whole selection and cannot update a
    pack without updating the content.
    ``selected`` adds the profiles of the workspaces to the sources checked; the content digest is the
    one of the root selection plus ``workspace_origins``, as compute_plan records it.
    """
    lock = read_lock(project_root)
    report = source_report(catalog, selected or resolved, digests, lock)
    for name, item in report.items():
        if item["selected"] and item["differences"] and item["updates"] != UPDATES_AUTO:
            raise IncompleteEvaluationError(
                f"profile source '{name}' is pinned and differs from the lock ({'; '.join(item['differences'])}); "
                "SessionStart does not adopt it, so this repository keeps its committed assets until someone adopts the change"
            )
    marker = content_source.read_marker(skill_dir)
    # A local content directory (AGENT_READY_SETUP_CONTENT_DIR) has no revision: its digest decides.
    locked_revision = (lock or {}).get("source", {}).get("revision")
    projects_locked_revision = bool(marker and marker.get("commit")) and marker["commit"] == locked_revision
    # The content digest covers engine-owned files too (hooks, settings templates): with the revision
    # of the lock projected, a new engine is not a release of the content and the sync goes on.
    if lock and not projects_locked_revision and content_source.update_mode(configuration_of(project_root)) == UPDATES_PINNED:
        # The same texts as the plan, so a rule an override removed hashes as the apply wrote it.
        assets = desired_assets(skill_dir, catalog, resolved, shared_texts=rule_override_texts(skill_dir, catalog, resolved, project_root))
        golfo_assets = {destination: entry for destination, entry in assets.items() if not is_pack_profile(entry["profile"])}
        identity = source_identity(skill_dir, golfo_assets, merged_template_entries(skill_dir, catalog, resolved),
                                   golfo_blocks(desired_blocks(skill_dir, catalog, resolved, assets)),
                                   golfo_blocks(nested_contents(skill_dir, catalog, resolved)), workspace_origins)
        if lock.get("source", {}).get("contentDigest") != identity["contentDigest"]:
            raise IncompleteEvaluationError(
                "this repository pins its golfo content and has a release pending, and SessionStart cannot update a pack alone; "
                "the repository keeps its committed assets until someone adopts both"
            )


def asset_owner(entry):
    """The source an asset of a plan or a lock comes from: a pack, or the content (golfo)."""
    profile = entry.get("profile") or ""
    return source_of_profile(profile) if is_pack_profile(profile) else content_source.CONTENT_SOURCE_NAME


def is_engine_asset(entry):
    """An asset the installed engine projects (hooks and what connects them): never pinned, so never compared."""
    return asset_owner(entry) == content_source.CONTENT_SOURCE_NAME and content_source.is_engine_owned(entry.get("source") or "")


def locked_desired_sha256(locked_entry):
    """The content a source published for an asset of the lock: applied, or wanted when it ended in conflict."""
    if locked_entry.get("state") == STATE_APPLIED:
        return locked_entry.get("sha256")
    return locked_entry.get("desiredSha256")


def lock_differences(plan, lock):
    """Why a plan does not reproduce the lock, one line per source, and how many engine files differ.

    Content is compared byte for byte: the selection, the revision of the content and of each
    pack, the digest of each pack and the sha256 of every asset and merged template. The files
    of the engine follow the installed one, so they are only counted.
    """
    if not lock:
        return ["there is no lockfile to apply from; run an apply first"], 0
    differences = []
    if plan["profiles"] != lock.get("profileOrder"):
        differences.append(f"selection: the manifest resolves to {', '.join(plan['profiles'])} and the lock has "
                           f"{', '.join(lock.get('profileOrder') or []) or 'none'}")
    # The workspaces are part of the selection: the same lines status shows for them.
    differences += [f"selection: {line}" for line in workspace_selection.differences(
        plan.get("workspaces", []), lock.get("workspaces") or {})]
    locked_revision = (lock.get("source") or {}).get("revision")
    if locked_revision and plan["source"].get("revision") != locked_revision:
        differences.append(f"{content_source.CONTENT_SOURCE_NAME}: revision {(plan['source'].get('revision') or 'none')[:12]} "
                           f"instead of {locked_revision[:12]}")
    locked_sources = lock.get("profileSources", {})
    for name in sorted(set(locked_sources) | set(plan["profileSources"])):
        locked_entry, current = locked_sources.get(name), plan["profileSources"].get(name)
        if not current:
            differences.append(f"{name}: in the lock, but this repository no longer selects it")
        elif not locked_entry:
            differences.append(f"{name}: not in the lock")
        elif current.get("resolvedCommit") != locked_entry.get("resolvedCommit"):
            differences.append(f"{name}: revision {(current.get('resolvedCommit') or 'none')[:12]} instead of "
                               f"{(locked_entry.get('resolvedCommit') or 'none')[:12]}")
        elif current.get("contentDigest") != locked_entry.get("contentDigest"):
            differences.append(f"{name}: its content does not match the digest of the lock")
    locked_assets = lock.get("assets", {})
    desired = {entry["destination"]: entry for entry in plan["entries"] if entry["sha256"]}
    engine_changes = 0
    for destination, entry in sorted(desired.items()):
        locked_entry = locked_assets.get(destination)
        if is_engine_asset(entry):
            engine_changes += bool(locked_entry) and locked_entry.get("sha256") != entry["sha256"]
        elif not locked_entry:
            differences.append(f"{asset_owner(entry)}: {destination} is not in the lock")
        elif locked_desired_sha256(locked_entry) != entry["sha256"]:
            differences.append(f"{asset_owner(entry)}: {destination} does not match the sha256 of the lock")
    for destination, locked_entry in sorted(locked_assets.items()):
        # A retired asset the project kept (retired-preserved) is no longer published by any source.
        if destination not in desired and locked_entry.get("state") != STATE_RETIRED_PRESERVED and not is_engine_asset(locked_entry):
            differences.append(f"{asset_owner(locked_entry)}: {destination} is in the lock but not in this resolution")
    locked_blocks = lock.get("blocks") or {}
    desired_blocks_by_key = {(entry["destination"], entry["id"]): entry for entry in plan.get("blocks", []) if entry["sha256"]}
    for (destination, block_id), entry in sorted(desired_blocks_by_key.items()):
        locked_entry = (locked_blocks.get(destination) or {}).get(block_id)
        if not locked_entry:
            differences.append(f"{entry['profile']}: the block {block_id} of {destination} is not in the lock")
        elif locked_desired_sha256(locked_entry) != entry["sha256"]:
            differences.append(f"{entry['profile']}: the block {block_id} of {destination} does not match the sha256 of the lock")
    for destination, file_blocks in sorted(locked_blocks.items()):
        for block_id, locked_entry in sorted(file_blocks.items()):
            if (destination, block_id) not in desired_blocks_by_key:
                differences.append(f"{locked_entry.get('profile')}: the block {block_id} of {destination} is in the lock "
                                   "but not in this resolution")
    for destination, entry in sorted(plan["merged"].items()):
        if content_source.is_engine_owned(entry["template"]):
            continue
        locked_entry = lock.get("merged", {}).get(destination)
        if not locked_entry or locked_entry.get("templateSha256") != entry["templateSha256"]:
            differences.append(f"{content_source.CONTENT_SOURCE_NAME}: the template of {destination} does not match the lock")
        elif locked_entry.get("inputsSha256") != entry.get("inputsSha256"):
            differences.append(f"{content_source.CONTENT_SOURCE_NAME}: what {destination} is rendered with (the centralization "
                               "and proxy texts) does not match the lock")
    return differences, engine_changes


def enforce_lock_reproduction(plan, lock):
    """--from-lock projects exactly the lock or nothing: stop before writing and name what differs."""
    differences, engine_changes = lock_differences(plan, lock)
    if differences:
        raise ProfileError("--from-lock cannot reproduce the lock, so nothing was changed:\n  - " + "\n  - ".join(differences))
    if engine_changes:
        write_line(f"--from-lock: {engine_changes} file(s) of the engine (hooks and their settings) follow the installed "
                   "plugin and differ from the lock; the content is the lock's.", sys.stderr)


def keep_locked_entries_of_unselected_sources(plan, lock):
    """SessionStart does not adopt a pinned source without selected profiles either: its drift stays visible."""
    locked_sources = (lock or {}).get("profileSources", {})
    for name, item in plan["sourceReport"].items():
        if item["selected"] or not item["differences"] or item["updates"] == UPDATES_AUTO:
            continue
        if name in locked_sources:
            plan["profileSources"][name] = locked_sources[name]
        else:
            plan["profileSources"].pop(name, None)
SOURCE_KIND_GIT = "git"
SOURCE_KIND_LOCAL = "local"


def content_version(skill_dir):
    """Version of the content: the ``version`` its catalog declares (a content pack must declare one)."""
    try:
        declared = read_json_file(os.path.join(skill_dir, PROFILE_CATALOG_RELATIVE_PATH), "profile catalog").get("version")
    except StateError:
        declared = None
    return declared if isinstance(declared, str) and compatibility.semver_key(declared) else None


def golfo_blocks(blocks):
    """The managed blocks, or nested targets, the content publishes: packs have their own digest."""
    return {key: item for key, item in blocks.items() if not is_pack_profile(item["profile"])}


def source_identity(skill_dir, assets, merged_templates, blocks, nested_targets, workspace_origins=None):
    """Identity of the resolved source; contentDigest is the immutable part.

    The content records the Git origin, ref and revision it came from, so the next apply of a
    pinned repository fetches exactly that content again. A nested target counts by its id, not
    by the folders it goes to in this repository, and what a profile only workspaces select projects by
    the files it comes from (workspace_profile_origins).
    """
    digest_lines = [f"{destination}\t{entry['sha256']}" for destination, entry in sorted(assets.items())]
    digest_lines += [f"{destination}\t{entry['templateSha256']}" for destination, entry in sorted(merged_templates.items())]
    digest_lines += [f"{destination}\t{block_id}\t{sha256_of_text(item['content'])}"
                     for (destination, block_id), item in sorted(blocks.items())]
    digest_lines += [f"{nested.NESTED_PREFIX}{identifier}\t{sha256_of_text(item['content'])}"
                     for identifier, item in sorted(nested_targets.items())]
    digest_lines += [f"{WORKSPACE_ORIGIN_PREFIX}{origin}\t{sha256}" for origin, sha256 in sorted((workspace_origins or {}).items())]
    digest_lines += [
        f"{relative_path}\t{sha256_of_file(os.path.join(skill_dir, relative_path))}"
        for relative_path in RENDERED_INSTRUCTION_INPUTS
        if os.path.isfile(os.path.join(skill_dir, relative_path))
    ]
    marker = content_source.read_marker(skill_dir) or {}
    identity = {
        "name": content_source.CONTENT_SOURCE_NAME,
        "version": content_version(skill_dir),
        # The development override (a local directory) has no revision: its files identify it.
        "kind": SOURCE_KIND_GIT if marker.get("commit") else SOURCE_KIND_LOCAL,
        "revision": marker.get("commit"),
        "contentDigest": sha256_of_text("\n".join(digest_lines)),
    }
    for key, field in (("origin", "origin"), ("requestedRef", "requestedRef")):
        if marker.get(field):
            identity[key] = marker[field]
    return identity


def agents_template_path(skill_dir, catalog):
    """The one AGENTS.md template: its managed block is the same for every repository.

    Each stack adds its section as a block, and a profile can publish only the skeleton of a new
    AGENTS.md (software-development: Stack, Commands, Architecture) in place of the neutral one.
    """
    return os.path.join(skill_dir, catalog.get("baseAssets", "assets/common"), AGENTS_TEMPLATE_NAME)


def merged_template_entries(skill_dir, catalog, resolved):
    """Files merged with project content instead of copied verbatim."""
    agents_template = agents_template_path(skill_dir, catalog)
    settings_template = os.path.join(skill_dir, *CLAUDE_SETTINGS_TEMPLATE_RELATIVE_PATH.split("/"))
    codex_template = os.path.join(skill_dir, CODEX_HOOKS_TEMPLATE_RELATIVE_PATH)
    entries = {}
    for destination, template, kind in (
        ("AGENTS.md", agents_template, "managed-block"),
        (".claude/settings.json", settings_template, "merged-json"),
        (".codex/hooks.json", codex_template, "merged-json"),
    ):
        if os.path.isfile(template):
            entries[destination] = {
                "kind": kind,
                "template": os.path.relpath(template, skill_dir).replace(os.sep, "/"),
                "templateSha256": sha256_of_file(template),
            }
    if "AGENTS.md" in entries:
        entries["AGENTS.md"]["inputsSha256"] = rendered_inputs_digest(skill_dir)
    return entries


def rendered_inputs_digest(skill_dir):
    """Content the managed block of AGENTS.md is rendered with besides its template; the renderer is the engine's."""
    lines = [f"{relative_path}\t{sha256_of_file(os.path.join(skill_dir, relative_path))}"
             for relative_path in RENDERED_INSTRUCTION_INPUTS
             if not content_source.is_engine_owned(relative_path) and relative_path != RENDERER_RELATIVE_PATH
             and os.path.isfile(os.path.join(skill_dir, relative_path))]
    return sha256_of_text("\n".join(lines))
