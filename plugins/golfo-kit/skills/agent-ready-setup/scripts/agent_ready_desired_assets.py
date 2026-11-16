"""Desired assets: what the selected profiles publish and where each asset lands, the managed blocks they bring,
the assets and rules of each workspace, the digest of each profile and the stack directory composed from them.
"""

import json
import os
import shutil
import tempfile

import agent_ready_blocks as managed_blocks
import agent_ready_nested as nested
import agent_ready_workspaces as workspace_selection
from agent_ready_common import (
    ProfileError,
    is_link,
    sha256_of_file,
    sha256_of_text,
    skill_cache_directory,
    text_bytes,
    walk_content_files,
    write_text_atomically,
)
from agent_ready_detection import STACK_PROFILE_KIND
from agent_ready_layout import (
    AGENTS_SKELETON_NAME,
    AGENTS_TEMPLATE_NAME,
    CLAUDE_SETTINGS_TEMPLATE_NAME,
    MANIFEST_RELATIVE_PATH,
)
from agent_ready_manifest import configuration_of
from agent_ready_options import (
    CODEX_PROVIDER,
    NESTED_CODEX_INDEX_KEY,
    NESTED_ENABLED_KEY,
    NESTED_TARGETS_KEY,
    PROVIDERS_KEY,
)
from agent_ready_packs import is_pack_profile, source_of_profile
from agent_ready_profiles import BASE_PROFILE_NAME, is_overridden, primary_stack, profile_asset_root, resolved_overrides

# Catalog fields that do not change what a profile projects, so they stay out of its digest.
PROFILE_DIGEST_EXCLUDED_FIELDS = ("detect",)


def destinations_for_template(relative_path, is_stack_root):
    """Managed destinations that the Bash projection writes for one template file.

    Mirrors project_asset_tree in bootstrap-asset-projection.sh and project_assets in
    sync-marketplace.sh. Merged files (settings.json) and the AGENTS.md
    template are handled separately and return no verbatim destination.
    """
    if relative_path in (AGENTS_TEMPLATE_NAME, AGENTS_SKELETON_NAME, CLAUDE_SETTINGS_TEMPLATE_NAME):
        return []
    if managed_blocks.destination_of(relative_path) is not None or relative_path.startswith(nested.NESTED_PREFIX):
        # A block goes inside a file shared with the project (desired_blocks) or the AGENTS.md of a
        # folder (desired_nested_blocks), never as a whole file.
        return []
    if relative_path.startswith("github/"):
        return [".github/" + relative_path[len("github/"):]]
    destinations = [".agents/" + relative_path]
    if relative_path == "mcp.json" and is_stack_root:
        destinations.append(".codex/.mcp.json")
    top_directory = relative_path.split("/", 1)[0]
    if relative_path.endswith(".md") and "/" in relative_path:
        if top_directory in ("agents", "commands") or (
            top_directory == "skills" and relative_path.count("/") == 1
        ):
            skill_name = os.path.basename(relative_path)[: -len(".md")]
            destinations.append(f".agents/skills/{skill_name}/SKILL.md")
    return destinations


def template_origin(skill_dir, catalog, profile_name, absolute_path):
    """Where a template comes from, without any path of this machine."""
    if is_pack_profile(profile_name):
        source_name = source_of_profile(profile_name)
        pack_relative = os.path.relpath(absolute_path, catalog["sources"][source_name]["root"]).replace(os.sep, "/")
        return f"{source_name}:{pack_relative}"
    return os.path.relpath(absolute_path, skill_dir).replace(os.sep, "/")


def shared_overrides(skill_dir, catalog, resolved, workspace_profiles=()):
    """resolved_overrides of what goes to the repository once: the root selection and the shared assets of
    the profiles only workspaces select. A rule such a profile overrides stays in its workspace, so
    workspace_rule_files validates it per workspace and two workspaces can replace the same rule."""
    return resolved_overrides(
        skill_dir, catalog, list(resolved) + list(workspace_profiles),
        lambda name, path: name in workspace_profiles and path.startswith(workspace_selection.RULES_DIRECTORY + "/"))


