"""Unit tests for executive health report generator."""

from packages.core.reports.health_report import ExecutiveHealthReportGenerator


def test_executive_health_report_generation():
    gen = ExecutiveHealthReportGenerator()
    report = gen.generate_report("https://example.com")

    assert "# 📊 Executive AI Agent Health Report" in report
    assert "Core Readiness Components" in report
    assert "Autonomous Agent Persona Simulations" in report
    assert "Turnkey Remediation Commands" in report
    assert "agentready fix" in report
