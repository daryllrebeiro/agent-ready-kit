"""Single source of truth for version, key prefixes, and scoring weights.

Sprint 0 (IMPLEMENTATION_PLAN.md 0.5): exactly one version string, one key
prefix, one weight table. All other modules must import from here.
"""

ALGORITHM_VERSION = "score_v0.1"
AGENTREADY_VERSION = "0.1.0"
API_KEY_PREFIX = "ark_live_"
SHARE_TOKEN_PREFIX = "dst_"

# Canonical v0.1 weights — sum to 1.0. Recorded into Score.metadata["weights"].
DEFAULT_WEIGHTS = {
    "llms_txt": 0.30,
    "structured_data": 0.30,
    "token_bloat": 0.20,
    "bot_permissions": 0.20,
}
