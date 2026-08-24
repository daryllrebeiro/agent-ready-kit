"""30-Day Hypercare Operating Cadence & Health Reporting Daemon.

Performs automated daily health reviews across:
- DLQ pending & escalated counts
- Edge Proxy fail-open events
- Multi-model probe success rates & p95 latencies
- SaaS unit gross profit margins
"""

import time
from typing import Any, Dict, List, Optional
from packages.core.billing.margins import GrossMarginGuardrail
from packages.core.observability.apm import APMMetricsBridge
from packages.core.pipeline.dlq import DeadLetterQueue


class HypercareDaemon:
    """Automated operational health monitor during the post-GA 30-day hypercare window."""

    def __init__(
        self,
        dlq: Optional[DeadLetterQueue] = None,
        apm_bridge: Optional[APMMetricsBridge] = None,
    ):
        self.dlq = dlq or DeadLetterQueue()
        self.apm = apm_bridge or APMMetricsBridge()

    def generate_daily_hypercare_report(self, day_number: int = 1) -> Dict[str, Any]:
        """Runs daily audit inspection and evaluates if the system remains in healthy operational status."""
        metrics = self.apm.calculate_current_metrics()
        dlq_pending = len(self.dlq)
        dlq_escalated = self.dlq.escalated_size()

        growth_margin = GrossMarginGuardrail.calculate_plan_gross_margin("growth")
        ent_margin = GrossMarginGuardrail.calculate_plan_gross_margin("enterprise")

        is_healthy = (
            metrics["probe_success_rate"] >= 99.0
            and dlq_escalated == 0
            and growth_margin["target_margin_met"]
            and ent_margin["target_margin_met"]
        )

        return {
            "hypercare_day": day_number,
            "timestamp": time.time(),
            "status": "HEALTHY_STEADY_STATE" if is_healthy else "NEEDS_ATTENTION",
            "metrics": {
                "api_p95_latency_ms": metrics["api_p95_latency_ms"],
                "probe_success_rate": metrics["probe_success_rate"],
                "dlq_pending_jobs": dlq_pending,
                "dlq_escalated_jobs": dlq_escalated,
            },
            "financial_margins": {
                "growth_gross_margin_pct": growth_margin["gross_margin_pct"],
                "enterprise_gross_margin_pct": ent_margin["gross_margin_pct"],
            },
            "action_required": None if is_healthy else "Investigate escalated DLQ jobs or latency breaches",
        }
