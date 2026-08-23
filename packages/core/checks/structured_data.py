"""Check structured data (JSON-LD, OpenGraph, Microdata) on web pages."""

import json
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from packages.core.schemas import ComponentStatus, ScoreComponent

RECOGNIZED_HIGH_VALUE_SCHEMAS = {
    "organization",
    "website",
    "webpage",
    "softwareapplication",
    "product",
    "article",
    "techarticle",
    "blogposting",
    "faqpage",
    "breadcrumblist",
    "corporation",
    "dataset",
    "service",
    "localbusiness",
}


def extract_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract and parse all JSON-LD blocks from HTML."""
    json_ld_blocks: List[Dict[str, Any]] = []
    scripts = soup.find_all("script", type=lambda t: t and "ld+json" in t.lower())
    for script in scripts:
        raw_text = script.string or script.get_text() or ""
        if not raw_text.strip():
            continue
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, list):
                json_ld_blocks.extend(parsed)
            elif isinstance(parsed, dict):
                # Handle @graph patterns
                if "@graph" in parsed and isinstance(parsed["@graph"], list):
                    json_ld_blocks.extend(parsed["@graph"])
                else:
                    json_ld_blocks.append(parsed)
        except Exception:
            # Add note about malformed JSON-LD
            json_ld_blocks.append({"_error": "malformed_json_ld", "_raw": raw_text[:200]})
    return json_ld_blocks


def extract_opengraph_and_meta(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract OpenGraph and core meta tags."""
    meta_tags: Dict[str, str] = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name")
        content = meta.get("content")
        if prop and content:
            meta_tags[prop.lower()] = content.strip()
    return meta_tags


def check_structured_data(
    html: str,
    weight: float = 0.30,
) -> ScoreComponent:
    """Evaluate structured data on the page."""
    recommendations: List[str] = []
    evidence: Dict[str, Any] = {
        "json_ld_count": 0,
        "schema_types": [],
        "opengraph_tags": [],
        "has_canonical": False,
        "has_meta_description": False,
    }

    if not html or not html.strip():
        return ScoreComponent(
            name="structured_data",
            display_name="Structured Data & Semantics",
            score=0.0,
            weight=weight,
            status=ComponentStatus.FAIL,
            evidence=evidence,
            details="Empty HTML content provided. No structured data could be extracted.",
            recommendations=["Provide valid HTML markup with semantic metadata."],
        )

    soup = BeautifulSoup(html, "html.parser")
    json_ld_blocks = extract_json_ld(soup)
    meta_tags = extract_opengraph_and_meta(soup)

    # Canonical link
    canonical_tag = soup.find("link", rel=lambda r: r and "canonical" in r)
    evidence["has_canonical"] = bool(canonical_tag and canonical_tag.get("href"))
    evidence["has_meta_description"] = "description" in meta_tags or "og:description" in meta_tags

    # Entity types found in JSON-LD
    schema_types: List[str] = []
    has_malformed_json = False

    for block in json_ld_blocks:
        if "_error" in block:
            has_malformed_json = True
            continue
        entity_type = block.get("@type")
        if isinstance(entity_type, list):
            schema_types.extend([str(t) for t in entity_type])
        elif entity_type:
            schema_types.append(str(entity_type))

    evidence["json_ld_count"] = len([b for b in json_ld_blocks if "_error" not in b])
    evidence["schema_types"] = schema_types
    evidence["has_malformed_json"] = has_malformed_json

    og_found = [k for k in ["og:title", "og:description", "og:image", "og:url", "og:type"] if k in meta_tags]
    evidence["opengraph_tags"] = og_found

    # Scoring breakdown (Max 100)
    score = 0.0

    # 1. JSON-LD presence and recognized high-value schema (Max 50 pts)
    if evidence["json_ld_count"] > 0:
        score += 25.0
        normalized_types = {t.lower() for t in schema_types}
        high_value_matches = normalized_types.intersection(RECOGNIZED_HIGH_VALUE_SCHEMAS)
        if high_value_matches:
            score += min(25.0, len(high_value_matches) * 12.5)
        else:
            recommendations.append("Add standard Schema.org entity types (e.g. Organization, WebSite, SoftwareApplication, Product, or FAQPage).")
    else:
        recommendations.append("Implement Schema.org JSON-LD structured data in a `<script type=\"application/ld+json\">` block.")

    # 2. OpenGraph / Social Metadata (Max 25 pts)
    og_score = (len(og_found) / 5.0) * 25.0
    score += og_score
    if len(og_found) < 4:
        recommendations.append("Include complete OpenGraph meta tags (`og:title`, `og:description`, `og:image`, `og:url`, `og:type`).")

    # 3. Canonical URL (Max 10 pts)
    if evidence["has_canonical"]:
        score += 10.0
    else:
        recommendations.append("Add a `<link rel=\"canonical\" href=\"...\">` tag to prevent agent citation duplication.")

    # 4. Meta Description (Max 15 pts)
    if evidence["has_meta_description"]:
        score += 15.0
    else:
        recommendations.append("Provide a clear `<meta name=\"description\">` tag summarizing page purpose.")

    # Penalties
    if has_malformed_json:
        score = max(0.0, score - 20.0)
        recommendations.insert(0, "Fix malformed JSON in your `<script type=\"application/ld+json\">` block.")

    score = min(100.0, max(0.0, score))

    if score >= 80.0:
        status = ComponentStatus.PASS
        details = f"Strong structured data detected with {evidence['json_ld_count']} JSON-LD entities and {len(og_found)}/5 OpenGraph tags."
    elif score >= 50.0:
        status = ComponentStatus.WARN
        details = f"Partial structured data present ({len(schema_types)} schema types, {len(og_found)}/5 OpenGraph tags)."
    else:
        status = ComponentStatus.FAIL
        details = "Minimal or missing structured data. AI agents will struggle to extract entity relationships."

    return ScoreComponent(
        name="structured_data",
        display_name="Structured Data & Semantics",
        score=score,
        weight=weight,
        status=status,
        evidence=evidence,
        details=details,
        recommendations=recommendations,
    )
