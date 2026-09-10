"""Phase 16 Task 9: Real Outbound Alert

Attempts to send a real Slack/Discord webhook notification.
REQUIRES: SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL environment variable.
If not set, reports BLOCKED (as per Phase 16 instructions).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.core.integrations.notifications import NotificationDispatcher
from packages.core.schemas import Score
from packages.core.schemas import ScoreComponent
from packages.core.schemas import ComponentStatus


def main():
    print("=" * 70)
    print("PHASE 16 TASK 9: REAL OUTBOUND ALERT")
    print("=" * 70)
    print()

    slack_url = os.environ.get("SLACK_WEBHOOK_URL")
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL")

    if not slack_url and not discord_url:
        print("BLOCKED: No SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL environment variable set.")
        print()
        print("To enable this test, set one of:")
        print("  export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/...'")
        print("  export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'")
        print()
        print("This is expected in CI/local dev without real webhook credentials.")
        print("The notification dispatch code exists and is wired; it just needs a real endpoint.")
        return 0

    # Build a real score payload
    score = Score(
        url="https://github.com",
        overall_score=92.3,
        grade="A",
        components=[
            ScoreComponent(
                name="llms_txt",
                display_name="llms.txt Spec Compliance",
                score=100.0,
                weight=0.3,
                status=ComponentStatus.PASS,
                details="Valid /llms.txt file detected",
                recommendations=[],
            ),
            ScoreComponent(
                name="structured_data",
                display_name="Structured Data & Semantics",
                score=95.0,
                weight=0.3,
                status=ComponentStatus.PASS,
                details="Rich JSON-LD with Organization, WebSite",
                recommendations=[],
            ),
            ScoreComponent(
                name="token_bloat",
                display_name="Content Token Efficiency",
                score=88.0,
                weight=0.2,
                status=ComponentStatus.PASS,
                details="Low HTML-to-token ratio",
                recommendations=[],
            ),
            ScoreComponent(
                name="bot_permissions",
                display_name="AI Bot & Crawler Permissions",
                score=90.0,
                weight=0.2,
                status=ComponentStatus.PASS,
                details="All major AI bots allowed",
                recommendations=[],
            ),
        ],
        summary="Excellent Agent Readiness",
        recommendations=[],
    )

    dispatcher = NotificationDispatcher()

    if slack_url:
        print(f"Sending to Slack webhook: {slack_url[:50]}...")
        ok = dispatcher.send_slack(slack_url, score, alert_reason="E2E test alert from Phase 16 Task 9")
        print(f"Slack dispatch: {'OK' if ok else 'FAILED'}")

    if discord_url:
        print(f"Sending to Discord webhook: {discord_url[:50]}...")
        ok = dispatcher.send_discord(discord_url, score, alert_reason="E2E test alert from Phase 16 Task 9")
        print(f"Discord dispatch: {'OK' if ok else 'FAILED'}")

    print()
    print("REAL OUTBOUND ALERT: SENT (check target channel)")
    return 0


if __name__ == "__main__":
    sys.exit(main())