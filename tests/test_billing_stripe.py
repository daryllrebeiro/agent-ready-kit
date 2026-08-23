"""Unit tests for Stripe Usage-Metered Billing Engine & Webhooks."""

import hashlib
import hmac
import json
import time
from packages.core.billing.stripe_engine import StripeBillingEngine


def test_billing_units_calculation():
    engine = StripeBillingEngine()

    # 1. Basic calculation
    est_free = engine.calculate_estimated_monthly_units(domain_count=2, probes_per_domain_per_month=10, languages_count=1, include_personas=False)
    assert est_free["recommended_tier"] == "free"
    assert est_free["tier_price_usd"] == 0

    # 2. Multilingual with personas multiplier (4 personas * 5 languages = 20x)
    est_growth = engine.calculate_estimated_monthly_units(domain_count=10, probes_per_domain_per_month=30, languages_count=5, include_personas=True)
    assert est_growth["total_monthly_probes"] == 10 * 30 * 5 * 4  # 6,000 probes
    assert est_growth["recommended_tier"] == "enterprise"
    assert est_growth["tier_price_usd"] == 499


def test_stripe_webhook_signature_verification():
    secret = "whsec_test_123"
    engine = StripeBillingEngine(webhook_secret=secret)
    payload = json.dumps({"id": "evt_test", "type": "ping"})

    ts = str(int(time.time()))
    signed_content = f"{ts}.{payload}"
    sig = hmac.new(secret.encode("utf-8"), signed_content.encode("utf-8"), hashlib.sha256).hexdigest()
    header = f"t={ts},v1={sig}"

    assert engine.verify_webhook_signature(payload, header) is True
    assert engine.verify_webhook_signature(payload, "t=123,v1=bad_sig") is False


def test_stripe_webhook_subscription_lifecycle_and_idempotency():
    engine = StripeBillingEngine()

    create_event = {
        "id": "evt_sub_created_001",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "org_test_tenant",
                "metadata": {"tenant_id": "org_test_tenant", "tier": "growth"},
            }
        }
    }

    # 1. Process creation
    success, msg = engine.handle_webhook_event(json.dumps(create_event))
    assert success is True
    sub = engine.get_subscription("org_test_tenant")
    assert sub is not None
    assert sub["status"] == "active"
    assert sub["tier"] == "growth"

    # 2. Idempotent replay
    success_replay, msg_replay = engine.handle_webhook_event(json.dumps(create_event))
    assert success_replay is True
    assert "already processed" in msg_replay

    # 3. Payment failed -> past_due
    payment_fail_event = {
        "id": "evt_pay_failed_002",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "customer": "org_test_tenant",
                "metadata": {"tenant_id": "org_test_tenant"},
            }
        }
    }
    engine.handle_webhook_event(json.dumps(payment_fail_event))
    assert engine.get_subscription("org_test_tenant")["status"] == "past_due"

    # 4. Payment succeeded -> active
    payment_success_event = {
        "id": "evt_pay_success_003",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "customer": "org_test_tenant",
                "metadata": {"tenant_id": "org_test_tenant"},
            }
        }
    }
    engine.handle_webhook_event(json.dumps(payment_success_event))
    assert engine.get_subscription("org_test_tenant")["status"] == "active"
