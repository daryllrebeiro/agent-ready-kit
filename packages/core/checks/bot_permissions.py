"""Check robots.txt permissions and crawling directives for AI agent bots."""

from typing import Any, Dict, List, Optional
from packages.core.config import TARGET_AI_BOTS
from packages.core.schemas import ComponentStatus, ScoreComponent


def parse_robots_txt(content: str) -> Dict[str, Any]:
    """Parse robots.txt into structured user-agent rules and directives."""
    lines = content.splitlines()
    rules: Dict[str, Dict[str, Any]] = {}
    current_agents: List[str] = []
    sitemaps: List[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if ":" not in line:
            continue

        key, val = line.split(":", 1)
        key = key.strip().lower()
        val = val.strip()

        if key == "user-agent":
            agent = val.lower()
            if agent not in rules:
                rules[agent] = {"disallows": [], "allows": [], "crawl_delay": None}
            current_agents.append(agent)
        elif key == "disallow":
            for agent in current_agents:
                rules[agent]["disallows"].append(val)
        elif key == "allow":
            for agent in current_agents:
                rules[agent]["allows"].append(val)
        elif key == "crawl-delay":
            try:
                delay = float(val)
                for agent in current_agents:
                    rules[agent]["crawl_delay"] = delay
            except ValueError:
                pass
        elif key == "sitemap":
            sitemaps.append(val)
        else:
            # Other directive or reset
            pass

    return {"rules": rules, "sitemaps": sitemaps}


def evaluate_bot_permission(agent_name: str, parsed_robots: Dict[str, Any]) -> Dict[str, Any]:
    """Check whether a specific bot is allowed, partially allowed, or blocked."""
    rules = parsed_robots.get("rules", {})
    name_lower = agent_name.lower()

    # Direct match takes precedence over wildcard
    bot_rule = rules.get(name_lower)
    matched_by = "specific"

    if not bot_rule:
        bot_rule = rules.get("*", {"disallows": [], "allows": [], "crawl_delay": None})
        matched_by = "wildcard (*)"

    disallows = bot_rule.get("disallows", [])
    allows = bot_rule.get("allows", [])

    is_blocked_root = "/" in disallows and "/" not in allows
    is_fully_allowed = len(disallows) == 0 or (len(disallows) == 1 and disallows[0] == "")

    if is_blocked_root:
        status = "BLOCKED"
    elif is_fully_allowed:
        status = "ALLOWED"
    else:
        status = "PARTIAL"

    return {
        "bot": agent_name,
        "status": status,
        "matched_by": matched_by,
        "disallows": disallows,
        "allows": allows,
        "crawl_delay": bot_rule.get("crawl_delay"),
    }


def check_bot_permissions(
    robots_content: Optional[str] = None,
    exists: bool = False,
    status_code: Optional[int] = None,
    weight: float = 0.20,
) -> ScoreComponent:
    """Evaluate AI crawler and agent permissions in robots.txt."""
    recommendations: List[str] = []
    evidence: Dict[str, Any] = {
        "exists": exists or bool(robots_content),
        "status_code": status_code,
        "sitemaps": [],
        "bot_status": {},
    }

    # If no robots.txt exists, default is open/allowed (standard web behavior)
    if not evidence["exists"] or not robots_content or not robots_content.strip():
        # Open by default, but missing sitemap reference
        return ScoreComponent(
            name="bot_permissions",
            display_name="AI Bot & Crawler Permissions",
            score=70.0,
            weight=weight,
            status=ComponentStatus.WARN,
            evidence=evidence,
            details="No robots.txt detected. Crawlers default to unrestricted access, but sitemap discovery is missing.",
            recommendations=[
                "Create a `robots.txt` file at your domain root.",
                "Explicitly declare permissions for `GPTBot`, `ClaudeBot`, `PerplexityBot`, and `Google-Extended`.",
                "Include a `Sitemap: https://yourdomain.com/sitemap.xml` directive.",
            ],
        )

    parsed = parse_robots_txt(robots_content)
    evidence["sitemaps"] = parsed["sitemaps"]

    bot_evaluations: Dict[str, Dict[str, Any]] = {}
    allowed_count = 0
    blocked_count = 0
    partial_count = 0

    for bot_info in TARGET_AI_BOTS:
        b_name = bot_info["name"]
        eval_result = evaluate_bot_permission(b_name, parsed)
        bot_evaluations[b_name] = eval_result
        if eval_result["status"] == "ALLOWED":
            allowed_count += 1
        elif eval_result["status"] == "BLOCKED":
            blocked_count += 1
        else:
            partial_count += 1

    evidence["bot_status"] = bot_evaluations
    evidence["allowed_count"] = allowed_count
    evidence["blocked_count"] = blocked_count
    evidence["total_bots_evaluated"] = len(TARGET_AI_BOTS)

    # Scoring breakdown (Max 100)
    score = 0.0

    # 1. AI bot accessibility (Max 75 pts)
    # Give full points for ALLOWED, partial for PARTIAL, 0 for BLOCKED
    bot_score_ratio = (allowed_count + (partial_count * 0.5)) / len(TARGET_AI_BOTS)
    score += bot_score_ratio * 75.0

    # 2. Sitemap declaration in robots.txt (Max 25 pts)
    if parsed["sitemaps"]:
        score += 25.0
    else:
        recommendations.append("Add a `Sitemap: <url>` reference in `robots.txt` to accelerate agent crawling.")

    # Specific bot recommendations
    for b_name in ["PerplexityBot", "ChatGPT-User", "Claude-Web"]:
        if b_name in bot_evaluations and bot_evaluations[b_name]["status"] == "BLOCKED":
            recommendations.append(f"Unblock `{b_name}` to allow real-time AI citations and direct user search queries.")

    for b_name in ["GPTBot", "ClaudeBot", "Google-Extended"]:
        if b_name in bot_evaluations and bot_evaluations[b_name]["status"] == "BLOCKED":
            recommendations.append(f"`{b_name}` is blocked. If you want your content indexed for future foundation model training, consider allowing it.")

    score = min(100.0, max(0.0, score))

    if score >= 80.0:
        status = ComponentStatus.PASS
        details = f"{allowed_count}/{len(TARGET_AI_BOTS)} AI bots allowed with sitemap defined."
    elif score >= 45.0:
        status = ComponentStatus.WARN
        details = f"Partial bot access ({allowed_count} allowed, {blocked_count} blocked)."
    else:
        status = ComponentStatus.FAIL
        details = f"Major AI bots blocked ({blocked_count} blocked). Website will be invisible to AI search agents."

    return ScoreComponent(
        name="bot_permissions",
        display_name="AI Bot & Crawler Permissions",
        score=round(score, 1),
        weight=weight,
        status=status,
        evidence=evidence,
        details=details,
        recommendations=recommendations,
    )
