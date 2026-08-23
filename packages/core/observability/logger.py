"""Structured JSON Logging & Trace Context Engine for AgentReady."""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable for holding active trace and tenant information
current_trace_id: ContextVar[Optional[str]] = ContextVar("current_trace_id", default=None)
current_tenant_id: ContextVar[Optional[str]] = ContextVar("current_tenant_id", default=None)


class StructuredJsonFormatter(logging.Formatter):
    """Outputs standardized single-line JSON log entries."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": current_trace_id.get() or getattr(record, "trace_id", None) or str(uuid.uuid4())[:8],
            "tenant_id": current_tenant_id.get() or getattr(record, "tenant_id", None) or "system",
        }

        # Include custom metadata if attached
        if hasattr(record, "metadata") and isinstance(record.metadata, dict):
            log_obj["metadata"] = record.metadata

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


class TraceContext:
    """Context manager for tracing operations with duration recording."""

    def __init__(self, trace_id: Optional[str] = None, tenant_id: Optional[str] = None):
        self.trace_id = trace_id or f"tr_{uuid.uuid4().hex[:12]}"
        self.tenant_id = tenant_id or "system"
        self._token_trace = None
        self._token_tenant = None
        self.start_time = 0.0

    def __enter__(self):
        self._token_trace = current_trace_id.set(self.trace_id)
        self._token_tenant = current_tenant_id.set(self.tenant_id)
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token_trace:
            current_trace_id.reset(self._token_trace)
        if self._token_tenant:
            current_tenant_id.reset(self._token_tenant)

    @property
    def elapsed_ms(self) -> float:
        return round((time.time() - self.start_time) * 1000.0, 2)


def get_structured_logger(name: str = "agentready") -> logging.Logger:
    """Returns a configured structured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)

    return logger
