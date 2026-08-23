"""End-to-End Multi-Tenant Integration Launch Matrix Test.

Validates the complete production lifecycle from tenant onboarding to probing,
billing sync, MCP execution, edge proxy, and observability health checks.
"""

import json
import time
from unittest.mock import MagicMock, patch

from packages.core.auth.middleware import AuthManager, UserRole
from packages.core.billing.stripe_engine import StripeBillingEngine
from packages.edge_proxy.simulator import EdgeBotRateLimiter, EdgeProxySimulator
from packages.core.observability.health import HealthChecker
from packages.core.observability.logger import TraceContext
from packages.core.pipeline.budget_enforcer import BudgetEnforcer
from packages.core.probes.redis_cache import DistributedProbeCache, MockRedisClient
from packages.core.probes.runner import MultiModelProber
from packages.core.scorer import Scorer
from packages.core.storage.repository import StorageRepository
from packages.mcp.server import MCPServer


def test_e2e_production_launch_matrix():
    with TraceContext(trace_id="tr_e2e_launch_matrix", tenant_id="tenant_acme_corp") as ctx:
        # Step 1: Initialize Storage, Mock Redis, and Auth Manager
        mock_redis = MockRedisClient()
        cache = DistributedProbeCache(redis_client=mock_redis)
        storage = StorageRepository()
        auth_mgr = AuthManager()
        billing = StripeBillingEngine(webhook_secret="whsec_test_secret_123")

        # Step 2: Tenant Onboarding & API Key Generation
        tenant_id = "tenant_acme_corp"
        org_id = "org_acme_engineering"
        raw_key = auth_mgr.generate_api_key(
            tenant_id=tenant_id,
            org_id=org_id,
            role=UserRole.ADMIN,
        )
        assert raw_key.startswith("ak_live_")

        auth_ctx = auth_mgr.resolve_api_key(raw_key)
        assert auth_ctx is not None
        assert auth_ctx.tenant_id == tenant_id
        assert auth_ctx.has_permission(UserRole.MEMBER) is True

        # Create subscription first
        created_event = {
            "id": "evt_sub_growth_matrix_0",
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_matrix_999",
                    "customer": "cus_acme_999",
                    "status": "active",
                    "metadata": {"tenant_id": tenant_id, "tier": "growth"},
                }
            },
        }
        ok_create, _ = billing.handle_webhook_event(json.dumps(created_event))
        assert ok_create is True
        assert billing.get_subscription(tenant_id)["tier"] == "growth"

        # Step 4: Pre-Call Budget Reservation (Growth tier has 2,500 units)
        budget_enforcer = BudgetEnforcer(cache=cache)
        budget_res = budget_enforcer.check_and_reserve_budget(
            tenant_id=tenant_id,
            plan_tier="growth",
            units_needed=4,
        )
        assert budget_res["allowed"] is True
        assert budget_res["remaining_budget"] == 1996

        # Step 5: Multi-Model Probing with Deduplication Cache
        prober = MultiModelProber()
        probes = prober.run_standard_probe_suite("example.com", max_prompts=2, dry_run=True)
        assert len(probes) == 2
        probe_results_list = probes[0]["results"]
        assert len(probe_results_list) == 4

        # Cache one probe and verify cache retrieval
        target_probe = probe_results_list[0]
        cache.store_cached_probe(tenant_id, target_probe.provider, target_probe.prompt, target_probe)
        cached_hit = cache.get_cached_probe(tenant_id, target_probe.provider, target_probe.prompt)
        assert cached_hit is not None
        assert cached_hit.provider == target_probe.provider

        # Step 6: Authenticated MCP Server Tool Call
        mcp_server = MCPServer(auth_manager=auth_mgr, auth_required=True)
        mcp_req = {
            "jsonrpc": "2.0",
            "id": "mcp_call_1",
            "method": "tools/call",
            "params": {
                "api_key": raw_key,
                "name": "get_site_readiness",
                "arguments": {"url": "https://example.com"},
            },
        }
        mcp_resp = mcp_server.handle_request(mcp_req)
        assert "result" in mcp_resp
        assert mcp_resp["result"].get("isError") is not True

        # Step 7: Edge Proxy Crawler Rate Limiting & Fail-Open Check
        edge_limiter = EdgeBotRateLimiter(max_bot_requests_per_minute=5)
        edge_proxy = EdgeProxySimulator(
            shadow_mode=False,
            fallback_llms_txt="# Fallback llms.txt",
            bot_rate_limiter=edge_limiter,
        )
        edge_headers = {
            "User-Agent": "GPTBot/1.0",
            "Accept": "text/markdown",
            "CF-Connecting-IP": "10.0.0.1",
        }
        edge_resp = edge_proxy.handle_request("https://example.com/llms.txt", edge_headers, lambda u, h: {"status": 404, "body": "", "headers": {}})
        assert edge_resp["status"] == 200
        assert "AgentReady-Edge-Proxy" in edge_resp["headers"]["X-Served-By"]

        # Step 8: Operational Readiness Health Probe
        health = HealthChecker(storage=storage, cache=cache)
        readiness = health.check_readiness()
        assert readiness["ready"] is True
        assert readiness["status"] == "healthy"
        assert readiness["checks"]["database"]["status"] == "UP"
        assert readiness["checks"]["redis"]["status"] == "UP"

        # Verify execution completed smoothly
        assert ctx.elapsed_ms > 0
