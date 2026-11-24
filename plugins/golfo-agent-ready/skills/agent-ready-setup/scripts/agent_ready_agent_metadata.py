"""Portable metadata of a subagent: how much it can touch (access) and how strong a model it needs (model-tier).

A subagent template (agents/<name>.md) may declare, in its frontmatter:

* ``access: read-only | edit | full``: read-only reads and searches, edit also writes files, full also runs
  commands;
* ``model-tier: fast | balanced | deep``.

Each provider names tools and models differently, so the template carries only these two words and the
engine renders the view of each provider from the mapping of assets/providers.json (``agentMetadata``):
the .agents/agents/<name>.md that Antigravity reads (``tools`` and ``model`` in its own names), the
.claude/agents/<name>.md of Claude Code (a generated file instead of a view of the canonical one) and the
.codex/agents/<name>.toml of Codex (agent_ready_codex_agents). A template without them is projected as
it always was. What a provider cannot enforce (Codex keeps the sandbox of the session that starts the
subagent) is reported by plan (limitations).
"""

import json
import os

from agent_ready_common import ProfileError
from agent_ready_layout import PROVIDER_CATALOG_RELATIVE_PATH

ACCESS_KEY = "access"
MODEL_TIER_KEY = "model-tier"
PORTABLE_KEYS = (ACCESS_KEY, MODEL_TIER_KEY)
ACCESS_VALUES = ("read-only", "edit", "full")
MODEL_TIER_VALUES = ("fast", "balanced", "deep")
METADATA_CATALOG_KEY = "agentMetadata"
FRONTMATTER_FENCE = "---"
# The views of a subagent with metadata, by provider.
VIEW_ANTIGRAVITY = "antigravity"
VIEW_CLAUDE = "claude"
VIEW_CODEX = "codex"
# The keys of the frontmatter of a view that the mapping writes; any other key of the template stays.
VIEW_KEYS = ("tools", "model")


def split(text):
    """(frontmatter lines, body lines) of a subagent template; (None, lines) without a closed frontmatter."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == FRONTMATTER_FENCE:
        for index in range(1, len(lines)):
            if lines[index].strip() == FRONTMATTER_FENCE:
                return lines[1:index], lines[index + 1:]
    return None, lines


def key_of(line):
    """The top-level key of a frontmatter line, or None for a continuation or a comment."""
    if not line or line[0] in (" ", "\t", "#", "-") or ":" not in line:
        return None
    return line.split(":", 1)[0].strip()


def metadata(text, origin):
    """{access, model-tier} the template declares (each optional); a value outside its list fails, naming ``origin``."""
    header, _ = split(text)
    found = {}
    for line in header or []:
        key = key_of(line)
        if key not in PORTABLE_KEYS:
            continue
        value = line.split(":", 1)[1].split(" #", 1)[0].strip().strip("\"'")
        allowed = ACCESS_VALUES if key == ACCESS_KEY else MODEL_TIER_VALUES
        if value not in allowed:
            raise ProfileError(f"{origin}: {key} is {value!r}; it must be one of {', '.join(allowed)}")
        found[key] = value
    return found


def mapping(skill_dir):
    """{provider: {access: {...}, model-tier: {...}}} of assets/providers.json."""
    with open(os.path.join(skill_dir, *PROVIDER_CATALOG_RELATIVE_PATH.split("/")), encoding="utf-8") as catalog_file:
        providers = json.load(catalog_file).get("providers", {})
    return {name: provider.get(METADATA_CATALOG_KEY, {}) for name, provider in providers.items()}


def view_fields(skill_dir, provider, declared):
    """{key: value} a provider gets for the declared metadata: the union of what access and model-tier map to."""
    provider_mapping = mapping(skill_dir).get(provider, {})
    fields = {}
    for key, value in declared.items():
        fields.update(provider_mapping.get(key, {}).get(value, {}))
    return fields


def yaml_value(value):
    """A frontmatter value: a list as an inline YAML sequence, anything else as a quoted-when-needed scalar."""
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(item) for item in value) + "]"
    return str(value)


def render_markdown_view(text, fields):
    """The template with its portable keys replaced by ``fields`` (tools, model) of one provider."""
    header, body = split(text)
    kept = [line for line in header if key_of(line) not in PORTABLE_KEYS + VIEW_KEYS]
    extra = [f"{key}: {yaml_value(fields[key])}" for key in VIEW_KEYS if key in fields]
    return "\n".join([FRONTMATTER_FENCE] + kept + extra + [FRONTMATTER_FENCE] + body)


def render_view(skill_dir, text, origin, provider):
    """The Markdown view of a subagent template for ``provider`` (antigravity or claude), or None when the
    template declares no metadata (the canonical file, or its view, is projected as it is)."""
    declared = metadata(text, origin)
    if not declared:
        return None
    return render_markdown_view(text, view_fields(skill_dir, provider, declared))


def limitations(skill_dir, declared):
    """[(provider, note)] of what a provider cannot enforce for the declared metadata (``limitation`` in the mapping)."""
    notes = []
    for provider, provider_mapping in sorted(mapping(skill_dir).items()):
        for key, value in declared.items():
            note = provider_mapping.get(key, {}).get(value, {}).get("limitation")
            if note:
                notes.append((provider, note))
    return notes
