"""Dead-Letter Queue (DLQ) for capturing and retrying failed probe jobs with alert escalation."""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


@dataclass
class FailedJob:
    """Record of a failed pipeline execution."""

    id: str
    org_id: str
    provider: str
    target_url: str
    prompt: str
    error_message: str
    retry_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "QUEUED"  # "QUEUED", "REPLAYING", "RESOLVED", "ESCALATED"


class DeadLetterQueue:
    """In-memory and durable queue capturing failed probes without dropping data."""

    def __init__(self, max_items: int = 1000):
        self.max_items = max_items
        self._queue: List[FailedJob] = []
        self._escalated: List[FailedJob] = []

    def push(
        self,
        org_id: str,
        provider: str,
        target_url: str,
        prompt: str,
        error_message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FailedJob:
        """Enqueue a failed probe execution."""
        job = FailedJob(
            id=str(uuid.uuid4())[:8],
            org_id=org_id,
            provider=provider,
            target_url=target_url,
            prompt=prompt,
            error_message=error_message,
            metadata=metadata or {},
        )
        self._queue.append(job)
        if len(self._queue) > self.max_items:
            self._queue.pop(0)
        return job

    def pop(self) -> Optional[FailedJob]:
        """Retrieve next failed job for re-processing."""
        if self._queue:
            return self._queue.pop(0)
        return None

    def replay_failed_jobs(
        self,
        executor: Callable[[FailedJob], bool],
        max_retries: int = 3,
        escalation_callback: Optional[Callable[[FailedJob], None]] = None,
    ) -> Dict[str, int]:
        """Processes all queued DLQ jobs with retry tracking and escalation."""
        results = {"replayed": 0, "succeeded": 0, "failed": 0, "escalated": 0}
        pending = list(self._queue)
        self._queue.clear()

        for job in pending:
            results["replayed"] += 1
            job.retry_count += 1
            try:
                success = executor(job)
                if success:
                    job.status = "RESOLVED"
                    results["succeeded"] += 1
                else:
                    raise RuntimeError("Executor returned failure")
            except Exception as e:
                job.error_message = str(e)
                if job.retry_count >= max_retries:
                    job.status = "ESCALATED"
                    self._escalated.append(job)
                    results["escalated"] += 1
                    if escalation_callback:
                        escalation_callback(job)
                else:
                    self._queue.append(job)
                    results["failed"] += 1

        return results

    def size(self) -> int:
        return len(self._queue)

    def escalated_size(self) -> int:
        return len(self._escalated)

    def list_jobs(self, org_id: Optional[str] = None) -> List[FailedJob]:
        if org_id:
            return [j for j in self._queue if j.org_id == org_id]
        return list(self._queue)
