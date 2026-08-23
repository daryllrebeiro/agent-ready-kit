"""Security and prompt-injection defense for MCP gateway."""

import re
from typing import List, Tuple

INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"\[SYSTEM_PROMPT_OVERRIDE\]", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+must", re.IGNORECASE),
    re.compile(r"elevate\s+privileges", re.IGNORECASE),
]


def detect_prompt_injection(content: str) -> Tuple[bool, List[str]]:
    """Scan content for known prompt injection and jailbreak patterns."""
    detected = []
    for pattern in INJECTION_PATTERNS:
        match = pattern.search(content)
        if match:
            detected.append(match.group(0))
    return bool(detected), detected


def sanitize_mcp_content(content: str) -> str:
    """Sanitize content to prevent delimiter escaping and prompt injections."""
    if not content:
        return ""

    sanitized = content
    for pattern in INJECTION_PATTERNS:
        sanitized = pattern.sub("[REDACTED_PROMPT_INJECTION]", sanitized)

    # Escape raw template delimiters
    sanitized = sanitized.replace("<|im_start|>", "[sanitized]").replace("<|im_end|>", "[sanitized]")
    return sanitized
