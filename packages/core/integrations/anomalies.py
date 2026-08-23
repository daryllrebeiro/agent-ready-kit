"""Proactive citation anomaly detection and root cause diagnosis."""

from typing import Any, Dict, List, Optional
from packages.core.schemas import Score


class CitationAnomalyDetector:
    """Detects citation anomalies and diagnoses probable root causes."""

    def __init__(self, drop_threshold_pct: float = 20.0):
        self.drop_threshold = drop_threshold_pct

    def detect_citation_drop(
        self,
        domain: str,
        current_rate_pct: float,
        baseline_rate_pct: float,
        latest_score: Optional[Score] = None,
    ) -> Optional[Dict[str, Any]]:
        """Detect citation drop exceeding threshold and diagnose root causes."""
        if baseline_rate_pct <= 0.0:
            return None

        drop = baseline_rate_pct - current_rate_pct
        if drop < self.drop_threshold:
            return None

        # Root Cause Diagnosis
        diagnoses: List[str] = []
        if latest_score:
            for comp in latest_score.components:
                if comp.name == "bot_permissions" and comp.score < 50.0:
                    diagnoses.append("CRITICAL: AI search crawlers (GPTBot/ClaudeBot/PerplexityBot) blocked in robots.txt")
                if comp.name == "structured_data" and comp.score < 40.0:
                    diagnoses.append("HIGH: Missing or malformed Schema.org JSON-LD structured entities")
                if comp.name == "token_bloat" and comp.score < 50.0:
                    diagnoses.append("MEDIUM: Content token bloat or SPA client-side rendering obscuring raw text")
                if comp.name == "llms_txt" and comp.score < 50.0:
                    diagnoses.append("MEDIUM: Missing /llms.txt markdown context directory")

        if not diagnoses:
            diagnoses.append("UNKNOWN: LLM model knowledge refresh or competitor authority displacement")

        return {
            "domain": domain,
            "severity": "SEV-2" if drop >= 40.0 else "SEV-3",
            "baseline_rate_pct": baseline_rate_pct,
            "current_rate_pct": current_rate_pct,
            "drop_percentage_points": round(drop, 1),
            "diagnoses": diagnoses,
            "recommended_actions": [
                f"Verify robots.txt allows AI bot user agents: `agentready scan https://{domain}`",
                "Re-run competitor benchmark to identify newly cited alternative domains",
                "Verify /llms.txt and JSON-LD schema validity",
            ],
        }

    def format_slack_anomaly_alert(self, anomaly: Dict[str, Any]) -> Dict[str, Any]:
        """Format Slack block payload for citation anomaly incident."""
        domain = anomaly["domain"]
        drop = anomaly["drop_percentage_points"]
        sev = anomaly["severity"]

        diagnoses_text = "\n".join([f"• {d}" for d in anomaly["diagnoses"]])
        actions_text = "\n".join([f"• {a}" for a in anomaly["recommended_actions"]])

        return {
            "text": f"[{sev}] Citation Drop Alert for {domain} (-{drop}% pts)",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🚨 [{sev}] AI Citation Drop Detected: {domain}"},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Baseline Rate:*\n{anomaly['baseline_rate_pct']:.1f}%"},
                        {"type": "mrkdwn", "text": f"*Current Rate:*\n{anomaly['current_rate_pct']:.1f}%"},
                        {"type": "mrkdwn", "text": f"*Drop:*\n-{drop}% pts"},
                        {"type": "mrkdwn", "text": f"*Severity:*\n{sev}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Root Cause Diagnoses:*\n{diagnoses_text}"},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Recommended Actions:*\n{actions_text}"},
                },
            ],
        }
