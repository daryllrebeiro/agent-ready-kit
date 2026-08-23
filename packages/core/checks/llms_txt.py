"""Check for /llms.txt and /llms-full.txt standard compliance."""

import re
from typing import Any, Dict, List, Optional
from packages.core.schemas import ComponentStatus, ScoreComponent


def parse_llms_txt_content(content: str) -> Dict[str, Any]:
    """Parse and validate llms.txt markdown content against spec."""
    lines = content.strip().splitlines()
    has_h1 = False
    h1_title = ""
    has_blockquote = False
    blockquote_text = ""
    sections: List[str] = []
    links: List[Dict[str, str]] = []

    # Markdown link pattern: - [Title](url): optional summary
    link_pattern = re.compile(r"^\s*-\s*\[([^\]]+)\]\(([^)]+)\)(?:\s*:\s*(.*))?")

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not has_h1:
            has_h1 = True
            h1_title = stripped[2:].strip()
        elif stripped.startswith(">") and not has_blockquote:
            has_blockquote = True
            blockquote_text = stripped[1:].strip()
        elif stripped.startswith("## "):
            sections.append(stripped[3:].strip())
        else:
            match = link_pattern.match(stripped)
            if match:
                links.append({
                    "title": match.group(1).strip(),
                    "url": match.group(2).strip(),
                    "description": (match.group(3) or "").strip(),
                })

    return {
        "has_h1": has_h1,
        "h1_title": h1_title,
        "has_blockquote": has_blockquote,
        "blockquote_summary": blockquote_text,
        "sections": sections,
        "link_count": len(links),
        "links": links[:10],  # preview
    }


def check_llms_txt(
    content: Optional[str] = None,
    full_content: Optional[str] = None,
    exists: bool = False,
    full_exists: bool = False,
    status_code: Optional[int] = None,
    weight: float = 0.30,
) -> ScoreComponent:
    """Evaluate /llms.txt compliance."""
    evidence: Dict[str, Any] = {
        "exists": exists or bool(content),
        "full_exists": full_exists or bool(full_content),
        "status_code": status_code,
    }
    recommendations: List[str] = []

    if not evidence["exists"] or not content or not content.strip():
        return ScoreComponent(
            name="llms_txt",
            display_name="llms.txt Spec Compliance",
            score=0.0,
            weight=weight,
            status=ComponentStatus.FAIL,
            evidence=evidence,
            details="No /llms.txt file detected. AI agents cannot quickly discover curated site context.",
            recommendations=[
                "Create an /llms.txt file at your domain root (run `agentready generate` to bootstrap).",
                "Include a clear H1 site title and a blockquote summary explaining what your service does.",
                "List essential markdown documentation links for agent ingestion.",
            ],
        )

    parsed = parse_llms_txt_content(content)
    evidence.update(parsed)

    score = 40.0  # File exists and is non-empty

    if parsed["has_h1"] and parsed["h1_title"]:
        score += 15.0
    else:
        recommendations.append("Add an H1 project/site title at the top of /llms.txt (e.g. `# My Project`).")

    if parsed["has_blockquote"] and parsed["blockquote_summary"]:
        score += 15.0
    else:
        recommendations.append("Add a blockquote summary directly below the H1 (e.g. `> Concise summary of what this site does`).")

    if parsed["link_count"] > 0:
        score += min(20.0, parsed["link_count"] * 5.0)
    else:
        recommendations.append("Add curated markdown links formatted as `- [Title](url): description` under section headings.")

    if evidence["full_exists"]:
        score += 10.0
    else:
        recommendations.append("Provide a comprehensive `/llms-full.txt` file or link for full-context ingestion.")

    score = min(100.0, score)

    if score >= 80.0:
        status = ComponentStatus.PASS
        details = f"Valid /llms.txt found with {parsed['link_count']} curated documentation links."
    elif score >= 50.0:
        status = ComponentStatus.WARN
        details = f"/llms.txt found but missing key spec formatting ({len(recommendations)} improvements recommended)."
    else:
        status = ComponentStatus.FAIL
        details = "/llms.txt is present but severely incomplete or non-compliant with standard specifications."

    return ScoreComponent(
        name="llms_txt",
        display_name="llms.txt Spec Compliance",
        score=score,
        weight=weight,
        status=status,
        evidence=evidence,
        details=details,
        recommendations=recommendations,
    )
