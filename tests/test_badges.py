"""Unit tests for dynamic SVG badge generation."""

from packages.core.badges.generator import BadgeGenerator
from packages.core.schemas import Score


def test_badge_generator_svg_output():
    score = Score(
        url="https://agentready.dev",
        version="score_v0.1",
        overall_score=94.0,
        grade="A+",
        components=[],
        summary="High readiness",
        recommendations=[],
    )

    svg = BadgeGenerator.generate_svg(score, label="agent-ready")
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "agent-ready" in svg
    assert "A+ (94/100)" in svg
    assert "#10B981" in svg  # Emerald green for A+
