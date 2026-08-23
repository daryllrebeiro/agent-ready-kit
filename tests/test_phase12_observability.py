"""Phase 12 Observability Tests: OpenTelemetry OTLP Exporter and Kubernetes /readyz Eviction."""

import pytest
from packages.core.observability.apm import OpenTelemetryTraceExporterBridge
from packages.core.observability.health import HealthChecker
from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient


def test_opentelemetry_otlp_trace_batch_export():
    """Verifies that spans are properly structured into standard OpenTelemetry OTLP format."""
    exporter = OpenTelemetryTraceExporterBridge(service_name="agentready-production-api")

    # Record 2 spans
    exporter.record_span(
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        span_id="00f067aa0ba902b7",
        name="probe.execute.openai",
        tenant_id="tenant_otlp_enterprise",
        duration_ms=45.2,
        attributes={"http.status_code": 200, "probe.provider": "openai"},
    )
    exporter.record_span(
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        span_id="5fb397be34d23b0f",
        name="storage.save.score",
        tenant_id="tenant_otlp_enterprise",
        duration_ms=8.5,
    )

    payload = exporter.export_otlp_payload()
    assert "resourceSpans" in payload
    resource_spans = payload["resourceSpans"]
    assert len(resource_spans) == 1
    spans = resource_spans[0]["scopeSpans"][0]["spans"]
    assert len(spans) == 2
    assert spans[0]["name"] == "probe.execute.openai"
    assert spans[0]["traceId"] == "4bf92f3577b34da6a3ce929d0e0e4736"

    # Buffer should be cleared after export
    empty_payload = exporter.export_otlp_payload()
    assert len(empty_payload["resourceSpans"][0]["scopeSpans"][0]["spans"]) == 0


def test_kubernetes_readiness_probe_dependency_eviction():
    """Verifies that dependency outage on /readyz returns degraded, removing pod from traffic."""
    # 1. Healthy dependencies
    healthy_checker = HealthChecker()
    ready_status = healthy_checker.check_readiness()
    assert ready_status["status"] == "healthy"
    assert ready_status["ready"] is True
    assert ready_status["checks"]["database"]["status"] == "UP"
    assert ready_status["checks"]["redis"]["status"] == "UP"

    # 2. Redis outage (simulated primary Redis partition)
    broken_redis = MockRedisClient(simulate_network_partition=True)
    broken_cache = DistributedProbeCache(redis_client=broken_redis, fail_open_on_error=False)
    broken_checker = HealthChecker(cache=broken_cache)
    unready_status = broken_checker.check_readiness()
    assert unready_status["status"] == "degraded"
    assert unready_status["ready"] is False
    assert unready_status["checks"]["redis"]["status"] == "DOWN"
