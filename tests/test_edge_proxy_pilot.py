"""Tests for edge proxy live pilot monitoring and synthetic witness measurements."""

import pytest
from packages.edge_proxy.simulator import EdgeProxySimulator
from packages.edge_proxy.pilot import EdgePilotMonitor


def test_edge_pilot_monitor_synthetic_latency_distribution():
    monitor = EdgePilotMonitor()

    # Record 100 synthetic witness probes with varying added latencies (1.0ms to 10.0ms)
    for i in range(100):
        added = (i % 10) + 1.0
        monitor.record_probe(
            target_url="https://pilot-customer.com/docs",
            user_agent="GPTBot/1.0",
            origin_latency_ms=45.0,
            proxy_latency_ms=45.0 + added,
            status_code=200,
            intercepted=True,
        )

    stats = monitor.calculate_percentiles()
    assert stats["total_probes"] == 100
    assert stats["p50"] <= 6.0
    assert stats["p95"] <= 10.0
    assert stats["p99"] <= 10.0
    assert stats["fail_open_count"] == 0


def test_edge_pilot_monitor_planned_kill_switch_reversion():
    proxy = EdgeProxySimulator(shadow_mode=False, kill_switch=False, fallback_llms_txt="# AgentReady")
    monitor = EdgePilotMonitor(proxy_simulator=proxy)

    origin = lambda u, h: {"status": 404, "body": "404 Not Found", "headers": {}}
    # Initial request with GPTBot for /llms.txt should be intercepted and served by proxy
    initial_res = proxy.handle_request("https://pilot-customer.com/llms.txt", {"User-Agent": "GPTBot/1.0"}, origin_fetch=origin)
    assert initial_res["headers"].get("X-Served-By") == "AgentReady-Edge-Proxy"

    # Exercise planned kill switch
    switch_res = monitor.exercise_planned_kill_switch("pilot-customer.com")
    assert switch_res["kill_switch_activated"] is True
    assert switch_res["reverted_to_origin"] is True
    assert switch_res["switch_latency_ms"] < 25.0  # Must switch instantly under 25ms
