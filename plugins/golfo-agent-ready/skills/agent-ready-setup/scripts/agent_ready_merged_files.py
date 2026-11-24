"""The rendered instructions and the merged files: the AGENTS.md an apply would write, the settings and Codex hooks
it would merge, and the CLAUDE.md proxies that no longer match the engine's.
"""

import os
import subprocess
import sys
import tempfile

import agent_ready_antigravity_hooks as antigravity_hooks
import agent_ready_nested as nested
from agent_ready_actions import ACTION_CONFLICT, ACTION_CREATE, ACTION_UNCHANGED, ACTION_UPDATE
from agent_ready_common import bash_executable, run_quiet, sha256_of_file
from agent_ready_desired_assets import compose_stack_directory
from agent_ready_layout import (
    AGENTS_SKELETON_NAME,
    CENTRALIZATION_RELATIVE_PATH,
    CLAUDE_PROXY_RELATIVE_PATH,
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_START,
    RENDERER_RELATIVE_PATH,
)
from agent_ready_manifest import configuration_of
from agent_ready_options import ANTIGRAVITY_PROVIDER, PROVIDERS_KEY
from agent_ready_profiles import load_effective_catalog
from agent_ready_source_identity import agents_template_path

SETTINGS_MERGER_RELATIVE_PATH = "scripts/merge-managed-settings.py"
CODEX_HOOKS_MERGER_RELATIVE_PATH = "scripts/merge-codex-hooks.py"
SETTINGS_TEMPLATE_FALLBACK_STATUS = 10


def extract_managed_block(text):
    """Text between the managed markers (inclusive), or None."""
    start = text.find(MANAGED_BLOCK_START)
    end = text.find(MANAGED_BLOCK_END)
    if start < 0 or end < start:
        return None
    return text[start:end + len(MANAGED_BLOCK_END)]


