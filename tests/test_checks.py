"""Unit tests for individual readiness check modules against realistic fixtures."""

import os
from packages.core.checks.bot_permissions import check_bot_permissions, parse_robots_txt
from packages.core.checks.llms_txt import check_llms_txt, parse_llms_txt_content
from packages.core.checks.structured_data import check_structured_data
from packages.core.checks.token_bloat import check_token_bloat
from packages.core.schemas import ComponentStatus

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def read_fixture(subpath: str) -> str:
    with open(os.path.join(FIXTURES_DIR, subpath), "r", encoding="utf-8") as f:
        return f.read()


def test_llms_txt_good_fixture():
    content = read_fixture("good_site/llms.txt")
    comp = check_llms_txt(content=content, exists=True)

    assert comp.name == "llms_txt"
    assert comp.score >= 80.0
    assert comp.status == ComponentStatus.PASS
    assert comp.evidence["has_h1"] is True
    assert comp.evidence["has_blockquote"] is True
    assert comp.evidence["link_count"] >= 3


def test_llms_txt_missing():
    comp = check_llms_txt(content=None, exists=False)
    assert comp.score == 0.0
    assert comp.status == ComponentStatus.FAIL
    assert len(comp.recommendations) > 0


def test_structured_data_good_fixture():
    html = read_fixture("good_site/index.html")
    comp = check_structured_data(html)

    assert comp.score >= 80.0
    assert comp.status == ComponentStatus.PASS
    assert comp.evidence["json_ld_count"] >= 1
    assert "WebSite" in comp.evidence["schema_types"]
    assert "Organization" in comp.evidence["schema_types"]
    assert comp.evidence["has_canonical"] is True


def test_structured_data_bad_fixture():
    html = read_fixture("bad_site/index.html")
    comp = check_structured_data(html)

    assert comp.score < 40.0
    assert comp.status == ComponentStatus.FAIL
    assert comp.evidence["json_ld_count"] == 0


def test_structured_data_malformed_json():
    html = read_fixture("malformed/index.html")
    comp = check_structured_data(html)

    assert comp.evidence["has_malformed_json"] is True
    assert any("malformed JSON" in rec for rec in comp.recommendations)


def test_token_bloat_good_fixture():
    html = read_fixture("good_site/index.html")
    comp = check_token_bloat(html)

    assert comp.score >= 70.0
    assert comp.status == ComponentStatus.PASS or comp.status == ComponentStatus.WARN
    assert comp.evidence["has_h1"] is True
    assert comp.evidence["has_semantic_main"] is True


def test_token_bloat_spa_bloat_fixture():
    html = read_fixture("bloated_spa/index.html")
    comp = check_token_bloat(html)

    assert comp.score < 50.0
    assert comp.status == ComponentStatus.FAIL
    assert comp.evidence["has_h1"] is False


def test_bot_permissions_good_fixture():
    robots = read_fixture("good_site/robots.txt")
    comp = check_bot_permissions(robots_content=robots, exists=True)

    assert comp.score >= 80.0
    assert comp.status == ComponentStatus.PASS
    assert comp.evidence["allowed_count"] >= 4
    assert len(comp.evidence["sitemaps"]) > 0


def test_bot_permissions_blocked_fixture():
    robots = read_fixture("bad_site/robots.txt")
    comp = check_bot_permissions(robots_content=robots, exists=True)

    assert comp.score < 20.0
    assert comp.status == ComponentStatus.FAIL
    assert comp.evidence["blocked_count"] >= 4
