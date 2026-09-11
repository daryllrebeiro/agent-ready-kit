"""Core scoring orchestrator and aggregation engine."""

import argparse
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from packages.core.checks.bot_permissions import check_bot_permissions
from packages.core.checks.llms_txt import check_llms_txt
from packages.core.checks.structured_data import check_structured_data
from packages.core.checks.token_bloat import check_token_bloat
from packages.core.config import ALGORITHM_VERSION, DEFAULT_WEIGHTS, get_grade
from packages.core.schemas import Score, ScoreComponent
from packages.core.version import AGENTREADY_VERSION


class UnsafeTargetError(Exception):
    """Raised when a fetch target fails SSRF validation."""


class Scorer:
    """Orchestrates agent-readiness evaluations for a target URL."""

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        timeout_seconds: float = 10.0,
        user_agent: str | None = None,
    ):
        if user_agent is None:
            user_agent = (
                f"AgentReadyScorer/{AGENTREADY_VERSION} (+https://github.com/daryllrebeiro/agent-ready-kit)"
            )
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def normalize_url(self, raw_url: str) -> str:
        """Ensure standard URL schema."""
        url = raw_url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        return url

    def resolve_and_validate(self, url: str) -> None:
        """Raise UnsafeTargetError if URL is not a safe public target.

        Validates the literal URL plus DNS-resolved IPs (blocks
        hostname-of-internal-IP tricks). Redirect targets are re-validated
        in fetch_resource via a response hook.

        Explicit opt-out: AGENTREADY_ALLOW_PRIVATE_HOSTS="127.0.0.1,::1"
        permits loopback targets for local development and entrypoint smoke
        tests. Each use is logged as a warning; never set in production.
        """
        import logging
        import os

        from packages.core.security.scanner import SecurityScanner

        hostname = urlparse(url).hostname or ""
        allowed = {
            h.strip().lower()
            for h in os.environ.get("AGENTREADY_ALLOW_PRIVATE_HOSTS", "").split(",")
            if h.strip()
        }
        if hostname.lower() in allowed:
            logging.getLogger("agentready.scorer").warning(
                "SSRF guard bypassed for allowlisted host=%s via AGENTREADY_ALLOW_PRIVATE_HOSTS",
                hostname,
            )
            return

        ok, reason = SecurityScanner.is_safe_public_url(url)
        if not ok:
            raise UnsafeTargetError(reason)
        try:
            import ipaddress
            import socket

            for info in socket.getaddrinfo(hostname, None):
                ip = ipaddress.ip_address(info[4][0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    raise UnsafeTargetError(f"DNS resolves to private address {ip}")
        except UnsafeTargetError:
            raise
        except Exception:
            # DNS failure -> let requests raise normally (no SSRF bypass:
            # literal-IP and hostname blocklists already enforced above).
            pass

    def fetch_resource(self, url: str) -> dict[str, Any]:
        """Fetch an HTTP resource safely (SSRF-guarded)."""
        try:
            self.resolve_and_validate(url)
        except UnsafeTargetError as e:
            return {
                "success": False,
                "status_code": None,
                "content": "",
                "headers": {},
                "url": url,
                "error": f"unsafe-target: {e}",
            }
        headers = {"User-Agent": self.user_agent}

        def _guard_redirect(response, *args, **kwargs):
            try:
                self.resolve_and_validate(response.url)
            except UnsafeTargetError:
                # Abort redirect chain by raising inside hook; caught below.
                raise UnsafeTargetError(f"redirect to unsafe target blocked: {response.url}")

        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=self.timeout_seconds,
                allow_redirects=True,
                hooks={"response": _guard_redirect},
            )
            return {
                "success": resp.status_code < 400,
                "status_code": resp.status_code,
                "content": resp.text,
                "headers": dict(resp.headers),
                "url": str(resp.url),
            }
        except UnsafeTargetError as e:
            return {
                "success": False,
                "status_code": None,
                "content": "",
                "headers": {},
                "url": url,
                "error": f"unsafe-target: {e}",
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
        robots_txt: str | None = None,
        llms_txt: str | None = None,
        llms_full_txt: str | None = None,
        metadata: dict[str, Any] | None = None,
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

        components: list[ScoreComponent] = [comp_llms, comp_struct, comp_bloat, comp_bots]

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
        components: list[ScoreComponent],
        metadata: dict[str, Any] | None = None,
    ) -> Score:
        """Compute composite score, letter grade, and prioritized recommendations."""
        total_weight = sum(c.weight for c in components) or 1.0
        weighted_sum = sum(c.score * c.weight for c in components)
        overall_score = round(weighted_sum / total_weight, 1)

        grade = get_grade(overall_score)

        # Collect unique recommendations in order of component severity (FAIL first, then WARN)
        recs: list[str] = []
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

        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("weights", {c.name: c.weight for c in components})
        merged_metadata.setdefault("algorithm_version", ALGORITHM_VERSION)

        return Score(
            url=url,
            version=ALGORITHM_VERSION,
            timestamp=datetime.now(UTC),
            overall_score=overall_score,
            grade=grade,
            components=components,
            summary=summary,
            recommendations=recs,
            metadata=merged_metadata,
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
