"""Correlation analysis engine to validate whether agent-readiness scores predict LLM citation behavior."""

import math
from typing import Any, Dict, List, Tuple
from packages.core.schemas import Score


def compute_pearson_correlation(x: List[float], y: List[float]) -> float:
    """Compute Pearson correlation coefficient between two numeric series."""
    n = len(x)
    if n != len(y) or n < 2:
        return 0.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    var_x = sum((x[i] - mean_x) ** 2 for i in range(n))
    var_y = sum((y[i] - mean_y) ** 2 for i in range(n))

    denominator = math.sqrt(var_x * var_y)
    if denominator == 0:
        return 0.0
    return round(cov / denominator, 4)


def compute_spearman_rank_correlation(x: List[float], y: List[float]) -> float:
    """Compute Spearman's rank correlation coefficient."""
    n = len(x)
    if n != len(y) or n < 2:
        return 0.0

    def rankify(series: List[float]) -> List[float]:
        sorted_indices = sorted(range(n), key=lambda i: series[i])
        ranks = [0.0] * n
        for rank, idx in enumerate(sorted_indices, 1):
            ranks[idx] = float(rank)
        return ranks

    rank_x = rankify(x)
    rank_y = rankify(y)
    return compute_pearson_correlation(rank_x, rank_y)


class CorrelationHarness:
    """Analyzes correlation between agent-readiness scores and LLM citation outcomes."""

    def analyze_dataset(
        self,
        samples: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyze a list of sampled items.
        Each sample dict contains:
          - domain: str
          - score: Score object or dict
          - citation_count: int / float
          - citation_rate: float (0.0 to 1.0)
        """
        if not samples:
            return {"error": "empty_dataset", "samples_count": 0}

        overall_scores: List[float] = []
        llms_txt_scores: List[float] = []
        structured_scores: List[float] = []
        bloat_scores: List[float] = []
        bot_scores: List[float] = []
        citation_rates: List[float] = []

        for sample in samples:
            sc = sample["score"]
            overall = sc.overall_score if isinstance(sc, Score) else sc.get("overall_score", 0.0)
            overall_scores.append(overall)

            components = sc.components if isinstance(sc, Score) else sc.get("components", [])
            comp_map = {c.name: c.score for c in components} if isinstance(sc, Score) else {c["name"]: c["score"] for c in components}

            llms_txt_scores.append(comp_map.get("llms_txt", 0.0))
            structured_scores.append(comp_map.get("structured_data", 0.0))
            bloat_scores.append(comp_map.get("token_bloat", 0.0))
            bot_scores.append(comp_map.get("bot_permissions", 0.0))

            citation_rates.append(float(sample.get("citation_rate", 0.0)))

        pearson = compute_pearson_correlation(overall_scores, citation_rates)
        spearman = compute_spearman_rank_correlation(overall_scores, citation_rates)

        sub_correlations = {
            "llms_txt": compute_pearson_correlation(llms_txt_scores, citation_rates),
            "structured_data": compute_pearson_correlation(structured_scores, citation_rates),
            "token_bloat": compute_pearson_correlation(bloat_scores, citation_rates),
            "bot_permissions": compute_pearson_correlation(bot_scores, citation_rates),
        }

        # Determine signal impact rank
        ranked_signals = sorted(sub_correlations.items(), key=lambda x: x[1], reverse=True)

        if pearson >= 0.70:
            finding = "STRONG POSITIVE CORRELATION: Higher agent readiness directly predicts higher citation frequency."
        elif pearson >= 0.40:
            finding = "MODERATE CORRELATION: Agent readiness shows positive predictive signal for LLM citations."
        elif pearson >= 0.10:
            finding = "WEAK CORRELATION: Signal detected, but requires weight recalibration."
        else:
            finding = "NO CORRELATION: Revisit signal definitions or prompt selection."

        return {
            "samples_count": len(samples),
            "overall_pearson_r": pearson,
            "overall_spearman_rho": spearman,
            "signal_correlations": sub_correlations,
            "strongest_signal": ranked_signals[0][0] if ranked_signals else None,
            "finding": finding,
        }
