"""Graduated General Availability (GA) Rollout Controller.

Manages tenant cohort allocation and traffic percentage gates (10% -> 50% -> 100%)
with automated safety rollback triggers upon SLO breaches.
"""

import hashlib
import time
from enum import Enum
from typing import Any, Dict, List, Optional


class RolloutStage(str, Enum):
    PILOT_10 = "10_PERCENT_PILOT"
    EXPANDED_50 = "50_PERCENT_EXPANDED"
    GA_100 = "100_PERCENT_GA"
    ROLLED_BACK = "ROLLED_BACK"


class GraduatedRolloutController:
    """Controls gradual tenant progression to General Availability."""

    def __init__(
        self,
        initial_stage: RolloutStage = RolloutStage.PILOT_10,
        allowed_canary_tenants: Optional[List[str]] = None,
    ):
        self.stage = initial_stage
        self.canary_tenants = set(allowed_canary_tenants or ["tenant_enterprise_beta_1", "tenant_growth_pilot_2"])
        self.stage_history: List[Dict[str, Any]] = [
            {"stage": self.stage.value, "timestamp": time.time(), "reason": "Initial deployment"}
        ]

    def is_tenant_eligible(self, tenant_id: str) -> bool:
        """Determines if a tenant is enrolled in the current rollout stage."""
        if self.stage == RolloutStage.ROLLED_BACK:
            return False

        if self.stage == RolloutStage.GA_100:
            return True

        # Explicit canary override
        if tenant_id in self.canary_tenants:
            return True

        # Consistent deterministic hashing for gradual cohorts (10% or 50%)
        bucket = int(hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:8], 16) % 100

        if self.stage == RolloutStage.PILOT_10:
            return bucket < 10

        if self.stage == RolloutStage.EXPANDED_50:
            return bucket < 50

        return False

    def promote_stage(self, new_stage: RolloutStage, reason: str = "SLO validation passed") -> Dict[str, Any]:
        """Promotes the rollout to the next stage."""
        self.stage = new_stage
        event = {
            "stage": self.stage.value,
            "timestamp": time.time(),
            "reason": reason,
        }
        self.stage_history.append(event)
        return event

    def trigger_emergency_rollback(self, breach_reason: str) -> Dict[str, Any]:
        """Immediately rolls back traffic to 0% in response to critical SLO or DLQ breach."""
        self.stage = RolloutStage.ROLLED_BACK
        event = {
            "stage": self.stage.value,
            "timestamp": time.time(),
            "reason": f"EMERGENCY ROLLBACK: {breach_reason}",
        }
        self.stage_history.append(event)
        return event
