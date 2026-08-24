"""Phase 15 GA Rollout & Hypercare Daemon Tests."""

import pytest
from packages.core.rollout.graduated_rollout import GraduatedRolloutController, RolloutStage
from packages.core.rollout.hypercare import HypercareDaemon
from packages.core.pipeline.dlq import DeadLetterQueue
from packages.core.observability.apm import APMMetricsBridge


def test_graduated_rollout_stage_progression_and_canary_gating():
    """Verifies deterministic cohort assignment, canary bypass, and stage promotion to full GA."""
    controller = GraduatedRolloutController(
        initial_stage=RolloutStage.PILOT_10,
        allowed_canary_tenants=["tenant_vip_alpha"],
    )

    # 1. Canary tenant is always eligible in 10% pilot
    assert controller.is_tenant_eligible("tenant_vip_alpha") is True

    # 2. Promote to 50%
    controller.promote_stage(RolloutStage.EXPANDED_50, reason="Week 1 pilot zero DLQ escalations")
    assert controller.stage == RolloutStage.EXPANDED_50

    # 3. Promote to 100% GA
    controller.promote_stage(RolloutStage.GA_100, reason="Week 2 expanded rollout passed all SLOs")
    assert controller.stage == RolloutStage.GA_100
    assert controller.is_tenant_eligible("any_random_tenant_xyz") is True

    # 4. Emergency Rollback
    controller.trigger_emergency_rollback("Upstream critical cascade")
    assert controller.stage == RolloutStage.ROLLED_BACK
    assert controller.is_tenant_eligible("tenant_vip_alpha") is False


def test_30_day_hypercare_daemon_daily_inspection():
    """Verifies that the hypercare daemon accurately aggregates system health and financial margins."""
    dlq = DeadLetterQueue()
    apm = APMMetricsBridge()

    # Record 100 healthy probe operations
    for _ in range(100):
        apm.record_api_request(30.0)
        apm.record_probe_execution(True)

    daemon = HypercareDaemon(dlq=dlq, apm_bridge=apm)
    report = daemon.generate_daily_hypercare_report(day_number=14)

    assert report["hypercare_day"] == 14
    assert report["status"] == "HEALTHY_STEADY_STATE"
    assert report["metrics"]["probe_success_rate"] == 100.0
    assert report["metrics"]["dlq_pending_jobs"] == 0
    assert report["metrics"]["dlq_escalated_jobs"] == 0
    assert report["financial_margins"]["growth_gross_margin_pct"] >= 70.0
    assert report["action_required"] is None
