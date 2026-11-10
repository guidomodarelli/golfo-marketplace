"""Options of the configuration that the scripts read, by their dotted key.

Types, defaults and descriptions live only in the schemas of ``assets/config/``, which
``agent_ready_config`` resolves layer by layer; this module just names the keys and the
values that the code compares against, so no default is repeated here.
"""

PROFILES_KEY = "profiles"
PROVIDERS_KEY = "providers"
DETECTION_ENABLED_KEY = "detection.enabled"
SOURCES_ENABLED_KEY = "sources.enabled"
SOURCES_PACKS_KEY = "sources.packs"
SOURCES_GOLFO_KIT_REF_KEY = "sources.golfoKit.ref"
SOURCES_GOLFO_KIT_UPDATES_KEY = "sources.golfoKit.updates"
UPDATES_MODE_KEY = "updates.mode"
UPDATES_REFRESH_KEY = "updates.refresh"
UPDATES_FROM_LOCK_KEY = "updates.fromLock"
UPDATES_PRESET_KEY = "updates.preset"
CI_ENABLED_KEY = "ci.enabled"
CI_MODE_KEY = "ci.mode"
CI_PROVIDER_KEY = "ci.provider"
TOOLS_ENABLED_KEY = "tools.enabled"
TRUSTED_PROJECTS_KEY = "security.trustedProjects"
REVIEWS_ENABLED_KEY = "reviews.enabled"
CONFLICTS_ENABLED_KEY = "conflicts.enabled"
CONFLICTS_BLOCK_KEY = "conflicts.block"
REVIEWS_CACHE_KEY = "reviews.cache"
REVIEWS_TTL_KEY = "reviews.ttl"
REVIEWS_COMMIT_KEY = "reviews.commit"

UPDATES_AUTO = "auto"
UPDATES_PINNED = "pinned"
UPDATE_MODES = (UPDATES_AUTO, UPDATES_PINNED)
CI_WARN = "warn"
CI_PROVIDER_NONE = "none"
SUPPORTED_PROVIDERS = ("claude", "codex")
