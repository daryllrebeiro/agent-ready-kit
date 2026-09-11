"""Configuration and weights for Agent-Ready scoring algorithm."""

# Single source of truth lives in packages.core.version (Sprint 0.5).
# Re-exported here (with __all__) because scorer, CLI, and checks import
# the weights/version from this module; do not let linters remove this.
from packages.core.version import ALGORITHM_VERSION, DEFAULT_WEIGHTS

__all__ = [
    "ALGORITHM_VERSION",
    "DEFAULT_WEIGHTS",
    "GRADE_THRESHOLDS",
    "TARGET_AI_BOTS",
    "get_grade",
]

# Major AI crawlers and scrapers evaluated in robots.txt
TARGET_AI_BOTS: list[dict[str, str]] = [
    {
        "name": "GPTBot",
        "owner": "OpenAI",
        "description": "OpenAI training and data collection crawler",
    },
    {
        "name": "ChatGPT-User",
        "owner": "OpenAI",
        "description": "Direct browsing agent used by ChatGPT Plus/Enterprise users",
    },
    {
        "name": "ClaudeBot",
        "owner": "Anthropic",
        "description": "Anthropic model training and search crawler",
    },
    {
        "name": "Claude-Web",
        "owner": "Anthropic",
        "description": "Direct real-time browsing agent used by Claude users",
    },
    {
        "name": "PerplexityBot",
        "owner": "Perplexity",
        "description": "Perplexity AI search engine crawler",
    },
    {
        "name": "Google-Extended",
        "owner": "Google",
        "description": "Google Gemini & AI training/grounding crawler",
    },
    {
        "name": "Applebot-Extended",
        "owner": "Apple",
        "description": "Apple Intelligence data crawler",
    },
    {
        "name": "CCBot",
        "owner": "Common Crawl",
        "description": "Open web archive used widely by LLM foundations",
    },
    {
        "name": "cohere-ai",
        "owner": "Cohere",
        "description": "Cohere LLM crawler",
    },
]

# Grade thresholds
GRADE_THRESHOLDS = [
    (95.0, "A+"),
    (85.0, "A"),
    (70.0, "B"),
    (50.0, "C"),
    (35.0, "D"),
    (0.0, "F"),
]


def get_grade(score: float) -> str:
    """Return letter grade corresponding to numerical score."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"
