"""Model drift detection and scoring algorithm evolution (score_v0.2)."""

from typing import Any

from packages.core.schemas import Score
from packages.core.version import ALGORITHM_VERSION_V0_2, EXPERIMENTAL_WEIGHTS_V0_2

# Single weights source lives in packages.core.version; re-exported here
# for backward compatibility with existing imports.
WEIGHTS_V0_2 = EXPERIMENTAL_WEIGHTS_V0_2


def calculate_distribution_drift(
    baseline_citations: dict[str, int],
    current_citations: dict[str, int],
) -> dict[str, Any]:
    """
    Measure citation distribution drift across providers.
    Returns divergence score and drift assessment.
    """
    total_base = sum(baseline_citations.values()) or 1
    total_curr = sum(current_citations.values()) or 1

    providers = set(baseline_citations.keys()).union(set(current_citations.keys()))
    divergence = 0.0

    provider_shifts = {}
    for p in providers:
        p_base = baseline_citations.get(p, 0) / total_base
        p_curr = current_citations.get(p, 0) / total_curr
        shift = p_curr - p_base
        provider_shifts[p] = round(shift * 100.0, 2)
        divergence += abs(shift)

    drift_score = round(divergence / 2.0, 4)  # Normalized 0.0 to 1.0

    if drift_score >= 0.25:
        assessment = "SIGNIFICANT DRIFT: LLM citation patterns have shifted noticeably. Weight recalibration recommended."
    elif drift_score >= 0.10:
        assessment = "MODERATE DRIFT: Minor variance detected across provider share."
    else:
        assessment = "STABLE: Citation distributions remain consistent with baseline."

    return {
        "drift_score": drift_score,
        "assessment": assessment,
        "provider_shifts_pct": provider_shifts,
    }


def upgrade_score_to_v0_2(score: Score) -> Score:
    """Recalibrate an existing Score to algorithm version score_v0.2."""
    new_components = []
    total_weighted = 0.0
    total_weight = 0.0

    for comp in score.components:
        new_weight = WEIGHTS_V0_2.get(comp.name, comp.weight)
        updated_comp = comp.model_copy(update={"weight": new_weight})
        new_components.append(updated_comp)
        total_weighted += updated_comp.score * new_weight
        total_weight += new_weight

    new_overall = round(total_weighted / max(0.01, total_weight), 1)

    from packages.core.config import get_grade

    return score.model_copy(
        update={
            "version": ALGORITHM_VERSION_V0_2,
            "overall_score": new_overall,
            "grade": get_grade(new_overall),
            "components": new_components,
        }
    )