def is_workspace_shared_asset(relative_path):
    """True for an asset of a profile only workspaces select that goes to .agents/ once for the repository:
    everything but its rules (scoped to each workspace), its blocks, its nested targets and the templates
    of the root files (AGENTS.md and settings come from the root selection)."""
    return not relative_path.startswith(workspace_selection.RULES_DIRECTORY + "/") and \
        managed_blocks.destination_of(relative_path) is None and not relative_path.startswith(nested.NESTED_PREFIX) and \
        relative_path not in (AGENTS_TEMPLATE_NAME, AGENTS_SKELETON_NAME, CLAUDE_SETTINGS_TEMPLATE_NAME)
WORKSPACE_ASSETS_CACHE = "workspace-assets"


def rule_workspaces_of(workspace_rules, workspace_paths):
    """{rule path: [workspace]} of the rules those workspaces have (workspace_rule_files), for
    agent_ready_workspaces.scoped_references."""
    rule_workspaces = {}
    for entry in workspace_rules.values():
        if entry["workspace"] in workspace_paths:
            rule_workspaces.setdefault(entry["rulePath"], []).append(entry["workspace"])
    return rule_workspaces


def workspace_shared_texts(skill_dir, catalog, workspaces, workspace_profiles, workspace_rules):
    """{(profile, relative path): (text path, sha256)} of the shared assets whose text names a rule of a workspace.

    A skill, subagent or command of a profile only workspaces select goes to .agents/ once, but the rules
    it names went to the workspaces that select it: its references move to the rule of each of them
    (agent_ready_workspaces.scoped_references). The text is kept in the per-user cache by its sha256, so
    the plan and the projection read the same bytes. A template without such a reference is not listed.
    """
    texts = {}
    for name in workspace_profiles:
        asset_root = profile_asset_root(skill_dir, catalog, name)
        if not asset_root:
            continue
        rule_workspaces = rule_workspaces_of(
            workspace_rules, {workspace["path"] for workspace in workspaces if name in workspace["own"]})
        if not rule_workspaces:
            continue
        for relative_path, absolute_path in walk_content_files(asset_root):
            if not relative_path.endswith(".md") or not is_workspace_shared_asset(relative_path):
                continue
            with open(absolute_path, encoding="utf-8", newline="") as template_file:
                text = template_file.read()
            scoped = workspace_selection.scoped_references(text, rule_workspaces)
            if scoped == text:
                continue
            sha256 = sha256_of_text(scoped)
            text_path = skill_cache_directory(WORKSPACE_ASSETS_CACHE, f"{sha256}.md")
            if not os.path.isfile(text_path):
                write_text_atomically(text_path, scoped)
            texts[(name, relative_path)] = (text_path, sha256)
    return texts


def desired_assets(skill_dir, catalog, resolved, workspace_rules=None, workspace_profiles=(), shared_texts=None):
    """Map every managed destination to its template, owning profile and hash.

    Two templates cannot share a destination, including the skill adapters generated
    for Codex and paths that differ only by case, which collide on Windows and macOS.
    ``workspace_rules`` (workspace_rule_files) adds the rules of the workspaces, each with the
    workspace it belongs to, and ``workspace_profiles`` the skills, subagents and commands of the
    profiles only workspaces select, once for the repository (is_workspace_shared_asset), with the text
    ``shared_texts`` (workspace_shared_texts) gives the ones that name a rule of a workspace.
    """
    shared_texts = shared_texts or {}
    # Bash projects every profile tree as the stack tree, so only the base
    # assets skip the Codex MCP bridge.
    sources = [(BASE_PROFILE_NAME, os.path.join(skill_dir, catalog.get("baseAssets", "assets/common")), False)]
    for name in list(resolved) + list(workspace_profiles):
        root = profile_asset_root(skill_dir, catalog, name)
        if root:
            sources.append((name, root, True))

    assets = {}
    destinations_by_folded_name = {}
    overridden = shared_overrides(skill_dir, catalog, resolved, workspace_profiles)
    for profile_name, root, is_stack_root in sources:
        for relative_path, absolute_path in walk_content_files(root):
            if profile_name in workspace_profiles and not is_workspace_shared_asset(relative_path):
                continue
            if is_overridden(overridden, profile_name, relative_path):
                continue
            source_path, sha256 = shared_texts.get((profile_name, relative_path)) or (absolute_path, None)
            for destination in destinations_for_template(relative_path, is_stack_root):
                previous = destinations_by_folded_name.setdefault(destination.casefold(), destination)
                if previous in assets and assets[previous]["sourcePath"] != source_path:
                    raise ProfileError(
                        f"profiles '{assets[previous]['profile']}' and '{profile_name}' both write {destination}; "
                        "nothing was written. Rename one of the assets"
                    )
                assets[destination] = {
                    "profile": profile_name,
                    "source": template_origin(skill_dir, catalog, profile_name, absolute_path),
                    "sourcePath": source_path,
                    "sha256": sha256 or sha256_of_file(absolute_path),
                }
    for tree_path, entry in sorted((workspace_rules or {}).items()):
        destination = ".agents/" + tree_path
        previous = destinations_by_folded_name.setdefault(destination.casefold(), destination)
        if previous in assets:
            raise ProfileError(f"workspace {entry['workspace']}: {destination} is also written by profile "
                               f"'{assets[previous]['profile']}'; nothing was written")
        assets[destination] = {key: entry[key] for key in ("profile", "source", "sourcePath", "sha256", "workspace")}
    reject_destinations_inside_files(assets, destinations_by_folded_name)
    return assets
