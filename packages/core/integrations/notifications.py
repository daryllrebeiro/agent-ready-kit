"""Slack and Discord webhook notification dispatchers for AgentReady alerts."""

import json
from typing import Any, Dict, Optional
import requests
from packages.core.schemas import Score


class NotificationDispatcher:
    """Formats and dispatches rich alert payloads to Slack and Discord."""

    @staticmethod
    def build_slack_payload(score: Score, alert_reason: Optional[str] = None) -> Dict[str, Any]:
        """Format Slack block kit message."""
        status_emoji = ":white_check_mark:" if score.overall_score >= 80 else ":warning:" if score.overall_score >= 50 else ":x:"
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} AgentReady Score Report: {score.url}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Overall Score:*\n{score.overall_score:.1f} / 100"},
                    {"type": "mrkdwn", "text": f"*Letter Grade:*\n`{score.grade}`"},
                    {"type": "mrkdwn", "text": f"*Algorithm Version:*\n`{score.version}`"},
                    {"type": "mrkdwn", "text": f"*Status Summary:*\n{score.summary}"},
                ],
            },
        ]

        if alert_reason:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f":bell: *Alert Trigger:* {alert_reason}"}],
            })

        return {"blocks": blocks}

    @staticmethod
    def build_discord_payload(score: Score, alert_reason: Optional[str] = None) -> Dict[str, Any]:
        """Format Discord rich embed message."""
        color = 0x22C55E if score.overall_score >= 80 else 0xEAB308 if score.overall_score >= 50 else 0xEF4444
        embed = {
            "title": f"AgentReady Score Report: {score.url}",
            "description": score.summary,
            "color": color,
            "fields": [
                {"name": "Overall Score", "value": f"{score.overall_score:.1f}/100", "inline": True},
                {"name": "Grade", "value": f"**{score.grade}**", "inline": True},
                {"name": "Version", "value": f"`{score.version}`", "inline": True},
            ],
            "footer": {"text": "AgentReady Platform Alert"},
        }
        if alert_reason:
            embed["fields"].append({"name": "Alert Trigger", "value": alert_reason, "inline": False})

        return {"embeds": [embed]}

    def send_slack(self, webhook_url: str, score: Score, alert_reason: Optional[str] = None) -> bool:
        """Send notification to Slack webhook."""
        try:
            payload = self.build_slack_payload(score, alert_reason)
            resp = requests.post(webhook_url, json=payload, timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def send_discord(self, webhook_url: str, score: Score, alert_reason: Optional[str] = None) -> bool:
        """Send notification to Discord webhook."""
        try:
            payload = self.build_discord_payload(score, alert_reason)
            resp = requests.post(webhook_url, json=payload, timeout=5.0)
            return resp.status_code in [200, 204]
        except Exception:
            return False


def dispatch_dlq_escalation(job: Any) -> bool:
    """Phase 16 Task 9 code-side: send a real outbound webhook for an
    escalated DLQ job.

    Reads SLACK_WEBHOOK_URL / DISCORD_WEBHOOK_URL from the environment.
    Returns True if at least one real webhook accepted the message,
    False otherwise (no URL configured, or delivery failed).
    No mocks, no in-memory stand-ins: when no URL is configured the
    function reports failure honestly instead of pretending to send.
    """
    import os

    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not slack_url and not discord_url:
        return False

    text = (
        f":rotating_light: AgentReady DLQ escalation\n"
        f"provider={job.provider} target={job.target_url} "
        f"retries={job.retry_count} error={job.error_message[:300]}"
    )
    sent = False
    try:
        if slack_url:
            resp = requests.post(
                slack_url, json={"text": text}, timeout=5.0
            )
            sent = sent or resp.status_code == 200
        if discord_url:
            resp = requests.post(
                discord_url, json={"content": text}, timeout=5.0
            )
            sent = sent or resp.status_code in (200, 204)
    except Exception:
        return False
    return sent
