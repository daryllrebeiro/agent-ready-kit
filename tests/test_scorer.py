"""Unit tests for scorer orchestration and rank ordering."""

import os
from packages.core.scorer import Scorer

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def read_fixture(subpath: str) -> str:
    with open(os.path.join(FIXTURES_DIR, subpath), "r", encoding="utf-8") as f:
        return f.read()


def test_scorer_good_vs_bad_rank_order():
    scorer = Scorer()

    # Score known-good site
    good_html = read_fixture("good_site/index.html")
    good_robots = read_fixture("good_site/robots.txt")
    good_llms = read_fixture("good_site/llms.txt")

    good_score = scorer.score_payloads(
        url="https://agentready.dev",
        html_content=good_html,
        robots_txt=good_robots,
        llms_txt=good_llms,
    )

    # Score known-bad site
    bad_html = read_fixture("bad_site/index.html")
    bad_robots = read_fixture("bad_site/robots.txt")

    bad_score = scorer.score_payloads(
        url="https://bad-example.com",
        html_content=bad_html,
        robots_txt=bad_robots,
        llms_txt=None,
    )

    # Assert clear rank separation
    assert good_score.overall_score > bad_score.overall_score
    assert good_score.overall_score >= 80.0
    assert bad_score.overall_score <= 35.0
    assert good_score.grade in ["A+", "A", "B"]
    assert bad_score.grade in ["D", "F"]


def test_scorer_weights_customization():
    custom_weights = {
        "llms_txt": 0.70,
        "structured_data": 0.10,
        "token_bloat": 0.10,
        "bot_permissions": 0.10,
    }
    scorer = Scorer(weights=custom_weights)

    # Site with perfect llms.txt but nothing else
    score = scorer.score_payloads(
        url="https://docs-only.com",
        html_content="<html><body>Hello</body></html>",
        llms_txt=read_fixture("good_site/llms.txt"),
    )

    # With 70% weight on llms_txt, overall score should be significantly lifted
    assert score.overall_score > 60.0
