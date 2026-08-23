"""GitHub PR Comment Markdown Formatter."""

from packages.core.schemas import Score


def format_pr_comment(score: Score, min_score: float | None = None) -> str:
    """Render a GitHub Flavored Markdown comment for PR CI runs."""
    status_icon = "[PASS]" if score.overall_score >= 80 else "[WARN]" if score.overall_score >= 50 else "[FAIL]"
    ci_status = ""
    if min_score is not None:
        if score.overall_score >= min_score:
            ci_status = f"**CI Check:** [OK] Passed (Score {score.overall_score:.1f} >= {min_score:.1f})\n\n"
        else:
            ci_status = f"**CI Check:** [FAIL] FAILED (Score {score.overall_score:.1f} < {min_score:.1f})\n\n"

    lines = [
        f"## {status_icon} AgentReady Score Report: `{score.url}`",
        "",
        ci_status,
        f"**Overall Score:** `{score.overall_score:.1f}/100` (Grade: **{score.grade}**) | **Version:** `{score.version}`",
        "",
        f"> {score.summary}",
        "",
        "### Readiness Signal Breakdown",
        "",
        "| Status | Signal Check | Score | Weight | Key Diagnostics |",
        "| :---: | :--- | :---: | :---: | :--- |",
    ]

    for comp in score.components:
        badge = "PASS" if comp.status.value == "PASS" else "WARN" if comp.status.value == "WARN" else "FAIL"
        lines.append(f"| `{badge}` | **{comp.display_name}** | `{comp.score:.1f}` | {int(comp.weight * 100)}% | {comp.details} |")

    if score.recommendations:
        lines.extend([
            "",
            "<details>",
            "<summary><strong>[+] Actionable Remediation Checklist</strong> (click to expand)</summary>",
            "",
        ])
        for idx, rec in enumerate(score.recommendations, 1):
            lines.append(f"{idx}. {rec}")
        lines.append("\n</details>")

    lines.extend([
        "",
        "---",
        "*Report generated automatically by [AgentReady](https://github.com/daryllrebeiro/agent-ready-kit)*",
    ])

    return "\n".join(lines)
