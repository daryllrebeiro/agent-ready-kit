"""HMAC signed outbound webhook dispatcher for custom customer integrations."""

import hashlib
import hmac
import json
import time
from typing import Any, Dict
import requests


def compute_webhook_signature(payload_bytes: bytes, secret_key: str) -> str:
    """Generate SHA-256 HMAC signature for webhook payload."""
    return hmac.new(secret_key.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


class WebhookDispatcher:
    """Dispatches cryptographically verified webhook events."""

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    def dispatch_event(
        self,
        endpoint_url: str,
        secret_key: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send webhook event with X-AgentReady-Signature and X-AgentReady-Timestamp."""
        timestamp = str(int(time.time()))
        payload_dict = {
            "event": event_type,
            "timestamp": timestamp,
            "data": data,
        }
        body = json.dumps(payload_dict, default=str)
        signature = compute_webhook_signature(body.encode("utf-8"), secret_key)

        headers = {
            "Content-Type": "application/json",
            "X-AgentReady-Event": event_type,
            "X-AgentReady-Timestamp": timestamp,
            "X-AgentReady-Signature": signature,
        }

        try:
            resp = requests.post(endpoint_url, data=body, headers=headers, timeout=self.timeout_seconds)
            return {
                "success": resp.status_code < 400,
                "status_code": resp.status_code,
                "event": event_type,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "event": event_type,
            }
