"""The AI reviews as plan and status show them: the current findings and decisions, read without calling the
provider, and the review settings an apply leaves where the hooks read them.
"""

import sys

import agent_ready_blocks as managed_blocks
import agent_ready_conflicts as conflicts_review
from agent_ready_config import ConfigurationError
from agent_ready_layout import review_cache_module
from agent_ready_manifest import configuration_of
from agent_ready_options import REVIEWS_CACHE_KEY, REVIEWS_COMMIT_KEY, REVIEWS_ENABLED_KEY, REVIEWS_TTL_KEY
from agent_ready_removal import without_instruction_blocks


def review_findings(project_root, strict=False):
    """Every finding of the current reviews with its id and status, read without calling the provider.

    Returns (findings, decisions, units, stale). An entry whose files changed since its review is
    out of date: it is counted in stale, not shown, and runs again on the next edit or apply.
    ``strict`` refuses a decisions file that cannot be read instead of ignoring it.
    """
    module = review_cache_module()
    # The effective configuration, not the options of the last apply: a fresh clone shows the
    # committed reviews before anyone applies.
    try:
        commit = configuration_of(project_root).value(REVIEWS_COMMIT_KEY)
    except ConfigurationError:
        commit = None
    entries = module.ReviewCache(project_root).entries(commit=commit)
    decisions = module.Decisions(project_root)
    recorded = decisions.read(strict=strict)
    findings = []
    units = 0
    stale = 0
    for unit, entry in sorted(entries.items()):
        files = entry.get("files", {}) if isinstance(entry, dict) else {}
        # A semantic conflict with an AGENTS.md is about what the project wrote there, not the managed blocks.
        semantic = (isinstance(entry, dict) and entry.get("check") == conflicts_review.CONFLICT_CHECK
                    and any(conflicts_review.is_instructions(name) for name in files))
        current = (conflicts_review.current_hashes(module, project_root, files, project_owned_instructions)
                   if semantic else module.file_hashes(project_root, files))
        if files and current == files:
            units += 1
            annotated = decisions.annotate(unit, entry.get("findings", []), recorded)
            if semantic:
                for finding in annotated:
                    finding["reviewedFiles"] = current
                    if finding["decision"]:
                        finding["status"] = conflicts_review.decision_status(module, finding["decision"], current)
            findings += [dict(finding, check=entry.get("check")) for finding in annotated]
        else:
            stale += 1
    return findings, recorded, units, stale


def review_summary(project_root):
    """What status and plan show of the AI reviews: open findings and decisions to confirm."""
    module = review_cache_module()
    findings, decisions, units, stale = review_findings(project_root)
    shown = module.visible(findings)
    return {"units": units, "stale": stale, "findings": shown, "quiet": len(findings) - len(shown),
            "decisions": len(decisions)}


def record_review_settings(project_root):
    """Leave the reviews options where the hooks read them, so they follow the configuration."""
    configuration = configuration_of(project_root)
    module = review_cache_module()
    try:
        module.ReviewCache(project_root).write_settings(configuration.value(REVIEWS_ENABLED_KEY),
                                                        configuration.value(REVIEWS_CACHE_KEY),
                                                        configuration.value(REVIEWS_TTL_KEY),
                                                        configuration.value(REVIEWS_COMMIT_KEY))
    except (OSError, module.CacheLockTimeout) as caught_error:
        sys.stderr.write(f"WARNING: the review settings were not recorded: {caught_error}\n")


def project_owned_instructions(text):
    """What the project wrote in AGENTS.md: the managed block and the stack sections are the engine's,
    and an update replaces them."""
    destination = managed_blocks.INSTRUCTION_SECTIONS_DESTINATION
    try:
        remaining = without_instruction_blocks(text, sorted(managed_blocks.parse(text, destination)))
    except (ValueError, managed_blocks.MarkerError):
        # Markers that are not one pair: nothing can tell the block apart, so all of it is reviewed.
        return text
    return text if remaining is None else remaining