WORKSPACE_RULES_CACHE = "workspace-rules"
# Prefix of the lines of the content digest for the rules the profiles of the content add to workspaces.
WORKSPACE_ORIGIN_PREFIX = "workspace:"


def workspace_rule_files(skill_dir, catalog, workspaces):
    """{tree path: entry} of the rules the profiles of each workspace add, scoped to its folder.

    Each rule of a profile a workspace adds goes to rules/workspaces/<path>/, with paths: limited to
    the workspace (agent_ready_workspaces.scoped_rule_text). Its text is kept in the per-user cache by
    its sha256, so the plan, the projection and the reviews read the same bytes. Two profiles of one
    workspace that publish the same rule fail, as in the root selection; overrides of the workspace
    selection are honored.
    """
    files = {}
    for workspace in workspaces:
        overridden = resolved_overrides(skill_dir, catalog, workspace["resolved"])
        for target in overridden:
            replaced_by = {by for by in overridden[target].values() if by in workspace["own"]}
            if target not in workspace["own"] and replaced_by:
                # The root projects that asset for the whole repository: the workspace would load both.
                raise ProfileError(f"workspace {workspace['path']}: profile '{sorted(replaced_by)[0]}' overrides an asset of "
                                   f"'{target}', which the root selection projects for the whole repository; a workspace "
                                   "can only override the profiles it adds")
        owners = {}
        for name in workspace["own"]:
            asset_root = profile_asset_root(skill_dir, catalog, name)
            if not asset_root:
                continue
            for relative_path, absolute_path in walk_content_files(asset_root):
                if not relative_path.startswith(workspace_selection.RULES_DIRECTORY + "/") or \
                        is_overridden(overridden, name, relative_path):
                    continue
                rule_path = relative_path[len(workspace_selection.RULES_DIRECTORY) + 1:]
                if rule_path in owners:
                    raise ProfileError(f"workspace {workspace['path']}: profiles '{owners[rule_path]}' and '{name}' "
                                       f"both publish {relative_path}; nothing was written")
                owners[rule_path] = name
                with open(absolute_path, encoding="utf-8", newline="") as rule_file:
                    text = workspace_selection.scoped_rule_text(rule_file.read(), workspace["path"],
                                                               f"{name}:{relative_path}")
                sha256 = sha256_of_text(text)
                cache_path = skill_cache_directory(WORKSPACE_RULES_CACHE, f"{sha256}.md")
                if not os.path.isfile(cache_path):
                    write_text_atomically(cache_path, text)
                files[workspace_selection.rule_tree_path(workspace["path"], rule_path)] = {
                    "profile": name, "source": template_origin(skill_dir, catalog, name, absolute_path),
                    "sourcePath": cache_path, "sha256": sha256, "workspace": workspace["path"],
                    "rulePath": rule_path}
    return files


def workspace_profile_origins(skill_dir, catalog, workspace_profiles):
    """{"<profile>:<path>": sha256} of every file of the profiles of the content only workspaces select.

    What those profiles project depends on the folders of this repository (rules with paths:, sections
    with the references of a workspace, the folders of their nested targets): the content digest takes
    the files they come from instead, so pinned content sees their change and the digest does not depend
    on the folders. Packs have their own digest.
    """
    origins = {}
    for name in workspace_profiles:
        asset_root = profile_asset_root(skill_dir, catalog, name)
        if is_pack_profile(name) or not asset_root:
            continue
        for relative_path, absolute_path in walk_content_files(asset_root):
            origins[f"{name}:{relative_path}"] = sha256_of_file(absolute_path)
    return origins


