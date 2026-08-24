"""Enterprise Incident Communication Templates & Customer Advisory Catalog.

Provides pre-composed markdown & HTML advisory templates for operational incidents,
fail-open status updates, and quota alerts.
"""

from typing import Any, Dict


class IncidentTemplateCatalog:
    """Pre-drafted operational advisory templates for on-call & customer support."""

    @staticmethod
    def edge_proxy_failopen_advisory(domain_url: str, duration_minutes: int = 5) -> Dict[str, str]:
        return {
            "incident_type": "EDGE_PROXY_FAIL_OPEN",
            "subject": f"[Advisory] Temporary Edge Proxy Bypass Activated for {domain_url}",
            "slack_message": (
                f":warning: *Edge Proxy Safety Bypass Active*\n"
                f"*Target Domain:* `{domain_url}`\n"
                f"*Status:* Edge proxy automatically failed open to protect origin traffic.\n"
                f"*Action Taken:* All user traffic continues directly to origin with 0 downtime."
            ),
            "customer_email_markdown": (
                f"### Service Update for {domain_url}\n\n"
                f"Our edge proxy monitoring detected elevated latency on upstream routing. "
                f"In accordance with our zero-downtime fail-open guarantee, traffic was automatically bypassed directly to your origin servers for {duration_minutes} minutes.\n\n"
                f"No customer traffic was dropped. Service has returned to normal."
            ),
        }

    @staticmethod
    def upstream_provider_degradation_advisory(provider: str) -> Dict[str, str]:
        return {
            "incident_type": "UPSTREAM_PROVIDER_DEGRADATION",
            "subject": f"[Advisory] Upstream {provider.title()} Latency Elevated",
            "slack_message": (
                f":satellite: *Upstream AI Degradation: {provider.title()}*\n"
                f"Probing requests to {provider.title()} are being buffered in our Dead-Letter Queue (DLQ) for automatic replay."
            ),
            "status_page_body": (
                f"We are observing elevated response latencies from {provider.title()}. "
                f"Active probing jobs will automatically retry as provider capacity normalizes."
            ),
        }
