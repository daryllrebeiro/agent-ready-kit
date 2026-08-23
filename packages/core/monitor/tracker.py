"""Autonomous monitoring and daily delta tracking between scans."""

from typing import Any, Dict, List, Optional
from packages.core.schemas import ComponentStatus, Score


class ScoreDeltaTracker:
    """Computes regressions, improvements, and change digests between score snapshots."""

    @staticmethod
    def compute_delta(baseline: Score, current: Score) -> Dict[str, Any]:
        """Compare two scores and generate a delta report."""
        score_diff = round(current.overall_score - baseline.overall_score, 1)
        grade_changed = baseline.grade != current.grade

        component_regressions: List[Dict[str, str]] = []
        component_improvements: List[Dict[str, str]] = []

        base_comps = {c.name: c for c in baseline.components}
        curr_comps = {c.name: c for c in current.components}

        for name, curr_c in curr_comps.items():
            base_c = base_comps.get(name)
            if not base_c:
                continue

            diff = round(curr_c.score - base_c.score, 1)
            if diff < 0 or (base_c.status == ComponentStatus.PASS and curr_c.status != ComponentStatus.PASS):
                component_regressions.append({
                    "component": curr_c.display_name,
                    "previous_score": f"{base_c.score:.1f}",
                    "current_score": f"{curr_c.score:.1f}",
                    "delta": f"{diff:+.1f}",
                    "previous_status": base_c.status.value,
                    "current_status": curr_c.status.value,
                })
            elif diff > 0 or (base_c.status != ComponentStatus.PASS and curr_c.status == ComponentStatus.PASS):
                component_improvements.append({
                    "component": curr_c.display_name,
                    "previous_score": f"{base_c.score:.1f}",
                    "current_score": f"{curr_c.score:.1f}",
                    "delta": f"{diff:+.1f}",
                    "previous_status": base_c.status.value,
                    "current_status": curr_c.status.value,
                })

        # Summary classification
        if score_diff < -5.0 or component_regressions:
            change_type = "REGRESSION"
        elif score_diff > 5.0 or component_improvements:
            change_type = "IMPROVEMENT"
        else:
            change_type = "STABLE"

        return {
            "url": current.url,
            "change_type": change_type,
            "overall_score_delta": score_diff,
            "previous_score": baseline.overall_score,
            "current_score": current.overall_score,
            "previous_grade": baseline.grade,
            "current_grade": current.grade,
            "grade_changed": grade_changed,
            "regressions": component_regressions,
            "improvements": component_improvements,
        }