def block_item(skill_dir, catalog, profile_name, absolute_path):
    """{profile, source, content} of the block a profile publishes in ``absolute_path``."""
    with open(absolute_path, encoding="utf-8", newline="") as template_file:
        content = managed_blocks.normalized_content(template_file.read())
    return {"profile": profile_name, "source": template_origin(skill_dir, catalog, profile_name, absolute_path),
            "content": content}


def require_stack_section(catalog, profile_name, destination):
    """Only a stack profile adds a section to an AGENTS.md."""
    if profile_name == BASE_PROFILE_NAME or catalog["profiles"].get(profile_name, {}).get("kind") != STACK_PROFILE_KIND:
        raise ProfileError(f"profile '{profile_name}': only a stack profile adds a section to "
                           f"{destination}; nothing was written")


def workspace_blocks(skill_dir, catalog, workspaces, workspace_rules):
    """{(destination, id): item} of the AGENTS.md of each workspace, for Codex.

    It lists the rules of the workspace and keeps the section of each stack the workspace adds, with
    its references to those rules moved to the rules of the workspace: the skills and commands the
    section names are in .agents/ for the whole repository (is_workspace_shared_asset).
    """
    blocks = {}
    for workspace in workspaces:
        destination = nested.destination_in(workspace["path"])
        rule_paths = workspace_rule_paths(workspace_rules, workspace["path"])
        if rule_paths:
            blocks[(destination, workspace_selection.INDEX_BLOCK_ID)] = {
                "profile": BASE_PROFILE_NAME, "source": workspace_selection.INDEX_SOURCE,
                "content": workspace_selection.index_content(
                    workspace["path"],
                    [".agents/" + workspace_selection.rule_tree_path(workspace["path"], path) for path in rule_paths])}
        for name in workspace["own"]:
            asset_root = profile_asset_root(skill_dir, catalog, name)
            section = os.path.join(asset_root, managed_blocks.BLOCK_DIRECTORY,
                                   managed_blocks.INSTRUCTION_SECTIONS_DESTINATION) if asset_root else None
            if not section or not os.path.isfile(section):
                continue
            require_stack_section(catalog, name, destination)
            item = block_item(skill_dir, catalog, name, section)
            item["content"] = workspace_selection.with_workspace_references(item["content"], workspace["path"], rule_paths)
            blocks[(destination, name)] = item
    return blocks


def workspace_file_blocks(skill_dir, catalog, workspaces, assets, root_blocks, workspace_rules):
    """{(destination, id): item} of the blocks the profiles only workspaces select publish for other files.

    A block of a file Git or Docker reads for its own folder goes to the one of the workspace
    (agent_ready_workspaces.FOLDER_BLOCK_FILES) and names the rules of that workspace; any other goes to
    the root file, once for the repository, under the spelling the root selection already uses, and names
    the rules of every workspace that selects its profile. The section of AGENTS.md is workspace_blocks.
    """
    blocks = {}
    folded_assets = {destination.casefold() for destination in assets}
    spelling_by_folded = {destination.casefold(): destination for destination, _ in root_blocks}
    for workspace in workspaces:
        for name in workspace["own"]:
            asset_root = profile_asset_root(skill_dir, catalog, name)
            if not asset_root:
                continue
            for relative_path, absolute_path in walk_content_files(asset_root):
                destination = managed_blocks.destination_of(relative_path)
                if destination is None or destination == managed_blocks.INSTRUCTION_SECTIONS_DESTINATION:
                    continue
                managed_blocks.validate_destination(destination, name)
                scoped = workspace_selection.block_destination(workspace["path"], destination)
                workspace_paths = {workspace["path"]} if scoped != destination else \
                    {other["path"] for other in workspaces if name in other["own"]}
                destination = spelling_by_folded.setdefault(scoped.casefold(), scoped)
                if destination.casefold() in folded_assets:
                    raise ProfileError(f"profile '{name}' publishes a block for {destination}, which another "
                                       "profile writes as a whole file; nothing was written")
                item = block_item(skill_dir, catalog, name, absolute_path)
                item["content"] = workspace_selection.scoped_references(
                    item["content"], rule_workspaces_of(workspace_rules, workspace_paths))
                blocks[(destination, name)] = item
    return blocks


