"""Edge Proxy Pilot Monitor and Third-Party Synthetic Witness Harness.

Tracks live pilot customer observation metrics, synthetic external latency
measurements (p50/p95/p99), fail-open trigger audits, and runtime kill-switch exercises.
"""

import math
import time
from typing import Any, Dict, List, Optional
from packages.edge_proxy.simulator import EdgeProxySimulator


class EdgePilotMonitor:
    """Monitors live edge proxy pilot rollout with independent synthetic verification."""

    def __init__(self, proxy_simulator: Optional[EdgeProxySimulator] = None):
        self.proxy = proxy_simulator or EdgeProxySimulator(shadow_mode=False)
        self.synthetic_probes: List[Dict[str, Any]] = []
        self.fail_open_events: List[Dict[str, Any]] = []

    def record_probe(
        self,
        target_url: str,
        user_agent: str,
        origin_latency_ms: float,
        proxy_latency_ms: float,
        status_code: int,
        intercepted: bool,
        fail_open_triggered: bool = False,
        fail_open_reason: Optional[str] = None,
    ):
        """Records an external synthetic witness probe measurement."""
        added_latency_ms = max(0.0, proxy_latency_ms - origin_latency_ms)
        record = {
            "timestamp": time.time(),
            "target_url": target_url,
            "user_agent": user_agent,
            "origin_latency_ms": origin_latency_ms,
            "proxy_latency_ms": proxy_latency_ms,
            "added_latency_ms": added_latency_ms,
            "status_code": status_code,
            "intercepted": intercepted,
            "fail_open_triggered": fail_open_triggered,
            "fail_open_reason": fail_open_reason,
        }
        self.synthetic_probes.append(record)
        if fail_open_triggered:
            self.fail_open_events.append(record)

    def calculate_percentiles(self) -> Dict[str, float]:
        """Calculates p50, p95, and p99 added latency percentiles across recorded probes."""
        if not self.synthetic_probes:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "total_probes": 0}

        latencies = sorted([p["added_latency_ms"] for p in self.synthetic_probes])
        n = len(latencies)

        def percentile(p: float) -> float:
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return latencies[int(k)]
            d0 = latencies[int(f)] * (c - k)
            d1 = latencies[int(c)] * (k - f)
            return round(d0 + d1, 2)

        return {
            "p50": percentile(0.50),
            "p95": percentile(0.95),
            "p99": percentile(0.99),
            "total_probes": n,
            "fail_open_count": len(self.fail_open_events),
        }

    def exercise_planned_kill_switch(self, target_domain: str) -> Dict[str, Any]:
        """Exercises planned runtime kill switch and asserts immediate fallback to origin."""
        start_t = time.time()
        # Activate kill switch
        self.proxy.kill_switch = True
        
        origin_fetch = lambda u, h: {"status": 200, "body": "Origin Content", "headers": {}}
        # Test routing request with AI bot User-Agent
        req_headers = {"User-Agent": "GPTBot/1.0"}
        res = self.proxy.handle_request(f"https://{target_domain}/docs", req_headers, origin_fetch=origin_fetch)
        elapsed_ms = (time.time() - start_t) * 1000.0

        return {
            "kill_switch_activated": True,
            "reverted_to_origin": res.get("headers", {}).get("X-AgentReady-Bypass") == "true",
            "response_status": res.get("status", 200),
            "switch_latency_ms": round(elapsed_ms, 2),
        }
