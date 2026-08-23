"""Advanced semantic entity graph and authority linkage analysis."""

import json
from typing import Any, Dict, List, Set
from bs4 import BeautifulSoup
from packages.core.checks.structured_data import extract_json_ld
from packages.core.schemas import ComponentStatus, ScoreComponent

AUTHORITATIVE_SAME_AS_DOMAINS = {
    "wikidata.org",
    "wikipedia.org",
    "github.com",
    "crunchbase.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
}


def analyze_entity_graph(json_ld_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze interconnectedness, sameAs links, and entity depth in JSON-LD."""
    entities: List[str] = []
    same_as_links: List[str] = []
    connected_edges = 0

    for block in json_ld_blocks:
        if not isinstance(block, dict) or "_error" in block:
            continue

        etype = block.get("@type", "Thing")
        if isinstance(etype, list):
            entities.extend([str(t) for t in etype])
        else:
            entities.append(str(etype))

        # Check sameAs links
        same_as = block.get("sameAs")
        if isinstance(same_as, str):
            same_as_links.append(same_as)
        elif isinstance(same_as, list):
            same_as_links.extend([str(s) for s in same_as])

        # Check relationship edges
        for rel_key in ["isPartOf", "publisher", "author", "creator", "mainEntity", "about", "hasPart", "provider"]:
            if rel_key in block:
                connected_edges += 1

    # Extract verified authority domains
    verified_authorities: Set[str] = set()
    for link in same_as_links:
        for auth_domain in AUTHORITATIVE_SAME_AS_DOMAINS:
            if auth_domain in link.lower():
                verified_authorities.add(auth_domain)

    return {
        "entity_count": len(entities),
        "entities": entities,
        "same_as_count": len(same_as_links),
        "same_as_links": same_as_links,
        "verified_authority_links": sorted(list(verified_authorities)),
        "connected_edges": connected_edges,
    }


def check_semantic_graph(
    html: str,
    weight: float = 0.15,
) -> ScoreComponent:
    """Evaluate semantic entity graph depth and authority grounding."""
    recommendations: List[str] = []
    evidence: Dict[str, Any] = {
        "entity_count": 0,
        "same_as_count": 0,
        "verified_authorities": [],
        "connected_edges": 0,
    }

    if not html or not html.strip():
        return ScoreComponent(
            name="semantic_graph",
            display_name="Semantic Entity Graph & Authority",
            score=0.0,
            weight=weight,
            status=ComponentStatus.FAIL,
            evidence=evidence,
            details="Empty document provided.",
            recommendations=["Add semantic JSON-LD entity graph definitions."],
        )

    soup = BeautifulSoup(html, "html.parser")
    json_ld_blocks = extract_json_ld(soup)
    graph_metrics = analyze_entity_graph(json_ld_blocks)

    evidence.update({
        "entity_count": graph_metrics["entity_count"],
        "same_as_count": graph_metrics["same_as_count"],
        "verified_authorities": graph_metrics["verified_authority_links"],
        "connected_edges": graph_metrics["connected_edges"],
    })

    score = 0.0

    # 1. Entity presence (Max 30 pts)
    if graph_metrics["entity_count"] > 0:
        score += min(30.0, 15.0 + (graph_metrics["entity_count"] - 1) * 5.0)
    else:
        recommendations.append("Define Schema.org entities (`Organization`, `WebSite`, `Product`) to anchor your brand in AI knowledge graphs.")

    # 2. sameAs Authority Links (Max 40 pts)
    auth_count = len(graph_metrics["verified_authority_links"])
    if auth_count > 0:
        score += min(40.0, 10.0 + auth_count * 10.0)
    else:
        recommendations.append("Add `sameAs` entity links to Wikidata, Wikipedia, GitHub, or Crunchbase to verify brand authority for LLM citations.")

    # 3. Interconnected Graph Edges (Max 30 pts)
    edges = graph_metrics["connected_edges"]
    if edges > 0:
        score += min(30.0, 10.0 + edges * 10.0)
    else:
        recommendations.append("Link nested entities with `publisher`, `author`, or `isPartOf` relationship predicates.")

    score = min(100.0, max(0.0, score))

    if score >= 75.0:
        status = ComponentStatus.PASS
        details = f"Strong semantic graph with {graph_metrics['entity_count']} entities, {auth_count} verified authority links, and {edges} relationship edges."
    elif score >= 40.0:
        status = ComponentStatus.WARN
        details = f"Basic entity definitions present but lacks authoritative `sameAs` links or relationship edges."
    else:
        status = ComponentStatus.FAIL
        details = "No connected semantic entity graph found. AI models cannot anchor brand entities in knowledge bases."

    return ScoreComponent(
        name="semantic_graph",
        display_name="Semantic Entity Graph & Authority",
        score=round(score, 1),
        weight=weight,
        status=status,
        evidence=evidence,
        details=details,
        recommendations=recommendations,
    )
