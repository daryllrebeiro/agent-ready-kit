"""Edge proxy simulation harness for verifying fail-open behavior and bot routing."""

import re
from typing import Any, Callable, Dict, Optional

AI_BOT_PATTERN = re.compile(
    r"(GPTBot|ClaudeBot|PerplexityBot|Claude-Web|ChatGPT-User|Google-Extended|Applebot-Extended|Amazonbot|cohere-ai|CCBot)",
    re.IGNORECASE,
)


class EdgeProxySimulator:
    """Simulates edge reverse proxy handling with guaranteed fail-open behavior."""

    def __init__(
        self,
        shadow_mode: bool = True,
        kill_switch: bool = False,
        fallback_llms_txt: Optional[str] = None,
    ):
        self.shadow_mode = shadow_mode
        self.kill_switch = kill_switch
        self.fallback_llms_txt = fallback_llms_txt
        self.shadow_logs: list[Dict[str, Any]] = []

    def handle_request(
        self,
        url: str,
        headers: Dict[str, str],
        origin_fetch: Callable[[str, Dict[str, str]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Processes incoming request with strict FAIL-OPEN envelope.
        origin_fetch is a callable returning {"status": 200, "body": "...", "headers": {...}}
        """
        try:
            return self._internal_route(url, headers, origin_fetch)
        except Exception as e:
            # FAIL-OPEN SAFETY: Any exception falls back directly to origin
            try:
                fallback_resp = origin_fetch(url, headers)
                fallback_resp["headers"]["X-AgentReady-FailOpen"] = "true"
                return fallback_resp
            except Exception:
                # If even origin fails, return a 502 pass-through
                return {"status": 502, "body": "Origin unavailable", "headers": {}}

    def _internal_route(
        self,
        url: str,
        headers: Dict[str, str],
        origin_fetch: Callable[[str, Dict[str, str]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        user_agent = headers.get("User-Agent", "")
        accept = headers.get("Accept", "")
        is_bypass = headers.get("X-AgentReady-Bypass") == "true" or self.kill_switch

        # 1. Kill Switch Bypass
        if is_bypass:
            resp = origin_fetch(url, headers)
            resp["headers"]["X-AgentReady-Bypass"] = "true"
            return resp

        # 2. Bot Detection
        is_ai_bot = bool(AI_BOT_PATTERN.search(user_agent))
        requests_markdown = "text/markdown" in accept

        # 3. Shadow Mode
        if self.shadow_mode:
            self.shadow_logs.append({
                "url": url,
                "user_agent": user_agent,
                "is_ai_bot": is_ai_bot,
                "requests_markdown": requests_markdown,
            })
            resp = origin_fetch(url, headers)
            resp["headers"]["X-AgentReady-Shadow"] = "true"
            return resp

        # 4. Active Interception
        if (is_ai_bot or requests_markdown) and url.endswith("/llms.txt"):
            origin_resp = origin_fetch(url, headers)
            if origin_resp.get("status") == 200:
                return origin_resp
            if self.fallback_llms_txt:
                return {
                    "status": 200,
                    "body": self.fallback_llms_txt,
                    "headers": {
                        "Content-Type": "text/markdown; charset=utf-8",
                        "X-Served-By": "AgentReady-Edge-Proxy",
                    },
                }

        return origin_fetch(url, headers)