def render_instructions(skill_dir, catalog, stack_root, project_rules_root, managed_block_only):
    """AGENTS.md as render-instruction-template.sh writes it, or only its managed block; None on failure.

    The new file takes the skeleton of the composed tree when a profile publishes one, as the
    instruction normalization does.
    """
    renderer = [
        bash_executable(), os.path.join(skill_dir, RENDERER_RELATIVE_PATH),
        "--template", agents_template_path(skill_dir, catalog),
        "--rules-dir", os.path.join(stack_root, "rules"),
        "--common-rules-dir", os.path.join(skill_dir, catalog.get("baseAssets", "assets/common"), "rules"),
        "--centralization", os.path.join(skill_dir, CENTRALIZATION_RELATIVE_PATH),
    ]
    if managed_block_only:
        renderer.append("--managed-block")
    else:
        skeleton = os.path.join(stack_root, AGENTS_SKELETON_NAME)
        if os.path.isfile(skeleton):
            renderer += ["--skeleton", skeleton]
    if project_rules_root:
        renderer += ["--project-rules-dir", project_rules_root]
    try:
        completed = subprocess.run(renderer, capture_output=True, encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None
    return completed.stdout if completed.returncode == 0 else None


def merged_file_changes(project_root, skill_dir, plan, source_state=None):
    """Describe whether each merged file would change, without writing it."""
    # The effective catalog: composing the tree needs the asset roots of the pack profiles too.
    catalog = load_effective_catalog(project_root, skill_dir, source_state)
    # Bootstrap exports the composed tree, the one the managed block is rendered from; without it the
    # tree is composed in a temporary directory, so a plan still writes nothing of its own.
    stack_root = os.environ.get("AGENT_READY_SETUP_STACK_DIR")
    if stack_root:
        return merged_file_changes_from(project_root, skill_dir, plan, catalog, stack_root)
    with tempfile.TemporaryDirectory(prefix="agent-ready-plan-compose.") as compose_root:
        stack_root = compose_stack_directory(skill_dir, catalog, plan["profiles"], compose_root)
        return merged_file_changes_from(project_root, skill_dir, plan, catalog, stack_root)


def merged_file_changes_from(project_root, skill_dir, plan, catalog, stack_root):
    """merged_file_changes with the stack tree the managed block is rendered from."""
    changes = []

    agents_path = os.path.join(project_root, "AGENTS.md")
    project_rules_root = os.path.join(project_root, ".agents", "rules")
    rendered_block = render_instructions(skill_dir, catalog, stack_root,
                                         project_rules_root if os.path.isdir(project_rules_root) else None,
                                         managed_block_only=True)
    if not os.path.isfile(agents_path):
        changes.append(("AGENTS.md", ACTION_CREATE, "created from the base template"))
    else:
        with open(agents_path, encoding="utf-8") as file_handle:
            current_block = extract_managed_block(file_handle.read())
        if current_block is None:
            changes.append(("AGENTS.md", ACTION_UPDATE, "no managed block yet; the instruction review migrates it"))
        elif rendered_block is None:
            changes.append(("AGENTS.md", ACTION_CONFLICT, "managed block could not be rendered"))
        elif extract_managed_block(rendered_block) != current_block:
            changes.append(("AGENTS.md", ACTION_UPDATE, "managed block changes; project content is preserved"))
        else:
            changes.append(("AGENTS.md", ACTION_UNCHANGED, "managed block is current"))

    for destination, merger, extra_arguments in (
        (".claude/settings.json", SETTINGS_MERGER_RELATIVE_PATH, ["--allow-nested-template-match"]),
        (".codex/hooks.json", CODEX_HOOKS_MERGER_RELATIVE_PATH, []),
    ):
        entry = plan["merged"].get(destination)
        if not entry:
            continue
        template = os.path.join(skill_dir, entry["template"])
        current = os.path.join(project_root, destination)
        if not os.path.isfile(current):
            changes.append((destination, ACTION_CREATE, "created from the template"))
            continue
        command = [sys.executable, os.path.join(skill_dir, merger)] + extra_arguments + [template, current]
        try:
            completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", check=False)
        except OSError as caught_error:
            changes.append((destination, ACTION_CONFLICT, f"merge preview failed: {caught_error}"))
            continue
        merged_text = completed.stdout
        if completed.returncode == SETTINGS_TEMPLATE_FALLBACK_STATUS:
            with open(template, encoding="utf-8") as file_handle:
                merged_text = file_handle.read()
        elif completed.returncode != 0:
            changes.append((destination, ACTION_CONFLICT, "invalid JSON; it is preserved"))
            continue
        with open(current, encoding="utf-8") as file_handle:
            current_text = file_handle.read()
        if merged_text == current_text:
            changes.append((destination, ACTION_UNCHANGED, "managed entries are current"))
        else:
            changes.append((destination, ACTION_UPDATE, "managed entries change; custom entries are preserved"))
    antigravity_change = antigravity_hooks_change(project_root, skill_dir)
    if antigravity_change:
        changes.append(antigravity_change)
    return changes


def antigravity_hooks_change(project_root, skill_dir):
    """What the projection does to .agents/hooks.json (sync_antigravity_hooks of asset-sync-common.sh), or None.

    With Antigravity among the providers the managed hook name is merged in; without it, the name
    leaves a file that has it. The preview reads the same module the merge helper runs."""
    destination = antigravity_hooks.HOOKS_RELATIVE_PATH
    current_path = os.path.join(project_root, *destination.split("/"))
    selected = ANTIGRAVITY_PROVIDER in configuration_of(project_root).value(PROVIDERS_KEY)
    if not selected and not os.path.isfile(current_path):
        return None
    try:
        current = antigravity_hooks.read(current_path)
    except antigravity_hooks.HooksError:
        return (destination, ACTION_CONFLICT, "invalid JSON; it is preserved")
    if not selected:
        if antigravity_hooks.MANAGED_GROUP not in current:
            return None
        return (destination, ACTION_UPDATE, "Antigravity is no longer a provider: the agent-ready hooks leave")
    if not os.path.isfile(current_path):
        return (destination, ACTION_CREATE, "created from the template")
    template = antigravity_hooks.read(os.path.join(skill_dir, *antigravity_hooks.TEMPLATE_RELATIVE_PATH.split("/")))
    with open(current_path, encoding="utf-8") as file_handle:
        current_text = file_handle.read()
    if antigravity_hooks.serialize(antigravity_hooks.merged(current, template)) == current_text:
        return (destination, ACTION_UNCHANGED, "managed entries are current")
    return (destination, ACTION_UPDATE, "managed entries change; custom entries are preserved")


def claude_proxy_drift(project_root, skill_dir):
    """CLAUDE.md files that instruction normalization would rewrite or create."""
    proxy_path = os.path.join(skill_dir, CLAUDE_PROXY_RELATIVE_PATH)
    listed = run_quiet(["git", "ls-files", "-co", "--exclude-standard"], cwd=project_root)
    if listed is None or not os.path.isfile(proxy_path):
        return []
    proxy_hash = sha256_of_file(proxy_path)
    listed_paths = listed.splitlines()
    existing_proxies = {path.casefold() for path in listed_paths if os.path.basename(path).lower() == "claude.md"}
    drifted = []
    # The root always needs its proxy, and so does every AGENTS.md: it is what loads the instructions.
    required_proxies = {"CLAUDE.md"}
    for relative_path in listed_paths:
        file_name = os.path.basename(relative_path).lower()
        if file_name == "agents.md":
            required_proxies.add(os.path.join(os.path.dirname(relative_path), "CLAUDE.md").replace(os.sep, "/"))
        elif file_name == "claude.md":
            absolute_path = os.path.join(project_root, relative_path)
            if not os.path.isfile(absolute_path) or os.path.islink(absolute_path):
                continue
            # A nested CLAUDE.md is the import alone; the root one is the whole proxy (instruction-normalization.sh).
            if os.path.dirname(relative_path):
                normalized = nested.is_bare_proxy(absolute_path)
            else:
                normalized = sha256_of_file(absolute_path) == proxy_hash
            if not normalized:
                drifted.append(relative_path)
    for proxy in sorted(required_proxies):
        if proxy.casefold() not in existing_proxies and not os.path.lexists(os.path.join(project_root, proxy)):
            drifted.append(proxy)
    return drifted
