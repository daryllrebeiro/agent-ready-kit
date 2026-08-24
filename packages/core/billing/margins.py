"""SaaS Unit Economics & Gross Margin Guardrails.

Calculates estimated COGS per probe and guarantees subscription gross profit margins >= 70%.
"""

from typing import Any, Dict


ESTIMATED_COGS_PER_PROBE_USD = {
    "openai": 0.003,      # ~$0.003 per probe call (GPT-4o-mini / search)
    "anthropic": 0.004,   # ~$0.004 per probe call (Claude 3.5 Haiku)
    "gemini": 0.0015,     # ~$0.0015 per probe call (Gemini 1.5 Flash)
    "perplexity": 0.005,  # ~$0.005 per probe call (Sonar API)
}

PLAN_PRICING_USD = {
    "free": 0.0,
    "growth": 49.0,
    "enterprise": 249.0,
}

PLAN_INCLUDED_PROBES = {
    "free": 50,
    "growth": 1000,
    "enterprise": 10000,
}


class GrossMarginGuardrail:
    """Evaluates unit profitability and ensures COGS stays within sustainable SaaS boundaries."""

    @staticmethod
    def calculate_plan_gross_margin(plan_tier: str) -> Dict[str, Any]:
        """Calculates theoretical gross margin assuming 100% quota utilization."""
        revenue = PLAN_PRICING_USD.get(plan_tier.lower(), 0.0)
        probes_allowed = PLAN_INCLUDED_PROBES.get(plan_tier.lower(), 50)

        # Average blended cost per probe across the 4 providers
        avg_probe_cogs = sum(ESTIMATED_COGS_PER_PROBE_USD.values()) / len(ESTIMATED_COGS_PER_PROBE_USD)
        total_cogs = round(probes_allowed * avg_probe_cogs, 3)

        if revenue <= 0:
            gross_margin_pct = 0.0
        else:
            gross_profit = revenue - total_cogs
            gross_margin_pct = round((gross_profit / revenue) * 100.0, 1)

        is_sustainable = gross_margin_pct >= 70.0 if revenue > 0 else (total_cogs < 0.50)

        return {
            "plan_tier": plan_tier,
            "monthly_revenue_usd": revenue,
            "included_probes": probes_allowed,
            "blended_cogs_usd": total_cogs,
            "gross_margin_pct": gross_margin_pct,
            "target_margin_met": is_sustainable,
        }
