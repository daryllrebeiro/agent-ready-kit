"""Readiness check modules for scoring websites and endpoints."""

from packages.core.checks.bot_permissions import check_bot_permissions
from packages.core.checks.llms_txt import check_llms_txt
from packages.core.checks.structured_data import check_structured_data
from packages.core.checks.token_bloat import check_token_bloat

__all__ = [
    "check_bot_permissions",
    "check_llms_txt",
    "check_structured_data",
    "check_token_bloat",
]
