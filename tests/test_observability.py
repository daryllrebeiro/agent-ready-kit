"""Unit tests for Observability, Health Probes, and DLQ Escalation."""

import json
import logging
from unittest.mock import MagicMock
from packages.core.observability.health import HealthChecker
from packages.core.observability.logger import (
    StructuredJsonFormatter,
    TraceContext,
    get_structured_logger,
)
from packages.core.pipeline.dlq import DeadLetterQueue, FailedJob


def test_structured_json_logger_and_trace_context():
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Executing synthetic probe run",
        args=(),
        exc_info=None,
    )

    with TraceContext(trace_id="tr_custom_12345", tenant_id="tenant_acme") as ctx:
        formatted = formatter.format(record)
        log_json = json.loads(formatted)

        assert log_json["message"] == "Executing synthetic probe run"
        assert log_json["level"] == "INFO"
        assert log_json["trace_id"] == "tr_custom_12345"
        assert log_json["tenant_id"] == "tenant_acme"
        assert ctx.elapsed_ms >= 0


def test_health_checker_liveness_and_readiness():
    checker = HealthChecker()

    # 1. Liveness check
    live_res = checker.check_liveness()
    assert live_res["status"] == "alive"
    assert live_res["service"] == "agentready-core"

    # 2. Readiness check
    ready_res = checker.check_readiness()
    assert ready_res["ready"] is True
    assert "database" in ready_res["checks"]
    assert ready_res["checks"]["database"]["status"] == "UP"
    assert "redis" in ready_res["checks"]


def test_dlq_replay_and_escalation():
    dlq = DeadLetterQueue()
    escalated_jobs = []

    def on_escalate(job: FailedJob):
        escalated_jobs.append(job)

    # 1. Push a failed job
    dlq.push(
        org_id="org_1",
        provider="openai",
        target_url="https://example.com",
        prompt="Search prompt",
        error_message="503 Service Unavailable",
    )
    assert dlq.size() == 1

    # 2. Replay with failing executor (max_retries = 2)
    # Attempt 1: retry_count = 1 -> re-queued
    res1 = dlq.replay_failed_jobs(lambda job: False, max_retries=2, escalation_callback=on_escalate)
    assert res1["replayed"] == 1
    assert res1["failed"] == 1
    assert dlq.size() == 1
    assert len(escalated_jobs) == 0

    # Attempt 2: retry_count = 2 -> escalated
    res2 = dlq.replay_failed_jobs(lambda job: False, max_retries=2, escalation_callback=on_escalate)
    assert res2["replayed"] == 1
    assert res2["escalated"] == 1
    assert dlq.size() == 0
    assert len(escalated_jobs) == 1
    assert escalated_jobs[0].status == "ESCALATED"
