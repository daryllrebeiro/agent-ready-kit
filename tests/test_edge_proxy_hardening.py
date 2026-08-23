"""Unit tests for Edge Proxy Hardening & Crawler Rate Limiting."""

from packages.edge_proxy.simulator import EdgeBotRateLimiter, EdgeProxySimulator


def test_edge_proxy_bot_rate_limiting():
    rate_limiter = EdgeBotRateLimiter(max_bot_requests_per_minute=2)
    proxy = EdgeProxySimulator(
        shadow_mode=False,
        fallback_llms_txt="# Mock Fallback LLMs.txt",
        bot_rate_limiter=rate_limiter,
    )

    headers = {
        "User-Agent": "GPTBot/1.0",
        "Accept": "text/markdown",
        "CF-Connecting-IP": "1.2.3.4",
    }

    def origin_404(url, h):
        return {"status": 404, "body": "Not found", "headers": {}}

    # First 2 requests succeed
    res1 = proxy.handle_request("https://example.com/llms.txt", headers, origin_404)
    res2 = proxy.handle_request("https://example.com/llms.txt", headers, origin_404)
    assert res1["status"] == 200
    assert res2["status"] == 200

    # 3rd request is rate-limited at edge
    res3 = proxy.handle_request("https://example.com/llms.txt", headers, origin_404)
    assert res3["status"] == 429
    assert "Too Many Requests" in res3["body"]


def test_edge_proxy_fail_open_guarantee():
    proxy = EdgeProxySimulator(shadow_mode=False)

    def failing_origin(url, h):
        raise RuntimeError("Origin database timeout")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0)"}
    res = proxy.handle_request("https://example.com/page", headers, failing_origin)
    assert res["status"] == 502
    assert "Origin unavailable" in res["body"]
