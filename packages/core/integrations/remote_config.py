"""Remote Configuration & Cloud Feature Flag Coordinator.

Provides sub-second runtime toggle of safety switches (Edge Proxy bypass, GitHub PR Bot kill switch,
Spend safeguards) without requiring service redeployment.
"""

import time
from typing import Any, Dict, Optional


class RemoteConfigManager:
    """Manages cloud-synchronized dynamic feature flags and kill switches."""

    def __init__(self, initial_flags: Optional[Dict[str, Any]] = None):
        self._flags: Dict[str, Any] = initial_flags or {
            "edge_proxy_kill_switch": False,
            "github_pr_bot_kill_switch": False,
            "global_spend_circuit_breaker_override": False,
            "mcp_gateway_maintenance_mode": False,
        }
        self._last_synced: float = time.time()
        self._audit_log = []

    def get_flag(self, flag_name: str, default: Any = False) -> Any:
        return self._flags.get(flag_name, default)

    def set_flag(self, flag_name: str, value: Any, actor: str = "admin@agentready.dev") -> Dict[str, Any]:
        """Dynamically updates a remote flag and records an audit log entry."""
        prev = self._flags.get(flag_name)
        self._flags[flag_name] = value
        self._last_synced = time.time()
        entry = {
            "timestamp": self._last_synced,
            "flag_name": flag_name,
            "previous_value": prev,
            "new_value": value,
            "actor": actor,
        }
        self._audit_log.append(entry)
        return entry

    def is_kill_switch_active(self, component: str) -> bool:
        flag_key = f"{component}_kill_switch"
        return bool(self.get_flag(flag_key, False))
