"""Security and prompt-injection defense for MCP gateway with multi-vector adversarial detection."""

import re
import unicodedata
from typing import List, Tuple

INJECTION_PATTERNS: List[re.Pattern] = [
    # 1. Direct instruction overrides
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous|initial)\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"do\s+anything\s+now\s*\(dan\)", re.IGNORECASE),
    re.compile(r"bypass\s+all\s+(safety|content)\s+filters", re.IGNORECASE),
    
    # 2. Token and role delimiters
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"\[SYSTEM_PROMPT_OVERRIDE\]", re.IGNORECASE),
    re.compile(r"\[\/?INST\]", re.IGNORECASE),
    re.compile(r"<\/?(system|assistant|user)>", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+must", re.IGNORECASE),
    
    # 3. Privilege escalation and system manipulation
    re.compile(r"elevate\s+privileges", re.IGNORECASE),
    re.compile(r"print\s+your\s+(initial|system)\s+prompt", re.IGNORECASE),
    re.compile(r"reveal\s+your\s+hidden\s+instructions", re.IGNORECASE),
    
    # 4. Indirect exfiltration via Markdown image/link payloads
    re.compile(r"!\[.*?\]\(https?:\/\/[^\s\)]+(\?|\&)(data|token|key|cookie)=", re.IGNORECASE),
]


def normalize_input_text(text: str) -> str:
    """Normalizes unicode characters, strips zero-width spaces and homoglyphs."""
    if not text:
        return ""
    # Strip zero-width spaces, soft hyphens, and invisible formatting chars
    cleaned = re.sub(r"[\u200B-\u200D\uFEFF\u00AD]", "", text)
    # NFKD unicode normalization
    normalized = unicodedata.normalize("NFKD", cleaned)
    return normalized


def detect_prompt_injection(content: str) -> Tuple[bool, List[str]]:
    """Scan content for known prompt injection, jailbreak, and exfiltration patterns."""
    if not content:
        return False, []
    
    normalized = normalize_input_text(content)
    detected = []
    for pattern in INJECTION_PATTERNS:
        match = pattern.search(normalized)
        if match:
            detected.append(match.group(0))
    return bool(detected), detected


def sanitize_mcp_content(content: str) -> str:
    """Sanitize content to prevent delimiter escaping, prompt injections, and exfiltration."""
    if not content:
        return ""

    sanitized = normalize_input_text(content)
    for pattern in INJECTION_PATTERNS:
        sanitized = pattern.sub("[REDACTED_PROMPT_INJECTION]", sanitized)

    # Escape raw template delimiters
    sanitized = (
        sanitized.replace("<|im_start|>", "[sanitized]")
        .replace("<|im_end|>", "[sanitized]")
        .replace("<system>", "[sanitized]")
        .replace("</system>", "[sanitized]")
    )
    return sanitized
