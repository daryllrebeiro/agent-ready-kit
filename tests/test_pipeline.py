"""Unit tests for pipeline resilience, circuit breakers, DLQ, and quota tracking."""

import time
from packages.core.auth.context import TenantContext
from packages.core.pipeline.circuit_breaker import CircuitBreaker, CircuitState
from packages.core.pipeline.dlq import DeadLetterQueue
from packages.core.pipeline.quotas import QuotaManager


def test_circuit_breaker_trips_and_recovers():
    cb = CircuitBreaker("test-provider", failure_threshold=3, recovery_timeout_seconds=0.1)

    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # Record 3 failures
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False

    # Wait for recovery timeout
    time.sleep(0.15)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Success restores to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_dead_letter_queue():
    dlq = DeadLetterQueue(max_items=10)
    job = dlq.push(
        org_id="org_1",
        provider="openai",
        target_url="https://example.com",
        prompt="test prompt",
        error_message="HTTP 500 Provider Down",
    )

    assert dlq.size() == 1
    assert job.error_message == "HTTP 500 Provider Down"

    popped = dlq.pop()
    assert popped.id == job.id
    assert dlq.size() == 0


def test_quota_manager():
    qm = QuotaManager()
    ctx = TenantContext(org_id="org_test", user_id="u1", monthly_probe_quota=5)

    assert qm.check_and_increment(ctx, requested_probes=3) is True
    assert qm.get_usage("org_test") == 3

    assert qm.check_and_increment(ctx, requested_probes=2) is True
    assert qm.get_usage("org_test") == 5

    # Should fail: quota exceeded (5 + 1 > 5)
    assert qm.check_and_increment(ctx, requested_probes=1) is False