def desired_blocks(skill_dir, catalog, resolved, assets):
    """{(destination, id): {profile, source, content}} of every block the selection publishes.

    The id of a block is the name of its profile, so two profiles keep two blocks in one file.
    A file cannot be a whole managed asset and hold blocks at the same time.
    """
    sources = [(BASE_PROFILE_NAME, os.path.join(skill_dir, catalog.get("baseAssets", "assets/common")))]
    sources += [(name, profile_asset_root(skill_dir, catalog, name)) for name in resolved]
    blocks = {}
    folded_assets = {destination.casefold() for destination in assets}
    # On a case-insensitive filesystem PULL_REQUEST_TEMPLATE.md and pull_request_template.md are one
    # file: every block of it goes under the first spelling, so they are applied together.
    spelling_by_folded = {}
    for profile_name, root in sources:
        if not root:
            continue
        for relative_path, absolute_path in walk_content_files(root):
            destination = managed_blocks.destination_of(relative_path)
            if destination is None:
                continue
            managed_blocks.validate_destination(destination, profile_name)
            if destination == managed_blocks.INSTRUCTION_SECTIONS_DESTINATION:
                require_stack_section(catalog, profile_name, destination)
            destination = spelling_by_folded.setdefault(destination.casefold(), destination)
            if destination.casefold() in folded_assets:
                raise ProfileError(f"profile '{profile_name}' publishes a block for {destination}, which another "
                                   "profile writes as a whole file; nothing was written")
            blocks[(destination, profile_name)] = block_item(skill_dir, catalog, profile_name, absolute_path)
    return blocks


def nested_contents(skill_dir, catalog, resolved):
    """{id: {profile, source, content}} of every nested target the selection publishes, wherever it goes."""
    contents = {}
    for identifier, profile, name, _ in nested.declarations(catalog, resolved):
        path = nested.content_path(profile_asset_root(skill_dir, catalog, profile), name)
        if is_link(path) or not os.path.isfile(path):
            raise ProfileError(f"profile '{profile}' declares the nested target '{name}' but does not publish "
                               f"{nested.NESTED_PREFIX}{name}{nested.CONTENT_SUFFIX}")
        with open(path, encoding="utf-8", newline="") as template_file:
            content = managed_blocks.normalized_content(template_file.read())
        contents[identifier] = {"profile": profile, "source": template_origin(skill_dir, catalog, profile, path),
                                "content": content}
    return contents


def workspace_rule_paths(workspace_rules, workspace_path):
    """The paths under rules/ of the rules of one workspace (workspace_rule_files)."""
    return sorted(entry["rulePath"] for entry in workspace_rules.values() if entry["workspace"] == workspace_path)


def desired_nested_blocks(project_root, catalog, resolved, contents, workspaces=(), workspace_rules=None):
    """({(destination, id): {profile, source, content}}, report) of the nested targets of the selection.

    Each target puts its block, with its id, in the AGENTS.md of every folder it resolves to
    (agent_ready_nested.resolve): the folders of nested.targets, or else the first candidate that exists.
    A profile only a workspace selects looks for its candidates inside the workspace (apps/web/app), its
    block names the rules of the workspace (with_workspace_references) and its report entries carry the
    workspace; nested.targets applies by id wherever the profile is selected.
    """
    configuration = configuration_of(project_root)
    enabled = configuration.value(NESTED_ENABLED_KEY)
    configured = nested.configured_targets(configuration.value(NESTED_TARGETS_KEY), MANIFEST_RELATIVE_PATH)
    workspace_targets = [(workspace["path"], [
        (identifier, profile, name, [f"{workspace['path']}/{candidate}" for candidate in candidates])
        for identifier, profile, name, candidates in nested.declarations(catalog, workspace["own"])])
        for workspace in workspaces]
    workspace_ids = {target[0] for _, targets in workspace_targets for target in targets}
    root_folders, report = nested.resolve(
        project_root, nested.declarations(catalog, resolved), enabled,
        {identifier: setting for identifier, setting in configured.items() if identifier not in workspace_ids},
        MANIFEST_RELATIVE_PATH)
    folders = [(identifier, target_folders, None) for identifier, target_folders in root_folders.items()]
    for workspace_path, targets in workspace_targets:
        if not targets:
            continue
        identifiers = {target[0] for target in targets}
        # A folder of nested.targets goes to the workspace that holds it, so each block names its rules.
        settings = {identifier: (dict(setting, paths=[folder for folder in setting["paths"]
                                                      if workspace_selection.is_inside(folder, workspace_path)])
                                 if "paths" in setting else setting)
                    for identifier, setting in configured.items() if identifier in identifiers}
        target_folders, workspace_report = nested.resolve(project_root, targets, enabled, settings, MANIFEST_RELATIVE_PATH)
        report += [dict(entry, workspace=workspace_path) for entry in workspace_report]
        folders += [(identifier, paths, workspace_path) for identifier, paths in target_folders.items()]
    blocks = {}
    for identifier, target_folders, workspace_path in folders:
        item = dict(contents[identifier])
        if workspace_path:
            item["content"] = workspace_selection.with_workspace_references(
                item["content"], workspace_path, workspace_rule_paths(workspace_rules or {}, workspace_path))
        for folder in target_folders:
            blocks[(nested.destination_in(folder), identifier)] = dict(item)
    return blocks, report


