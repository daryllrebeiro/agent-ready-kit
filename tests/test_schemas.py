"""Unit tests for Pydantic data contract schemas in packages/core/schemas.py."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from packages.core.schemas import ComponentStatus, ProbeResult, Score, ScoreComponent


def test_score_component_valid():
    comp = ScoreComponent(
        name="llms_txt",
        display_name="llms.txt Compliance",
        score=95.0,
        weight=0.30,
        status=ComponentStatus.PASS,
        evidence={"exists": True},
        details="Compliant llms.txt found",
        recommendations=["Keep up to date"],
    )
    assert comp.name == "llms_txt"
    assert comp.score == 95.0
    assert comp.status == ComponentStatus.PASS


def test_score_component_invalid_score_bounds():
    with pytest.raises(ValidationError):
        ScoreComponent(
            name="test",
            display_name="Test",
            score=105.0,  # Invalid: > 100
            weight=0.5,
            status=ComponentStatus.PASS,
        )

    with pytest.raises(ValidationError):
        ScoreComponent(
            name="test",
            display_name="Test",
            score=-5.0,  # Invalid: < 0
            weight=0.5,
            status=ComponentStatus.FAIL,
        )


def test_score_roundtrip_serialization():
    comp = ScoreComponent(
        name="structured_data",
        display_name="Structured Data",
        score=85.0,
        weight=0.30,
        status=ComponentStatus.PASS,
        evidence={"json_ld_count": 2},
        details="Found 2 schemas",
        recommendations=[],
    )
    score = Score(
        url="https://example.com",
        version="score_v0.1",
        timestamp=datetime.now(timezone.utc),
        overall_score=85.0,
        grade="A",
        components=[comp],
        summary="High readiness",
        recommendations=[],
    )

    json_data = score.model_dump_json()
    reconstructed = Score.model_validate_json(json_data)

    assert reconstructed.url == score.url
    assert reconstructed.overall_score == score.overall_score
    assert reconstructed.grade == "A"
    assert len(reconstructed.components) == 1
    assert reconstructed.components[0].name == "structured_data"


def test_probe_result_schema():
    probe = ProbeResult(
        provider="perplexity",
        prompt="best agent ready tools",
        raw_response="According to https://agentready.dev, this tool scores readiness.",
        cited_domains=["agentready.dev"],
        extracted_urls=["https://agentready.dev"],
        latency_ms=450.5,
        metadata={"model": "sonar-medium"},
    )
    assert probe.provider == "perplexity"
    assert "agentready.dev" in probe.cited_domains
    assert probe.latency_ms == 450.5
