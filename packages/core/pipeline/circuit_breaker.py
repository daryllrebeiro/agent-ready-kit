"""Per-provider circuit breaker and rate limiting for LLM probing pipeline."""

import time
from enum import Enum
from typing import Any, Callable, Dict, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # Normal healthy operation
    OPEN = "OPEN"          # Provider failing, blocking traffic
    HALF_OPEN = "HALF_OPEN"# Testing canary requests to recover


class CircuitBreaker:
    """Protects probers from provider cascades and rate limit exhaustion."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 4,
        recovery_timeout_seconds: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def can_execute(self) -> bool:
        """Check if request is permitted through the circuit."""
        now = time.time()
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False

        # HALF_OPEN allows test attempts
        return True

    def record_success(self) -> None:
        """Reset failures upon successful response."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Track failure and trip circuit if threshold exceeded."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
