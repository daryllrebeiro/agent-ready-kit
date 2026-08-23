"""Unit tests for batch crawler and CSV export."""

import os
from packages.core.crawler.batch import BatchCrawler


def test_batch_crawler_execution(tmp_path):
    crawler = BatchCrawler(concurrency=2)
    urls = ["https://example.com", "https://agentready.dev"]
    scores = crawler.scan_urls(urls)

    assert len(scores) >= 1
    assert scores[0].overall_score >= 0.0

    csv_file = str(tmp_path / "batch_report.csv")
    crawler.export_to_csv(scores, csv_file)

    assert os.path.exists(csv_file)
    with open(csv_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "URL" in content
        assert "Overall Score" in content