def nested_index_block(project_root, nested_blocks, waiting):
    """({(AGENTS.md, id): item}, report) of the index of the nested AGENTS.md files in the root AGENTS.md.

    Codex reads the AGENTS.md files from the root down to the folder it starts in, once: the index tells
    it which nested ones to read before working in their folders. It lists every nested AGENTS.md the
    apply writes a block to (not one that waits, or sits beyond a symlink), and only when Codex is a
    provider of the repository and nested.codexIndex is on. The report has the files it lists and the
    bytes it adds to the root AGENTS.md, markers included.
    """
    configuration = configuration_of(project_root)
    destinations = sorted({destination for destination, _ in nested_blocks
                           if destination not in waiting and not managed_blocks.has_linked_directory(project_root, destination)})
    if not destinations or CODEX_PROVIDER not in configuration.value(PROVIDERS_KEY) \
            or not configuration.value(NESTED_CODEX_INDEX_KEY):
        return {}, {"destinations": [], "bytes": 0}
    destination, content = managed_blocks.INSTRUCTION_SECTIONS_DESTINATION, nested.index_content(destinations)
    index = {(destination, nested.INDEX_BLOCK_ID): {"profile": BASE_PROFILE_NAME, "source": nested.INDEX_SOURCE,
                                                    "content": content}}
    return index, {"destinations": destinations,
                   "bytes": text_bytes(managed_blocks.with_block("", destination, nested.INDEX_BLOCK_ID, content))}


def reject_destinations_inside_files(assets, destinations_by_folded_name):
    """A destination cannot sit under another one: one of the two could not be written."""
    for destination, entry in sorted(assets.items()):
        parent = os.path.dirname(destination)
        while parent:
            blocking = destinations_by_folded_name.get(parent.casefold())
            if blocking in assets:
                raise ProfileError(
                    f"profile '{assets[blocking]['profile']}' writes the file {blocking}, but profile "
                    f"'{entry['profile']}' needs it as a directory for {destination}; nothing was written. Rename one of the assets"
                )
            parent = os.path.dirname(parent)


def profile_digests(skill_dir, catalog, resolved):
    """Digest of each resolved profile: its asset bytes or its catalog entry."""
    digests = {}
    for name in [BASE_PROFILE_NAME] + resolved:
        if name == BASE_PROFILE_NAME:
            root = os.path.join(skill_dir, catalog.get("baseAssets", "assets/common"))
            entry = {"kind": "base"}
        else:
            root = profile_asset_root(skill_dir, catalog, name)
            entry = {
                field: value for field, value in catalog["profiles"][name].items()
                if field not in PROFILE_DIGEST_EXCLUDED_FIELDS
            }
        lines = [json.dumps(entry, sort_keys=True)]
        if root:
            lines += [f"{relative_path}\t{sha256_of_file(absolute_path)}" for relative_path, absolute_path in walk_content_files(root)]
        digests[name] = {"kind": entry.get("kind", "base"), "digest": sha256_of_text("\n".join(lines))}
    return digests


