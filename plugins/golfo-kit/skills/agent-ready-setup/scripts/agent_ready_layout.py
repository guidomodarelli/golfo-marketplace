"""Where the engine's files live: in the repository (the manifest, the .claude views, the managed block of
AGENTS.md) and in the skill directory (the catalog, the templates of the merged settings, the CLAUDE.md proxy
and the review cache of the hooks).
"""

import os

from agent_ready_config import PROJECT_CONFIG_RELATIVE_PATH

MANIFEST_RELATIVE_PATH = PROJECT_CONFIG_RELATIVE_PATH
# The review cache lives with the hooks, which also run where the skill is not installed.
REVIEW_CACHE_RELATIVE_PATH = "assets/common/hooks/review-cache.py"
ENGINE_SKILL_DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_CATALOG_RELATIVE_PATH = "assets/profiles.json"
CODEX_HOOKS_TEMPLATE_RELATIVE_PATH = "assets/codex/hooks.json"
# The template of .claude/settings.json is part of the engine, beside its hooks.
CLAUDE_SETTINGS_TEMPLATE_RELATIVE_PATH = "assets/common/settings.json"
# The project part of a new AGENTS.md that a profile publishes in place of the template's.
AGENTS_SKELETON_NAME = "agents-skeleton.md"
CLAUDE_PROXY_RELATIVE_PATH = "assets/claude-proxy.md"
MANAGED_BLOCK_START = "<!-- BEGIN AGENT-READY MANAGED -->"
MANAGED_BLOCK_END = "<!-- END AGENT-READY MANAGED -->"
# Assets under these directories have a view under .claude/; hooks stay canonical in .agents/.
CLAUDE_VIEW_DIRECTORIES = ("rules", "agents", "commands", "skills")

_REVIEW_CACHE = None


def review_cache_module():
    """review-cache.py of this installation, loaded once; its file name is not importable directly."""
    global _REVIEW_CACHE
    if _REVIEW_CACHE is None:
        import importlib.util

        path = os.path.join(ENGINE_SKILL_DIRECTORY, REVIEW_CACHE_RELATIVE_PATH)
        specification = importlib.util.spec_from_file_location("review_cache", path)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        _REVIEW_CACHE = module
    return _REVIEW_CACHE


def claude_proxy_text(skill_dir):
    """The CLAUDE.md proxy the normalization writes next to every AGENTS.md."""
    with open(os.path.join(skill_dir, CLAUDE_PROXY_RELATIVE_PATH), encoding="utf-8", newline="") as file_handle:
        return file_handle.read()


def settings_templates(skill_dir):
    """Merged JSON files and the template each one is merged from."""
    return (
        (".claude/settings.json", os.path.join(skill_dir, *CLAUDE_SETTINGS_TEMPLATE_RELATIVE_PATH.split("/"))),
        (".codex/hooks.json", os.path.join(skill_dir, CODEX_HOOKS_TEMPLATE_RELATIVE_PATH)),
    )
