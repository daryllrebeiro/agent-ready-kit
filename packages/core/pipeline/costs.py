"""LLM probe cost tracking and tenant unit economics calculator."""

from typing import Dict

# Pricing per 1k tokens / query (USD)
PROVIDER_PRICING: Dict[str, Dict[str, float]] = {
    "openai": {"input_per_1k": 0.0025, "output_per_1k": 0.0100, "per_query": 0.0},
    "anthropic": {"input_per_1k": 0.0030, "output_per_1k": 0.0150, "per_query": 0.0},
    "gemini": {"input_per_1k": 0.0001, "output_per_1k": 0.0004, "per_query": 0.0},
    "perplexity": {"input_per_1k": 0.0010, "output_per_1k": 0.0010, "per_query": 0.005},
}


class CostAuditor:
    """Computes variable LLM inference costs and subscription margins."""

    @staticmethod
    def estimate_probe_cost(
        provider: str,
        input_tokens: int = 250,
        output_tokens: int = 400,
    ) -> float:
        """Estimate the USD cost of a single LLM probe query."""
        pricing = PROVIDER_PRICING.get(provider.lower(), {"input_per_1k": 0.002, "output_per_1k": 0.008, "per_query": 0.0})
        cost = (
            (input_tokens / 1000.0) * pricing.get("input_per_1k", 0.0)
            + (output_tokens / 1000.0) * pricing.get("output_per_1k", 0.0)
            + pricing.get("per_query", 0.0)
        )
        return round(cost, 5)

    @staticmethod
    def calculate_tenant_margin(
        tier_monthly_price: float,
        probes_executed: int,
        avg_cost_per_probe: float = 0.006,
    ) -> Dict[str, float]:
        """Compute tenant profitability and gross margin percentage."""
        total_variable_cost = probes_executed * avg_cost_per_probe
        gross_profit = tier_monthly_price - total_variable_cost
        margin_pct = (gross_profit / max(0.01, tier_monthly_price)) * 100.0
        return {
            "tier_price": tier_monthly_price,
            "probes_executed": probes_executed,
            "total_variable_cost": round(total_variable_cost, 2),
            "gross_profit": round(gross_profit, 2),
            "margin_pct": round(margin_pct, 1),
        }