def compose_stack_directory(skill_dir, catalog, resolved, compose_root, workspace_rules=None, workspace_profiles=(),
                            shared_texts=None):
    """Return the stack tree Bash projects for the selected profiles.

    A single stack profile without extra assets uses its own directory, so the
    legacy layout is projected unchanged. Several asset profiles are copied into
    one composed tree; a relative path published by two profiles is an error.
    ``workspace_rules`` (workspace_rule_files) adds the rules of the workspaces under
    rules/workspaces/, so the projection writes them and links their Claude views, and
    ``workspace_profiles`` (the profiles only workspaces select) adds the rest of their assets
    (is_workspace_shared_asset), once for the repository, with the text of ``shared_texts``.
    """
    workspace_rules = workspace_rules or {}
    shared_texts = shared_texts or {}
    asset_profiles = [name for name in resolved if profile_asset_root(skill_dir, catalog, name)]
    shared_profiles = [name for name in workspace_profiles if profile_asset_root(skill_dir, catalog, name)]
    primary = primary_stack(catalog, resolved)
    overridden = shared_overrides(skill_dir, catalog, resolved, workspace_profiles)
    # The instruction scripts read rules/ of the tree: a stack without rules of its own (a pack stack
    # that only publishes its section) is composed, which gives the tree an empty rules/.
    if not overridden and not workspace_rules and not shared_profiles and not shared_texts and primary and asset_profiles == [primary] and \
            os.path.isdir(os.path.join(profile_asset_root(skill_dir, catalog, primary), "rules")):
        return profile_asset_root(skill_dir, catalog, primary)

    owners = {}
    for name in asset_profiles + shared_profiles:
        for relative_path, _ in walk_content_files(profile_asset_root(skill_dir, catalog, name)):
            if name in shared_profiles and not is_workspace_shared_asset(relative_path):
                continue
            if is_overridden(overridden, name, relative_path):
                # Another profile of the selection replaces it on purpose (overrides).
                continue
            if managed_blocks.destination_of(relative_path) is not None or relative_path.startswith(nested.NESTED_PREFIX):
                # Each profile keeps its own block of a shared file (desired_blocks) or of the AGENTS.md
                # of a folder (desired_nested_blocks).
                continue
            if relative_path in owners:
                raise ProfileError(
                    f"profiles '{owners[relative_path]}' and '{name}' both publish {relative_path}; "
                    "remove one of them or split the asset into a profile they both require"
                )
            owners[relative_path] = name

    if not compose_root:
        raise ProfileError("composing several asset profiles requires --compose-dir")
    # Two repositories can pin different revisions of a pack: they must not share a tree.
    tree_profiles = list(resolved) + list(workspace_profiles)
    pack_digests = profile_digests(skill_dir, catalog, [name for name in tree_profiles if is_pack_profile(name)]) if any(
        is_pack_profile(name) for name in tree_profiles
    ) else {}
    workspace_digest = {tree_path: entry["sha256"] for tree_path, entry in workspace_rules.items()}
    workspace_digest.update({text_path: sha256 for text_path, sha256 in shared_texts.values()})
    selection_key = sha256_of_text(
        os.path.abspath(skill_dir) + "\n" + ",".join(resolved) + "\n" + ",".join(workspace_profiles) + "\n"
        + json.dumps(pack_digests, sort_keys=True) + "\n" + json.dumps(workspace_digest, sort_keys=True)
    )[:16]
    destination = os.path.join(compose_root, selection_key)
    os.makedirs(compose_root, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".compose.", dir=compose_root)
    try:
        for relative_path, owner in sorted(owners.items()):
            source = os.path.join(profile_asset_root(skill_dir, catalog, owner), relative_path)
            source = shared_texts.get((owner, relative_path), (source,))[0]
            target = os.path.join(staging, relative_path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        for tree_path, entry in sorted(workspace_rules.items()):
            target = os.path.join(staging, *tree_path.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(entry["sourcePath"], target)
        os.makedirs(os.path.join(staging, "rules"), exist_ok=True)
        previous = None
        if os.path.exists(destination):
            previous = tempfile.mkdtemp(prefix=".previous.", dir=compose_root)
            os.rmdir(previous)
            os.replace(destination, previous)
        os.replace(staging, destination)
        if previous:
            shutil.rmtree(previous, ignore_errors=True)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
