"""High-throughput concurrent batch domain crawler."""

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from packages.core.schemas import Score
from packages.core.scorer import Scorer


class BatchCrawler:
    """Scans and evaluates hundreds of domains in parallel."""

    def __init__(self, concurrency: int = 5):
        self.concurrency = concurrency
        self.scorer = Scorer()

    def scan_urls(self, urls: List[str]) -> List[Score]:
        """Concurrently scan a list of URLs."""
        results: List[Score] = []
        clean_urls = [u.strip() for u in urls if u.strip() and not u.strip().startswith("#")]

        def _scan(u: str) -> Optional[Score]:
            try:
                target = u if "://" in u else f"https://{u}"
                return self.scorer.score_url(target)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            future_to_url = {executor.submit(_scan, u): u for u in clean_urls}
            for future in as_completed(future_to_url):
                res = future.result()
                if res:
                    results.append(res)

        return sorted(results, key=lambda s: s.overall_score, reverse=True)

    def export_to_csv(self, scores: List[Score], output_filepath: str) -> None:
        """Export scanned scores to CSV format."""
        with open(output_filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "URL",
                "Overall Score",
                "Grade",
                "Version",
                "llms_txt",
                "structured_data",
                "token_bloat",
                "bot_permissions",
                "Summary",
            ])
            for s in scores:
                comp_scores = {c.name: f"{c.score:.1f}" for c in s.components}
                writer.writerow([
                    s.url,
                    f"{s.overall_score:.1f}",
                    s.grade,
                    s.version,
                    comp_scores.get("llms_txt", "N/A"),
                    comp_scores.get("structured_data", "N/A"),
                    comp_scores.get("token_bloat", "N/A"),
                    comp_scores.get("bot_permissions", "N/A"),
                    s.summary,
                ])
