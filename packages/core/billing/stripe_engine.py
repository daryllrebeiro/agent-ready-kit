"""Stripe Usage-Metered Billing Engine & Idempotent Webhook Handler.

Calculates billable volume across tracked domains, probe frequency, and multilingual multipliers.
Handles Stripe subscription lifecycle with idempotent event verification.
"""

import hmac
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple


TIER_LIMITS = {
    "free": {
        "price_usd": 0,
        "max_domains": 5,
        "monthly_probe_budget": 100,
        "features": ["basic_scoring", "single_language"],
    },
    "growth": {
        "price_usd": 99,
        "max_domains": 25,
        "monthly_probe_budget": 2000,
        "features": ["basic_scoring", "persona_simulations", "competitor_benchmarks", "multilingual_5x"],
    },
    "enterprise": {
        "price_usd": 499,
        "max_domains": 100,
        "monthly_probe_budget": 15000,
        "features": ["all_features", "edge_proxy_cdn", "dedicated_sla", "unlimited_languages"],
    },
}


class StripeBillingEngine:
    """Manages subscription state, usage calculation, and idempotent webhook processing."""

    def __init__(self, webhook_secret: Optional[str] = None):
        self.webhook_secret = webhook_secret or "whsec_test_secret"
        # Idempotency set tracking processed Stripe event IDs
        self._processed_events: Set[str] = set()
        # Tenant subscriptions store: tenant_id -> subscription dict
        self._subscriptions: Dict[str, Dict[str, Any]] = {}

    def calculate_estimated_monthly_units(
        self,
        domain_count: int,
        probes_per_domain_per_month: int = 30,
        languages_count: int = 1,
        include_personas: bool = True,
    ) -> Dict[str, Any]:
        """Calculates expected probe units and recommended subscription tier."""
        persona_multiplier = 4 if include_personas else 1
        total_monthly_probes = domain_count * probes_per_domain_per_month * languages_count * persona_multiplier

        recommended_tier = "free"
        if domain_count > 25 or total_monthly_probes > 2000:
            recommended_tier = "enterprise"
        elif domain_count > 5 or total_monthly_probes > 100:
            recommended_tier = "growth"

        return {
            "domain_count": domain_count,
            "languages_count": languages_count,
            "total_monthly_probes": total_monthly_probes,
            "recommended_tier": recommended_tier,
            "tier_price_usd": TIER_LIMITS[recommended_tier]["price_usd"],
        }

    def verify_webhook_signature(self, payload: str, signature_header: str) -> bool:
        """Validates Stripe HMAC signature header (t=timestamp,v1=sig)."""
        if not signature_header:
            return False
        try:
            items = dict(item.split("=", 1) for item in signature_header.split(","))
            timestamp = items.get("t")
            received_sig = items.get("v1")
            if not timestamp or not received_sig:
                return False

            signed_payload = f"{timestamp}.{payload}"
            computed_sig = hmac.new(
                self.webhook_secret.encode("utf-8"),
                signed_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(computed_sig, received_sig)
        except Exception:
            return False

    def handle_webhook_event(self, event_json: str, signature_header: Optional[str] = None) -> Tuple[bool, str]:
        """Processes a Stripe event idempotently."""
        try:
            event = json.loads(event_json)
        except Exception:
            return False, "Invalid JSON payload"

        event_id = event.get("id")
        event_type = event.get("type")

        if not event_id or not event_type:
            return False, "Missing event id or type"

        # Idempotency check
        if event_id in self._processed_events:
            return True, f"Event {event_id} already processed (idempotent ignore)"

        data_obj = event.get("data", {}).get("object", {})
        tenant_id = data_obj.get("metadata", {}).get("tenant_id") or data_obj.get("customer") or "org_unknown"

        # Dispatch event
        if event_type == "customer.subscription.created":
            tier = data_obj.get("metadata", {}).get("tier", "growth")
            self._subscriptions[tenant_id] = {
                "status": "active",
                "tier": tier,
                "subscription_id": data_obj.get("id"),
                "max_domains": TIER_LIMITS.get(tier, {}).get("max_domains", 5),
                "monthly_probe_budget": TIER_LIMITS.get(tier, {}).get("monthly_probe_budget", 100),
                "updated_at": time.time(),
            }
        elif event_type == "customer.subscription.updated":
            if tenant_id in self._subscriptions:
                status = data_obj.get("status", "active")
                self._subscriptions[tenant_id]["status"] = status
                self._subscriptions[tenant_id]["updated_at"] = time.time()
        elif event_type == "customer.subscription.deleted":
            if tenant_id in self._subscriptions:
                self._subscriptions[tenant_id]["status"] = "canceled"
                self._subscriptions[tenant_id]["updated_at"] = time.time()
        elif event_type == "invoice.payment_failed":
            if tenant_id in self._subscriptions:
                self._subscriptions[tenant_id]["status"] = "past_due"
                self._subscriptions[tenant_id]["updated_at"] = time.time()
        elif event_type == "invoice.payment_succeeded":
            if tenant_id in self._subscriptions and self._subscriptions[tenant_id]["status"] == "past_due":
                self._subscriptions[tenant_id]["status"] = "active"
                self._subscriptions[tenant_id]["updated_at"] = time.time()

        self._processed_events.add(event_id)
        return True, f"Processed {event_type} for tenant {tenant_id}"

    def get_subscription(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        return self._subscriptions.get(tenant_id)
