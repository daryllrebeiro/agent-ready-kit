"""Executive AI Agent Health Report generator."""

import time
from typing import Any, Dict, Optional
from packages.core.personas.simulator import AgentPersonaSimulator
from packages.core.scorer import Scorer


class ExecutiveHealthReportGenerator:
    """Compiles complete Executive AI Agent Readiness & Health Reports."""

    def __init__(self):
        self.scorer = Scorer()
        self.personas = AgentPersonaSimulator()

    def generate_report(self, url: str) -> str:
        """Generate comprehensive markdown executive report for target URL."""
        from packages.core.probes.extractor import extract_domain_from_url
        score = self.scorer.score_url(url)
        persona_res = self.personas.simulate_all_personas(url)
        domain = extract_domain_from_url(score.url)

        lines = [
            f"# 📊 Executive AI Agent Health Report — {domain}",
            "",
            f"> **Generated on:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}  ",
            f"> **Target URL:** `{score.url}`  ",
            f"> **Overall Agent-Ready Score:** `{score.overall_score}/100` (Grade: **{score.grade}**)  ",
            f"> **Autonomous Persona Compatibility:** `{persona_res['overall_compatibility']}/100`",
            "",
            "---",
            "",
            "## 1. Core Readiness Components",
            "",
            "| Component | Score | Status | Weight | Details |",
            "|---|---|---|---|---|",
        ]

        for c in score.components:
            status_badge = "PASS" if c.status.value == "PASS" else "WARN" if c.status.value == "WARN" else "FAIL"
            lines.append(f"| **{c.display_name}** | {c.score}/100 | `{status_badge}` | {int(c.weight * 100)}% | {c.details} |")

        lines.extend([
            "",
            "---",
            "",
            "## 2. Autonomous Agent Persona Simulations",
            "",
            "| Agent Persona | Archetype | Compatibility | Status |",
            "|---|---|---|---|",
        ])

        for key, p in persona_res["personas"].items():
            lines.append(f"| **{p['name']}** | `{p['archetype']}` | {p['compatibility_score']:.1f}/100 | **{p['status']}** |")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Prioritized Action Items",
            "",
        ])

        recommendations = []
        for c in score.components:
            for rec in c.recommendations:
                recommendations.append(f"- **[{c.display_name}]**: {rec}")

        if not recommendations:
            lines.append("- [OK] All core checks passed! Maintain regular monitoring to detect citation drift.")
        else:
            lines.extend(recommendations)

        lines.extend([
            "",
            "---",
            "",
            "## 4. Turnkey Remediation Commands",
            "",
            "To automatically generate and deploy recommended context files:",
            "```bash",
            f"# 1. Automatically generate /llms.txt and schema templates",
            f"agentready fix {score.url} --output-dir ./public",
            "",
            f"# 2. Benchmark against industry competitors",
            f"agentready compare {score.url} --vs https://competitor1.com https://competitor2.com",
            "```",
            "",
            "---",
            "*Report compiled automatically by [AgentReady Kit](https://github.com/daryllrebeiro/agent-ready-kit)*",
        ])

        return "\n".join(lines)
