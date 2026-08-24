"""Phase 14 UX & Error Humanization Tests."""

import pytest
from packages.core.errors.humanized import HumanizedError


def test_humanized_budget_exceeded_error():
    """Verifies that budget exceeded error translates to a user-friendly payload with upgrade action."""
    err = HumanizedError.from_budget_exceeded(tenant_id="tenant_acme_growth", limit=500, current=500)
    data = err.to_dict()

    assert data["error_code"] == "BUDGET_LIMIT_REACHED"
    assert data["title"] == "Monthly Probe Budget Reached"
    assert "utilized all 500 included probe credits" in data["explanation"]
    assert len(data["remediation_steps"]) == 3
    assert data["action_label"] == "Upgrade Plan"
    assert "https://app.agentready.dev/billing/upgrade?tenant_id=tenant_acme_growth" in data["action_url"]
    assert data["support_code"].startswith("ERR-")
    assert err.status_code == 402


def test_humanized_invalid_domain_error():
    """Verifies that domain resolution failure produces clear guidance rather than socket errors."""
    err = HumanizedError.from_invalid_domain(raw_url="bad://internal-service")
    data = err.to_dict()

    assert data["error_code"] == "INVALID_DOMAIN_TARGET"
    assert "Unable to Reach Target Website" in data["title"]
    assert "https://docs.agentready.dev/troubleshooting/domain-access" in data["action_url"]
    assert err.status_code == 400


def test_humanized_provider_timeout_error():
    """Verifies that upstream AI timeouts explain DLQ background retry and link to status page."""
    err = HumanizedError.from_provider_timeout(provider="openai")
    data = err.to_dict()

    assert data["error_code"] == "UPSTREAM_PROVIDER_TIMEOUT"
    assert "Openai Service Temporarily Slow" in data["title"]
    assert "https://status.agentready.dev" in data["action_url"]
    assert err.status_code == 504
