"""Unit tests for synthetic multi-tenant load benchmark harness."""

from packages.core.benchmarks.load_test import LoadTestHarness


def test_load_test_harness_execution():
    harness = LoadTestHarness(tenant_count=10, operations_per_tenant=10)
    result = harness.run_multi_tenant_benchmark()

    assert result["tenants_tested"] == 10
    assert result["total_operations"] == 100
    assert result["throughput_ops_per_sec"] > 50.0
    assert result["errors_encountered"] == 0
    assert result["average_latency_ms"] >= 0.0
