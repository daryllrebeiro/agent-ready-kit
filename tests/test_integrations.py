"""Unit tests for Slack, Discord, and HMAC signed webhooks."""

from packages.core.integrations.notifications import NotificationDispatcher
from packages.core.integrations.webhooks import WebhookDispatcher, compute_webhook_signature
from packages.core.schemas import Score


def test_slack_and_discord_payload_builders():
    score = Score(
        url="https://agentready.dev",
        version="score_v0.1",
        overall_score=92.0,
        grade="A+",
        components=[],
        summary="High readiness",
        recommendations=["Keep up to date"],
    )

    slack_payload = NotificationDispatcher.build_slack_payload(score, alert_reason="Citation share +15%")
    assert len(slack_payload["blocks"]) >= 2
    assert "AgentReady Score Report" in slack_payload["blocks"][0]["text"]["text"]

    discord_payload = NotificationDispatcher.build_discord_payload(score)
    assert len(discord_payload["embeds"]) == 1
    assert discord_payload["embeds"][0]["title"] == "AgentReady Score Report: https://agentready.dev"


def test_hmac_webhook_signature():
    secret = "test_webhook_secret_key_12345"
    payload = b'{"event": "score.updated", "score": 85.0}'
    sig1 = compute_webhook_signature(payload, secret)
    sig2 = compute_webhook_signature(payload, secret)

    assert sig1 == sig2
    assert len(sig1) == 64
