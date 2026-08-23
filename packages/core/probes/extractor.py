"""Citation extraction utilities for parsing LLM probe responses."""

import re
from typing import Any, Dict, List, Set
from urllib.parse import urlparse


def extract_domain_from_url(url: str) -> str:
    """Normalize and extract clean base domain from a URL."""
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        # Strip port and www
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def extract_citations(text: str) -> Dict[str, Any]:
    """Extract explicit URLs and cited domains from raw LLM text while keeping raw response intact."""
    if not text:
        return {"urls": [], "domains": []}

    found_urls: List[str] = []
    found_domains: Set[str] = set()

    # 1. Full URLs: https://... or http://...
    raw_url_pattern = re.compile(r"https?://[^\s)\]\"'>,]+")
    for match in raw_url_pattern.finditer(text):
        url = match.group(0).rstrip(".,;:)")
        if url and url not in found_urls:
            found_urls.append(url)
            domain = extract_domain_from_url(url)
            if domain:
                found_domains.add(domain)

    # 2. Markdown Links: [Title](url)
    md_link_pattern = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
    for match in md_link_pattern.finditer(text):
        url = match.group(2).strip()
        if url and url not in found_urls:
            found_urls.append(url)
            domain = extract_domain_from_url(url)
            if domain:
                found_domains.add(domain)

    # 3. Source citations: (source: domain.com) or (via domain.com) or [Source: domain.com]
    source_pattern = re.compile(
        r"(?:source|via|ref|according to)\s*[:=]?\s*\[?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s)\]]*)?)",
        re.IGNORECASE,
    )
    for match in source_pattern.finditer(text):
        candidate = match.group(1).strip().rstrip(".,;:)")
        domain = extract_domain_from_url(candidate)
        if domain and "." in domain and not domain.endswith("."):
            found_domains.add(domain)

    # 4. Domain mentions: e.g. "github.com/...", "agentready.dev", "stripe.com"
    domain_mention_pattern = re.compile(
        r"\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|org|dev|io|ai|net|app|co|xyz|tech|so|sh|me|edu|gov))\b",
        re.IGNORECASE,
    )
    for match in domain_mention_pattern.finditer(text):
        domain = match.group(1).lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        found_domains.add(domain)

    return {
        "urls": found_urls,
        "domains": sorted(list(found_domains)),
    }
