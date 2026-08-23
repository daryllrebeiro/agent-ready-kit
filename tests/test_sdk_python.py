"""Unit tests for official Python SDK."""

from packages.sdk_python.agentready.client import AgentReadyClient


def test_python_sdk_local_scan():
    client = AgentReadyClient(use_local_engine=True)
    score = client.scan("https://example.com")
    assert score.url == "https://example.com"
    assert score.overall_score >= 0.0
    assert score.grade in ["A+", "A", "B", "C", "D", "F"]


def test_python_sdk_local_badge():
    client = AgentReadyClient(use_local_engine=True)
    svg = client.get_badge_svg("https://example.com", label="agent-ready")
    assert "<svg" in svg
    assert "agent-ready" in svg


def test_python_sdk_local_fix(tmp_path):
    client = AgentReadyClient(use_local_engine=True)
    out_dir = str(tmp_path / "sdk_fixes")
    fixes = client.fix("https://mysite.com", output_dir=out_dir)
    assert "llms.txt" in fixes
    assert "robots.txt" in fixes
