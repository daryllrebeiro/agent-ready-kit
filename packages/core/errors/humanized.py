"""Humanized Error Presentation & Resolution Guidance for AgentReady.

Transforms raw system exceptions and API rejections into clear, actionable,
user-friendly error states without raw stack traces.
"""

import time
import uuid
from typing import Any, Dict, List, Optional


class HumanizedError:
    """Structured, customer-friendly error payload."""

    def __init__(
        self,
        error_code: str,
        title: str,
        explanation: str,
        remediation_steps: List[str],
        action_url: Optional[str] = None,
        action_label: Optional[str] = None,
        support_code: Optional[str] = None,
        status_code: int = 400,
    ):
        self.error_code = error_code
        self.title = title
        self.explanation = explanation
        self.remediation_steps = remediation_steps
        self.action_url = action_url
        self.action_label = action_label
        self.support_code = support_code or f"ERR-{uuid.uuid4().hex[:8].upper()}"
        self.status_code = status_code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "title": self.title,
            "explanation": self.explanation,
            "remediation_steps": self.remediation_steps,
            "action_url": self.action_url,
            "action_label": self.action_label,
            "support_code": self.support_code,
            "timestamp": time.time(),
        }

    @classmethod
    def from_budget_exceeded(cls, tenant_id: str, limit: int, current: int) -> "HumanizedError":
        return cls(
            error_code="BUDGET_LIMIT_REACHED",
            title="Monthly Probe Budget Reached",
            explanation=f"Your workspace '{tenant_id}' has utilized all {limit} included probe credits for this billing cycle.",
            remediation_steps=[
                "Upgrade to Growth or Enterprise tier for expanded probe credits.",
                "Wait until the first day of next month for your quota to reset.",
                "Purchase an on-demand probe add-on pack in Billing Settings.",
            ],
            action_url=f"https://app.agentready.dev/billing/upgrade?tenant_id={tenant_id}",
            action_label="Upgrade Plan",
            status_code=402,
        )

    @classmethod
    def from_invalid_domain(cls, raw_url: str) -> "HumanizedError":
        return cls(
            error_code="INVALID_DOMAIN_TARGET",
            title="Unable to Reach Target Website",
            explanation=f"We could not resolve '{raw_url}'. The domain may be private, offline, or formatted incorrectly.",
            remediation_steps=[
                "Verify the domain starts with 'https://' or 'http://'.",
                "Ensure the website is publicly accessible on the public Internet.",
                "Check for typos in the domain name.",
            ],
            action_url="https://docs.agentready.dev/troubleshooting/domain-access",
            action_label="View Domain Guide",
            status_code=400,
        )

    @classmethod
    def from_provider_timeout(cls, provider: str) -> "HumanizedError":
        return cls(
            error_code="UPSTREAM_PROVIDER_TIMEOUT",
            title=f"{provider.title()} Service Temporarily Slow",
            explanation=f"The upstream AI provider ({provider.title()}) did not respond within our 15-second safety deadline.",
            remediation_steps=[
                "Your scan request was automatically saved to our retry queue (DLQ).",
                "We will complete your probe evaluation as soon as {provider.title()} recovers.",
                "Check system status at https://status.agentready.dev.",
            ],
            action_url="https://status.agentready.dev",
            action_label="View Live Status",
            status_code=504,
        )

    @classmethod
    def from_unauthorized(cls, tenant_id: Optional[str] = None) -> "HumanizedError":
        return cls(
            error_code="UNAUTHORIZED_ACCESS",
            title="Authentication Required",
            explanation="This action requires a valid API key with appropriate workspace permissions.",
            remediation_steps=[
                "Provide a valid Bearer token in the 'Authorization' header.",
                "Generate a new API key in Workspace Settings -> API Keys.",
                "Check if your API key has been revoked.",
            ],
            action_url="https://app.agentready.dev/settings/keys",
            action_label="Manage API Keys",
            status_code=401,
        )
