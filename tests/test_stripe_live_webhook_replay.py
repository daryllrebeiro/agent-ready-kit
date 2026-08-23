"""Live Stripe Webhook Replay, Lifecycle Transitions, and Out-of-Order Delivery Tests."""

import json
import time
import pytest
from packages.core.billing.stripe_engine import StripeBillingEngine


def test_stripe_full_subscription_lifecycle_transitions():
    billing = StripeBillingEngine(webhook_secret="whsec_live_replay_secret")
    tenant_id = "tenant_enterprise_corp"

    # 1. Signup / Subscription Created (Growth Tier)
    evt_create = {
        "id": "evt_replay_001_create",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_ent_001",
                "customer": "cus_ent_001",
                "status": "active",
                "metadata": {"tenant_id": tenant_id, "tier": "growth"},
            }
        },
    }
    ok, _ = billing.handle_webhook_event(json.dumps(evt_create))
    assert ok is True
    assert billing.get_subscription(tenant_id)["tier"] == "growth"
    assert billing.get_subscription(tenant_id)["status"] == "active"

    # 2. Upgrade to Enterprise
    evt_upgrade = {
        "id": "evt_replay_002_upgrade",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_ent_001",
                "customer": "cus_ent_001",
                "status": "active",
                "metadata": {"tenant_id": tenant_id, "tier": "enterprise"},
            }
        },
    }
    ok, _ = billing.handle_webhook_event(json.dumps(evt_upgrade))
    assert ok is True
    assert billing.get_subscription(tenant_id)["status"] == "active"

    # 3. Payment Failed (Past Due)
    evt_failed = {
        "id": "evt_replay_003_payment_failed",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "id": "in_ent_001",
                "customer": "cus_ent_001",
                "metadata": {"tenant_id": tenant_id},
            }
        },
    }
    ok, _ = billing.handle_webhook_event(json.dumps(evt_failed))
    assert ok is True
    assert billing.get_subscription(tenant_id)["status"] == "past_due"

    # 4. Payment Recovery (Invoice Payment Succeeded)
    evt_success = {
        "id": "evt_replay_004_payment_succeeded",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "id": "in_ent_002",
                "customer": "cus_ent_001",
                "metadata": {"tenant_id": tenant_id},
            }
        },
    }
    ok, _ = billing.handle_webhook_event(json.dumps(evt_success))
    assert ok is True
    assert billing.get_subscription(tenant_id)["status"] == "active"

    # 5. Cancellation (Subscription Deleted)
    evt_cancel = {
        "id": "evt_replay_005_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_ent_001",
                "customer": "cus_ent_001",
                "metadata": {"tenant_id": tenant_id},
            }
        },
    }
    ok, _ = billing.handle_webhook_event(json.dumps(evt_cancel))
    assert ok is True
    assert billing.get_subscription(tenant_id)["status"] == "canceled"


def test_stripe_duplicate_event_redelivery_idempotency():
    billing = StripeBillingEngine(webhook_secret="whsec_live_replay_secret")
    tenant_id = "tenant_idempotent_test"

    event_payload = {
        "id": "evt_duplicate_replay_999",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_idempotent_999",
                "customer": "cus_idempotent_999",
                "status": "active",
                "metadata": {"tenant_id": tenant_id, "tier": "growth"},
            }
        },
    }

    # Initial delivery
    ok_1, msg_1 = billing.handle_webhook_event(json.dumps(event_payload))
    assert ok_1 is True

    # Replay identical event (Stripe retry behavior on network timeout)
    ok_2, msg_2 = billing.handle_webhook_event(json.dumps(event_payload))
    assert ok_2 is True
    assert "already processed" in msg_2.lower()


def test_stripe_out_of_order_event_delivery():
    billing = StripeBillingEngine(webhook_secret="whsec_live_replay_secret")
    tenant_id = "tenant_ooo_test"

    # Out-of-order: invoice.payment_failed arrives before customer.subscription.created
    evt_failed = {
        "id": "evt_ooo_failed_001",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "id": "in_ooo_001",
                "customer": "cus_ooo_001",
                "metadata": {"tenant_id": tenant_id},
            }
        },
    }
    # Should not crash; gracefully returns ok
    ok, _ = billing.handle_webhook_event(json.dumps(evt_failed))
    assert ok is True
