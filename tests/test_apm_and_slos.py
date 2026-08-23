"""Tests for APM metrics bridge, SLO alerting engine, and incident tabletop rehearsals."""

import pytest
from packages.core.observability.apm import (
    APMMetricsBridge,
    SLOAlertEngine,
    IncidentTabletopSimulator,
)


def test_apm_metrics_bridge_and_slo_alerting_breach():
    bridge = APMMetricsBridge()

    # Record API requests within normal range (< 500ms)
    for _ in range(95):
        bridge.record_api_request(120.0)
    # Inject latency spike for remaining 5 requests
    for _ in range(5):
        bridge.record_api_request(850.0)

    # 100 probe executions with 2 failures (98.0% success rate, breaching 99.9% SLO)
    for _ in range(98):
        bridge.record_probe_execution(True)
    for _ in range(2):
        bridge.record_probe_execution(False)

    metrics = bridge.calculate_current_metrics()
    assert metrics["api_p95_latency_ms"] >= 500.0
    assert metrics["probe_success_rate"] == 98.0

    # Evaluate SLO alerts
    dispatched = []
    engine = SLOAlertEngine(bridge=bridge, alert_dispatcher=lambda a: dispatched.append(a))
    breaches = engine.evaluate_and_alert()

    assert len(breaches) >= 2
    assert len(dispatched) == len(breaches)
    slo_names = [b["slo_name"] for b in breaches]
    assert "api_p95_latency_ms" in slo_names
    assert "probe_success_rate" in slo_names


def test_incident_tabletop_rehearsal_drill():
    drill_result = IncidentTabletopSimulator.run_edge_proxy_failclosed_drill(
        on_call_engineer="alice@engineering.agentready.dev"
    )
    assert drill_result["rehearsal_status"] == "COMPLETED_SUCCESSFULLY"
    assert drill_result["on_call_engineer"] == "alice@engineering.agentready.dev"
    assert drill_result["kill_switch_executed"] is True
    assert drill_result["time_to_mitigate_seconds"] < 5.0
