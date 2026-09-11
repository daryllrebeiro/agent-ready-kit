"""Phase 16 follow-up fixes: tenant store, persistent keys, webhook, headers."""

import hashlib
import hmac
import json
import os
import threading
import time
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

import apps.web.server as web_server
from apps.web.server import DashboardAPIHandler
from packages.core.auth.middleware import AuthContext, UserRole


def _run_server():
    server = HTTPServer(("127.0.0.1", 0), DashboardAPIHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    return server, port


class TestDomainScoping:
    def test_suffix_collision_rejected(self):
        ctx = AuthContext(
            tenant_id="t", org_id="t", role=UserRole.READ_ONLY, scoped_domain="example.com"
        )
        assert ctx.can_access_domain("https://example.com/x") is True
        assert ctx.can_access_domain("https://sub.example.com/x") is True
        assert ctx.can_access_domain("https://attacker-example.com/") is False
        assert ctx.can_access_domain("https://example.com.attacker.com/") is False

    def test_unscoped_allows_all(self):
        ctx = AuthContext(tenant_id="t", org_id="t")
        assert ctx.can_access_domain("https://anything.example/") is True


class TestSecurityHeaders:
    def test_json_responses_carry_headers(self):
        server, port = _run_server()
        try:
            conn = HTTPConnection("127.0.0.1", port)
            conn.request("GET", "/healthz")
            res = conn.getresponse()
            res.read()
            assert res.getheader("X-Frame-Options") == "DENY"
            assert res.getheader("Referrer-Policy") == "no-referrer"
            assert res.getheader("X-Content-Type-Options") == "nosniff"
        finally:
            server.shutdown()
            server.server_close()


class TestTenantStoreDefault:
    def test_sqlite_default_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTREADY_STORAGE", "sqlite")
        monkeypatch.setenv("AGENTREADY_DB_PATH", str(tmp_path / "t.db"))
        from packages.core.storage.tenant_store import TenantStore, storage_mode

        assert storage_mode() == "sqlite"
        store = TenantStore("tenant_x")
        html = "<html><head><title>T</title></head><body><p>hello world</p></body></html>"
        from packages.core.scorer import Scorer

        score = Scorer().score_payloads("https://example.com", html_content=html)
        store.save_score("https://example.com", score)
        got = store.get_latest_score("https://example.com")
        assert got is not None and got.url == "https://example.com"

    def test_dlq_escalation_without_url_returns_false(self):
        import os

        from packages.core.integrations.notifications import dispatch_dlq_escalation
        from packages.core.pipeline.dlq import FailedJob

        os.environ.pop("SLACK_WEBHOOK_URL", None)
        os.environ.pop("DISCORD_WEBHOOK_URL", None)
        job = FailedJob(
            id="j1", org_id="o", provider="openai", target_url="https://x.example",
            prompt="p", error_message="boom",
        )
        assert dispatch_dlq_escalation(job) is False


class TestStripeWebhookEndpoint:
    def _post(self, port, body, signature=None):
        conn = HTTPConnection("127.0.0.1", port)
        headers = {"Content-Type": "application/json"}
        if signature is not None:
            headers["Stripe-Signature"] = signature
        conn.request("POST", "/api/webhooks/stripe", body=body, headers=headers)
        res = conn.getresponse()
        return res.status, json.loads(res.read().decode())

    def test_unconfigured_secret_returns_503(self, monkeypatch):
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        server, port = _run_server()
        try:
            status, payload = self._post(port, "{}")
            assert status == 503
            assert payload["error_code"] == "WEBHOOK_UNCONFIGURED"
        finally:
            server.shutdown()
            server.server_close()

    def test_bad_signature_returns_401(self, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_real_test_value")
        server, port = _run_server()
        try:
            status, payload = self._post(port, '{"id":"evt_1","type":"x"}', signature="t=1,v1=deadbeef")
            assert status == 401
            assert payload["error_code"] == "WEBHOOK_BAD_SIGNATURE"
        finally:
            server.shutdown()
            server.server_close()

    def test_valid_signature_accepted(self, monkeypatch):
        secret = "whsec_real_test_value"
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
        event = {
            "id": "evt_fix_1",
            "type": "customer.subscription.created",
            "data": {"object": {"id": "sub_1", "customer": "cus_1",
                                "metadata": {"tenant_id": "tenant_hook", "tier": "growth"}}},
        }
        raw = json.dumps(event)
        sig = hmac.new(secret.encode(), f"1750000000.{raw}".encode(), hashlib.sha256).hexdigest()
        server, port = _run_server()
        try:
            status, payload = self._post(port, raw, signature=f"t=1750000000,v1={sig}")
            assert status == 200, payload
            assert payload["received"] is True
        finally:
            server.shutdown()
            server.server_close()


@pytest.mark.integration
class TestPersistentKeysRealPG:
    def test_generate_resolve_revoke_survives(self):
        from packages.core.storage.pg_connection import connect_real
        from packages.core.auth.pg_keys import PgAuthManager

        mgr = PgAuthManager(connect_real())
        raw = mgr.generate_api_key("tenant_pg_keys")
        assert raw.startswith("ark_live_")
        ctx = mgr.resolve_api_key(raw)
        assert ctx is not None and ctx.tenant_id == "tenant_pg_keys"

        # New manager instance, same DB: key must still resolve (persistence).
        mgr2 = PgAuthManager(connect_real())
        ctx2 = mgr2.resolve_api_key(raw)
        assert ctx2 is not None and ctx2.tenant_id == "tenant_pg_keys"

        assert mgr2.revoke_api_key(raw) is True
        assert PgAuthManager(connect_real()).resolve_api_key(raw) is None

    def test_expired_key_rejected(self):
        from packages.core.storage.pg_connection import connect_real
        from packages.core.auth.pg_keys import PgAuthManager

        mgr = PgAuthManager(connect_real())
        raw = mgr.generate_api_key("tenant_pg_exp")
        hashed = mgr.hash_key(raw)
        cur = mgr.conn.conn.cursor()
        cur.execute(
            "UPDATE api_keys SET expires_at = '2000-01-01T00:00:00+00:00' WHERE key_hash = ?",
            (hashed,),
        )
        mgr.conn.commit()
        assert PgAuthManager(connect_real()).resolve_api_key(raw) is None
