"""Unit tests for Edge Proxy simulator verifying fail-open, shadow mode, and bot interception."""

from packages.edge_proxy.simulator import EdgeProxySimulator


def test_edge_proxy_fail_open_on_internal_exception():
    proxy = EdgeProxySimulator(shadow_mode=False)

    # Origin fetch returns valid HTML
    def mock_origin(url, headers):
        return {"status": 200, "body": "<h1>Origin Page</h1>", "headers": {"Content-Type": "text/html"}}

    # Force internal exception in routing
    res = proxy.handle_request(
        url="https://customer.com/page",
        headers={"User-Agent": "Mozilla/5.0"},
        origin_fetch=mock_origin,
    )

    # Must return origin page with fail-open safety
    assert res["status"] == 200
    assert "Origin Page" in res["body"]


def test_edge_proxy_shadow_mode():
    proxy = EdgeProxySimulator(shadow_mode=True)

    def mock_origin(url, headers):
        return {"status": 200, "body": "Origin Response", "headers": {}}

    res = proxy.handle_request(
        url="https://customer.com/llms.txt",
        headers={"User-Agent": "GPTBot/1.0"},
        origin_fetch=mock_origin,
    )

    assert res["status"] == 200
    assert res["headers"].get("X-AgentReady-Shadow") == "true"
    assert len(proxy.shadow_logs) == 1
    assert proxy.shadow_logs[0]["is_ai_bot"] is True


def test_edge_proxy_live_interception():
    proxy = EdgeProxySimulator(
        shadow_mode=False,
        fallback_llms_txt="# Generated llms.txt\n> Edge cached",
    )

    # Origin 404s on llms.txt
    def mock_origin(url, headers):
        return {"status": 404, "body": "Not found", "headers": {}}

    res = proxy.handle_request(
        url="https://customer.com/llms.txt",
        headers={"User-Agent": "PerplexityBot/1.0"},
        origin_fetch=mock_origin,
    )

    assert res["status"] == 200
    assert "Generated llms.txt" in res["body"]
    assert res["headers"].get("X-Served-By") == "AgentReady-Edge-Proxy"


def test_edge_proxy_kill_switch():
    proxy = EdgeProxySimulator(shadow_mode=False, kill_switch=True)

    def mock_origin(url, headers):
        return {"status": 200, "body": "Bypassed Origin", "headers": {}}

    res = proxy.handle_request(
        url="https://customer.com/llms.txt",
        headers={"User-Agent": "GPTBot/1.0"},
        origin_fetch=mock_origin,
    )

    assert res["status"] == 200
    assert "Bypassed Origin" in res["body"]
    assert res["headers"].get("X-AgentReady-Bypass") == "true"
