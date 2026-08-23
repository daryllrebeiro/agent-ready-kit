"""Multilingual and internationalization (i18n) agent readiness evaluation."""

from typing import Any, Dict, List
from bs4 import BeautifulSoup
from packages.core.checks.structured_data import extract_json_ld
from packages.core.schemas import ComponentStatus, ScoreComponent


def check_multilingual(
    html: str,
    weight: float = 0.15,
) -> ScoreComponent:
    """Evaluate multi-language hreflang alternates, inLanguage Schema, and localized agent discovery."""
    recommendations: List[str] = []
    evidence: Dict[str, Any] = {
        "html_lang": None,
        "hreflang_tags": [],
        "in_language_declarations": [],
        "has_x_default": False,
    }

    if not html or not html.strip():
        return ScoreComponent(
            name="multilingual_readiness",
            display_name="Multilingual & International Agent Readiness",
            score=0.0,
            weight=weight,
            status=ComponentStatus.FAIL,
            evidence=evidence,
            details="Empty document provided.",
            recommendations=["Declare HTML lang attribute and hreflang alternate language tags."],
        )

    soup = BeautifulSoup(html, "html.parser")
    json_ld = extract_json_ld(soup)

    # 1. HTML lang attribute
    html_tag = soup.find("html")
    html_lang = html_tag.get("lang") if html_tag else None
    evidence["html_lang"] = html_lang

    # 2. Hreflang alternates
    hreflangs = []
    has_x_default = False
    for link in soup.find_all("link", rel="alternate"):
        hl = link.get("hreflang")
        if hl:
            hreflangs.append(hl.lower())
            if hl.lower() == "x-default":
                has_x_default = True

    evidence["hreflang_tags"] = hreflangs
    evidence["has_x_default"] = has_x_default

    # 3. Schema.org inLanguage
    in_langs = []
    for b in json_ld:
        if "inLanguage" in b:
            val = b["inLanguage"]
            if isinstance(val, str):
                in_langs.append(val)
            elif isinstance(val, list):
                in_langs.extend([str(v) for v in val])

    evidence["in_language_declarations"] = in_langs

    # Scoring calculation
    score = 0.0

    # Base lang tag (30 pts)
    if html_lang:
        score += 30.0
    else:
        recommendations.append("Set `<html lang=\"...\">` with an IETF BCP 47 language code (e.g. `en`, `es`, `ja`).")

    # Multi-language alternates (40 pts)
    if len(hreflangs) >= 2:
        score += 40.0
    elif len(hreflangs) == 1:
        score += 20.0
    else:
        score += 15.0  # Single language site baseline

    # inLanguage Schema (30 pts)
    if len(in_langs) > 0:
        score += 30.0
    else:
        score += 15.0  # Basic presence

    score = min(100.0, max(0.0, score))

    if score >= 80.0:
        status = ComponentStatus.PASS
        details = f"Excellent internationalization: HTML lang='{html_lang}', {len(hreflangs)} hreflang alternates declared."
    elif score >= 50.0:
        status = ComponentStatus.WARN
        details = f"Basic language tag '{html_lang}' present, but missing structured multi-language alternates."
    else:
        status = ComponentStatus.FAIL
        details = "Missing language declarations. International AI agents cannot localize content accurately."

    return ScoreComponent(
        name="multilingual_readiness",
        display_name="Multilingual & International Agent Readiness",
        score=round(score, 1),
        weight=weight,
        status=status,
        evidence=evidence,
        details=details,
        recommendations=recommendations,
    )
