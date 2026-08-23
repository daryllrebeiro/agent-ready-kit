"""Multi-tenant context and role-based access control."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
    READ_ONLY = "read_only"


@dataclass(frozen=True)
class TenantContext:
    """Security context defining the active organization and user."""

    org_id: str
    user_id: str
    role: UserRole = UserRole.MEMBER
    tier: str = "growth"  # free, growth, enterprise
    max_domains: int = 10
    monthly_probe_quota: int = 500

    def can_modify_domains(self) -> bool:
        return self.role in [UserRole.ADMIN, UserRole.MEMBER]

    def can_manage_org(self) -> bool:
        return self.role == UserRole.ADMIN

    def is_enterprise(self) -> bool:
        return self.tier.lower() == "enterprise"
