"""Phase 14 Onboarding Wizard, Incident Templates, and Gross Margin Tests."""

import pytest
from packages.core.onboarding.wizard import OnboardingWizard
from packages.core.support.incident_templates import IncidentTemplateCatalog
from packages.core.billing.margins import GrossMarginGuardrail


def test_rapid_onboarding_wizard_flow():
    """Verifies end-to-end self-service onboarding completes all 3 steps with zero friction."""
    wizard = OnboardingWizard()
    result = wizard.execute_onboarding_flow(
        tenant_id="tenant_new_pilot",
        target_domain="https://example.com",
        competitor_domains=["https://competitor.com"],
    )

    assert result["tenant_id"] == "tenant_new_pilot"
    assert result["onboarding_status"] == "SUCCESS_FULLY_ONBOARDED"
    assert len(result["steps"]) == 3
    assert result["steps"][0]["name"] == "Site Readiness Assessment"
    assert result["steps"][1]["name"] == "Persona Simulation (3 Archetypes)"
    assert result["steps"][2]["name"] == "Competitive Benchmark & Badge Issuance"
    assert result["elapsed_seconds"] < 600.0  # Must be well under 10 minutes


def test_incident_communication_templates():
    """Verifies pre-composed operational incident advisories format correctly."""
    advisory = IncidentTemplateCatalog.edge_proxy_failopen_advisory("https://acme.com", duration_minutes=5)
    assert advisory["incident_type"] == "EDGE_PROXY_FAIL_OPEN"
    assert "https://acme.com" in advisory["subject"]
    assert "bypassed directly to your origin" in advisory["customer_email_markdown"]

    upstream_adv = IncidentTemplateCatalog.upstream_provider_degradation_advisory("openai")
    assert upstream_adv["incident_type"] == "UPSTREAM_PROVIDER_DEGRADATION"
    assert "Dead-Letter Queue (DLQ)" in upstream_adv["slack_message"]


def test_unit_economics_gross_margin_guardrails():
    """Verifies that Growth and Enterprise tiers achieve >= 70% gross margins at full utilization."""
    growth_margin = GrossMarginGuardrail.calculate_plan_gross_margin("growth")
    assert growth_margin["gross_margin_pct"] >= 70.0, f"Expected Growth margin >= 70%, got {growth_margin['gross_margin_pct']}%"
    assert growth_margin["target_margin_met"] is True

    ent_margin = GrossMarginGuardrail.calculate_plan_gross_margin("enterprise")
    assert ent_margin["gross_margin_pct"] >= 70.0, f"Expected Enterprise margin >= 70%, got {ent_margin['gross_margin_pct']}%"
    assert ent_margin["target_margin_met"] is True
