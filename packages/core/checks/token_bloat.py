"""Check token efficiency, content density, and HTML bloat for LLM agent ingestion."""

import re
from typing import Any, Dict, List
from bs4 import BeautifulSoup, Comment
from packages.core.schemas import ComponentStatus, ScoreComponent


def clean_html_content(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract clean readable text and compute noise metrics."""
    # Clone soup
    page = BeautifulSoup(str(soup), "html.parser")

    # Remove comments
    for comment in page.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Measure script, style, svg bytes
    script_bytes = sum(len(str(s)) for s in page.find_all("script"))
    style_bytes = sum(len(str(s)) for s in page.find_all(["style", "link"]))
    svg_bytes = sum(len(str(s)) for s in page.find_all("svg"))

    # Extract semantic structure
    has_h1 = bool(page.find("h1"))
    h1_count = len(page.find_all("h1"))
    h2_count = len(page.find_all("h2"))
    has_main = bool(page.find(["main", "article"]))

    # Strip noisy elements for main text extraction
    for tag in page.find_all(["script", "style", "svg", "noscript", "iframe"]):
        tag.decompose()

    # Extract cleaned text
    text = page.get_text(separator=" ", strip=True)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Approximate token count (roughly 1 token per 4 chars for English)
    estimated_tokens = max(1, len(text) // 4)

    return {
        "text_content_length": len(text),
        "estimated_tokens": estimated_tokens,
        "script_bytes": script_bytes,
        "style_bytes": style_bytes,
        "svg_bytes": svg_bytes,
        "has_h1": has_h1,
        "h1_count": h1_count,
        "h2_count": h2_count,
        "has_semantic_main": has_main,
    }


def check_token_bloat(
    html: str,
    weight: float = 0.20,
) -> ScoreComponent:
    """Evaluate HTML token bloat and content density."""
    recommendations: List[str] = []
    html_bytes = len(html.encode("utf-8")) if html else 0

    if html_bytes == 0:
        return ScoreComponent(
            name="token_bloat",
            display_name="Content Token Efficiency",
            score=0.0,
            weight=weight,
            status=ComponentStatus.FAIL,
            evidence={"html_bytes": 0},
            details="Empty document provided.",
            recommendations=["Ensure the server returns rendered HTML content rather than empty responses."],
        )

    soup = BeautifulSoup(html, "html.parser")
    metrics = clean_html_content(soup)

    text_length = metrics["text_content_length"]
    # Ratio of extracted text bytes to raw HTML bytes
    content_ratio = (text_length / max(1, html_bytes)) * 100.0
    overhead_bytes = metrics["script_bytes"] + metrics["style_bytes"] + metrics["svg_bytes"]
    overhead_ratio = (overhead_bytes / max(1, html_bytes)) * 100.0

    evidence: Dict[str, Any] = {
        "html_size_bytes": html_bytes,
        "text_characters": text_length,
        "estimated_tokens": metrics["estimated_tokens"],
        "content_density_pct": round(content_ratio, 2),
        "overhead_pct": round(overhead_ratio, 2),
        "has_h1": metrics["has_h1"],
        "h1_count": metrics["h1_count"],
        "h2_count": metrics["h2_count"],
        "has_semantic_main": metrics["has_semantic_main"],
    }

    # Scoring calculation (Max 100)
    score = 0.0

    # 1. Content Density Ratio (Max 40 pts)
    # > 20% density is exceptional for web; 10-20% is good; 5-10% is fair; < 5% is bloated
    if content_ratio >= 20.0:
        score += 40.0
    elif content_ratio >= 10.0:
        score += 30.0 + ((content_ratio - 10.0) / 10.0) * 10.0
    elif content_ratio >= 4.0:
        score += 15.0 + ((content_ratio - 4.0) / 6.0) * 15.0
    else:
        score += max(0.0, (content_ratio / 4.0) * 15.0)
        recommendations.append("High HTML bloat detected (<4% content density). Provide server-rendered markdown or cleaner DOM for AI agents.")

    # 2. Script/Style Overhead (Max 30 pts)
    # < 50% overhead = 30 pts, 50-80% = 15-30 pts, > 80% = 0-15 pts
    if overhead_ratio <= 40.0:
        score += 30.0
    elif overhead_ratio <= 75.0:
        score += 15.0 + ((75.0 - overhead_ratio) / 35.0) * 15.0
    else:
        score += max(0.0, ((100.0 - overhead_ratio) / 25.0) * 15.0)
        recommendations.append("Excessive inline scripts, styles, or SVGs consuming agent token budget. Defer or externalize assets.")

    # 3. Semantic Hierarchy (Max 30 pts)
    # H1 present (10 pts), Single H1 (5 pts), H2s present (5 pts), Semantic main/article (10 pts)
    if metrics["has_h1"]:
        score += 10.0
        if metrics["h1_count"] == 1:
            score += 5.0
        else:
            recommendations.append(f"Found {metrics['h1_count']} `<h1>` elements. Use a single top-level `<h1>` for unambiguous topic extraction.")
    else:
        recommendations.append("Add a clear `<h1>` heading defining the main topic of the page.")

    if metrics["h2_count"] > 0:
        score += 5.0
    else:
        recommendations.append("Use `<h2>` subheadings to structure content sections clearly.")

    if metrics["has_semantic_main"]:
        score += 10.0
    else:
        recommendations.append("Wrap primary content in semantic `<main>` or `<article>` tags to help agents isolate relevant body text.")

    score = min(100.0, max(0.0, score))

    if score >= 80.0:
        status = ComponentStatus.PASS
        details = f"High token efficiency ({round(content_ratio, 1)}% density, {metrics['estimated_tokens']} estimated tokens) with clean semantic structure."
    elif score >= 50.0:
        status = ComponentStatus.WARN
        details = f"Moderate content density ({round(content_ratio, 1)}% text vs {round(overhead_ratio, 1)}% scripts/styles)."
    else:
        status = ComponentStatus.FAIL
        details = f"Severe DOM overhead. Heavy boilerplate dilutes content and inflates LLM token consumption."

    return ScoreComponent(
        name="token_bloat",
        display_name="Content Token Efficiency",
        score=round(score, 1),
        weight=weight,
        status=status,
        evidence=evidence,
        details=details,
        recommendations=recommendations,
    )
