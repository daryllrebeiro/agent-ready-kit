"""Official Python client SDK for AgentReady."""

from typing import Any, Dict, List, Optional
import requests

from packages.core.badges.generator import BadgeGenerator
from packages.core.competitors.benchmark import CompetitorBenchmarkEngine
from packages.core.fixer.engine import FixerEngine
from packages.core.probes.runner import MultiModelProber
from packages.core.schemas import Score
from packages.core.scorer import Scorer


class AgentReadyClient:
    """Synchronous client for interacting with AgentReady locally or via remote API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "http://localhost:3000",
        use_local_engine: bool = True,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.use_local_engine = use_local_engine

        # Local engines
        self._scorer = Scorer() if use_local_engine else None
        self._prober = MultiModelProber() if use_local_engine else None
        self._fixer = FixerEngine() if use_local_engine else None
        self._competitors = CompetitorBenchmarkEngine() if use_local_engine else None

    def scan(self, url: str) -> Score:
        """Scan a URL for AI agent readiness and return a full Score model."""
        if self.use_local_engine and self._scorer:
            return self._scorer.score_url(url)

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = requests.post(f"{self.base_url}/api/scan", json={"url": url}, headers=headers, timeout=15.0)
        resp.raise_for_status()
        return Score.model_validate(resp.json())

    def probe(self, url: str, dry_run: bool = True, max_prompts: int = 3) -> List[Dict[str, Any]]:
        """Probe LLM providers to check live citation behavior."""
        if self.use_local_engine and self._prober:
            from packages.core.probes.extractor import extract_domain_from_url
            domain = extract_domain_from_url(url)
            return self._prober.run_standard_probe_suite(target_domain=domain, max_prompts=max_prompts, dry_run=dry_run)

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = requests.post(f"{self.base_url}/api/probe", json={"url": url, "dry_run": dry_run}, headers=headers, timeout=30.0)
        resp.raise_for_status()
        return resp.json()

    def compare(self, target_url: str, competitor_urls: List[str], dry_run: bool = True) -> Dict[str, Any]:
        """Compare citation share and readiness against competitors."""
        if self.use_local_engine and self._competitors:
            return self._competitors.compare_domains(target_url, competitor_urls, dry_run=dry_run)

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = requests.post(
            f"{self.base_url}/api/compare",
            json={"url": target_url, "competitors": competitor_urls, "dry_run": dry_run},
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    def fix(self, url: str, output_dir: Optional[str] = None) -> Dict[str, str]:
        """Generate drop-in remediation files (llms.txt, robots.txt, schema-ld.json)."""
        fixer = self._fixer or FixerEngine()
        fixes = fixer.generate_all_fixes(url)
        if output_dir:
            fixer.apply_fixes_to_directory(fixes, output_dir)
        return fixes

    def get_badge_svg(self, url_or_score: str | Score, label: str = "agent-ready") -> str:
        """Generate vector SVG badge markup."""
        if isinstance(url_or_score, Score):
            return BadgeGenerator.generate_svg(url_or_score, label=label)
        score = self.scan(url_or_score)
        return BadgeGenerator.generate_svg(score, label=label)
