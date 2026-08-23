"""Core scoring orchestrator and aggregation engine."""

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
import requests

from packages.core.checks.bot_permissions import check_bot_permissions
from packages.core.checks.llms_txt import check_llms_txt
from packages.core.checks.structured_data import check_structured_data
from packages.core.checks.token_bloat import check_token_bloat
from packages.core.config import ALGORITHM_VERSION, DEFAULT_WEIGHTS, get_grade
from packages.core.schemas import Score, ScoreComponent


class Scorer:
    """Orchestrates agent-readiness evaluations for a target URL."""

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        timeout_seconds: float = 10.0,
        user_agent: str = "AgentReadyScorer/0.1.0 (+https://github.com/daryllrebeiro/agent-ready-kit)",
    ):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def normalize_url(self, raw_url: str) -> str:
        """Ensure standard URL schema."""
        url = raw_url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        return url

    def fetch_resource(self, url: str) -> Dict[str, Any]:
        """Fetch an HTTP resource safely."""
        headers = {"User-Agent": self.user_agent}
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout_seconds, allow_redirects=True)
            return {
                "success": resp.status_code < 400,
                "status_code": resp.status_code,
                "content": resp.text,
                "headers": dict(resp.headers),
                "url": str(resp.url),
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "content": "",
                "headers": {},
                "url": url,
                "error": str(e),
            }

    def score_payloads(
        self,
        url: str,
        html_content: str,
        robots_txt: Optional[str] = None,
        llms_txt: Optional[str] = None,
        llms_full_txt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Score:
        """Score static/fixture payloads without making live network calls."""
        normalized_url = self.normalize_url(url)

        # 1. Run LLMs.txt check
        comp_llms = check_llms_txt(
            content=llms_txt,
            full_content=llms_full_txt,
            exists=bool(llms_txt),
            full_exists=bool(llms_full_txt),
            weight=self.weights.get("llms_txt", 0.30),
        )

        # 2. Run Structured Data check
        comp_struct = check_structured_data(
            html=html_content,
            weight=self.weights.get("structured_data", 0.30),
        )

        # 3. Run Token Bloat check
        comp_bloat = check_token_bloat(
            html=html_content,
            weight=self.weights.get("token_bloat", 0.20),
        )

        # 4. Run Bot Permissions check
        comp_bots = check_bot_permissions(
            robots_content=robots_txt,
            exists=bool(robots_txt),
            weight=self.weights.get("bot_permissions", 0.20),
        )

        components: List[ScoreComponent] = [comp_llms, comp_struct, comp_bloat, comp_bots]

        return self.aggregate(normalized_url, components, metadata=metadata)

    def score_url(self, target_url: str) -> Score:
        """Scan a live target URL and compile its agent readiness score."""
        url = self.normalize_url(target_url)
        parsed = urlparse(url)
        root_url = f"{parsed.scheme}://{parsed.netloc}"

        # Fetch main page HTML
        html_resp = self.fetch_resource(url)
        html_content = html_resp["content"]

        # Fetch robots.txt
        robots_url = urljoin(root_url, "/robots.txt")
        robots_resp = self.fetch_resource(robots_url)

        # Fetch llms.txt
        llms_url = urljoin(root_url, "/llms.txt")
        llms_resp = self.fetch_resource(llms_url)

        # Fetch llms-full.txt
        llms_full_url = urljoin(root_url, "/llms-full.txt")
        llms_full_resp = self.fetch_resource(llms_full_url)

        # Run checks with status codes
        comp_llms = check_llms_txt(
            content=llms_resp["content"] if llms_resp["success"] else None,
            full_content=llms_full_resp["content"] if llms_full_resp["success"] else None,
            exists=llms_resp["success"],
            full_exists=llms_full_resp["success"],
            status_code=llms_resp["status_code"],
            weight=self.weights.get("llms_txt", 0.30),
        )

        comp_struct = check_structured_data(
            html=html_content,
            weight=self.weights.get("structured_data", 0.30),
        )

        comp_bloat = check_token_bloat(
            html=html_content,
            weight=self.weights.get("token_bloat", 0.20),
        )

        comp_bots = check_bot_permissions(
            robots_content=robots_resp["content"] if robots_resp["success"] else None,
            exists=robots_resp["success"],
            status_code=robots_resp["status_code"],
            weight=self.weights.get("bot_permissions", 0.20),
        )

        components = [comp_llms, comp_struct, comp_bloat, comp_bots]

        metadata = {
            "fetch_status": {
                "html": html_resp["status_code"],
                "robots_txt": robots_resp["status_code"],
                "llms_txt": llms_resp["status_code"],
                "llms_full_txt": llms_full_resp["status_code"],
            },
            "final_url": html_resp.get("url", url),
        }

        return self.aggregate(url, components, metadata=metadata)

    def aggregate(
        self,
        url: str,
        components: List[ScoreComponent],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Score:
        """Compute composite score, letter grade, and prioritized recommendations."""
        total_weight = sum(c.weight for c in components) or 1.0
        weighted_sum = sum(c.score * c.weight for c in components)
        overall_score = round(weighted_sum / total_weight, 1)

        grade = get_grade(overall_score)

        # Collect unique recommendations in order of component severity (FAIL first, then WARN)
        recs: List[str] = []
        # Sort components by lowest score to prioritize fixes
        sorted_components = sorted(components, key=lambda c: (c.score, -c.weight))
        for comp in sorted_components:
            for rec in comp.recommendations:
                if rec not in recs:
                    recs.append(rec)

        # Generate summary
        if overall_score >= 85.0:
            summary = "Excellent Agent Readiness. Your site is well-structured for discovery and extraction by AI agents."
        elif overall_score >= 70.0:
            summary = "Good Agent Readiness. Minor optimizations will improve citations and reduce crawler token consumption."
        elif overall_score >= 50.0:
            summary = "Moderate Agent Readiness. AI crawlers can access some data, but agent discoverability is limited."
        else:
            summary = "Low Agent Readiness. Your content risks being skipped, misunderstood, or omitted in AI search citations."

        return Score(
            url=url,
            version=ALGORITHM_VERSION,
            timestamp=datetime.now(timezone.utc),
            overall_score=overall_score,
            grade=grade,
            components=components,
            summary=summary,
            recommendations=recs,
            metadata=metadata or {},
        )


def main() -> None:
    """CLI runner entrypoint for standalone core execution."""
    parser = argparse.ArgumentParser(description="AgentReady Core Scoring Engine")
    parser.add_argument("url", help="Target URL to analyze")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    scorer = Scorer()
    score = scorer.score_url(args.url)

    if args.json:
        print(score.model_dump_json(indent=2))
    else:
        print(f"Target: {score.url}")
        print(f"Overall Score: {score.overall_score}/100 (Grade: {score.grade})")
        print(f"Summary: {score.summary}")
        print("\nComponent Breakdown:")
        for c in score.components:
            print(f"  - [{c.status.value}] {c.display_name}: {c.score:.1f}/100 (Weight: {c.weight})")
            print(f"    {c.details}")
        if score.recommendations:
            print("\nKey Recommendations:")
            for i, rec in enumerate(score.recommendations[:5], 1):
                print(f"  {i}. {rec}")


if __name__ == "__main__":
    main()
