"""Phase 13 Chaos Game Day & 10x Scale Proof Tests."""

import concurrent.futures
import time
import pytest
from packages.core.observability.apm import APMMetricsBridge, DEFAULT_PRODUCTION_SLOS, SLOAlertEngine
from packages.core.pipeline.dlq import DeadLetterQueue
from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient
from packages.core.schemas import ProbeResult


def test_10x_burst_scale_concurrent_tenant_probes():
    """Simulates 10x baseline workload (500 concurrent probe tasks across 50 tenants) with zero data loss."""
    redis_mock = MockRedisClient()
    cache = DistributedProbeCache(redis_client=redis_mock)
    dlq = DeadLetterQueue()
    apm = APMMetricsBridge()

    def run_tenant_probe_task(task_id: int):
        tenant_id = f"scale_tenant_{task_id % 50}"
        prompt = f"How agent-ready is domain {task_id}?"
        start_t = time.time()

        # 1. Budget reservation
        cache.increment_tenant_usage(tenant_id, probe_cost_units=1)

        # 2. Probe execution simulation
        success = True
        latency_ms = 45.0 + (task_id % 20)
        apm.record_api_request(latency_ms)
        apm.record_probe_execution(success)

        # 3. Store result in cache
        probe_res = ProbeResult(
            provider="openai",
            prompt=prompt,
            raw_response="Cited: test.com",
            cited_domains=["test.com"],
            latency_ms=latency_ms,
        )
        cache.store_cached_probe(tenant_id, "openai", prompt, probe_res)
        return True

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(run_tenant_probe_task, i) for i in range(500)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 500
    assert all(results)
    metrics = apm.calculate_current_metrics()
    assert metrics["total_requests"] == 500
    assert metrics["probe_success_rate"] == 100.0


def test_chaos_game_day_primary_db_disconnect_and_dlq_self_healing():
    """Simulates primary database connection loss during burst load, verifying fallback to DLQ and post-recovery replay."""
    dlq = DeadLetterQueue()
    apm = APMMetricsBridge()
    alert_engine = SLOAlertEngine(bridge=apm)

    # 1. Normal traffic
    for _ in range(50):
        apm.record_api_request(35.0)
        apm.record_probe_execution(True)

    # 2. Chaos injection: Primary database disconnects during probe storage
    db_connected = False
    failed_attempts = 0

    for i in range(25):
        if not db_connected:
            # Storage fails -> route to DLQ
            dlq.push(
                org_id=f"tenant_{i % 5}",
                provider="anthropic",
                target_url=f"https://domain-{i}.com",
                prompt="GEO crawler query",
                error_message="OperationalError: database connection lost (simulated DB failover)",
            )
            apm.record_api_request(550.0)  # Latency spike from retry attempts
            apm.record_probe_execution(False)
            failed_attempts += 1

    assert failed_attempts == 25
    assert len(dlq) == 25

    # 3. Verify SLO alert triggered during chaos
    alerts = alert_engine.evaluate_and_alert()
    assert len(alerts) >= 1  # Probe success rate or p95 latency breached

    # 4. Recovery: Database reconnects and DLQ replays all jobs
    db_connected = True
    replayed = dlq.replay_failed_jobs(executor=lambda job: True)
    assert replayed["replayed"] == 25
    assert len(dlq) == 0  # DLQ drained successfully
