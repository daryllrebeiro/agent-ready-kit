"""Unit tests for GitHub PR Bot Safety Guardrails."""

from unittest.mock import MagicMock, patch
from packages.core.fixer.github_bot import GitHubPRBot, RepoOptInRegistry


def test_github_bot_opt_in_guardrail():
    registry = RepoOptInRegistry()
    bot = GitHubPRBot(github_token="fake_token", opt_in_registry=registry)

    # 1. Un-opted repository attempt
    res_unauthorized = bot.create_remediation_pr(
        repo="unauthorized/customer-repo",
        site_url="https://example.com",
        enforce_opt_in=True,
    )
    assert res_unauthorized["success"] is False
    assert "has not opted-in" in res_unauthorized["error"]

    # 2. Register opt-in permission
    registry.register_repo("authorized/customer-repo")
    assert registry.is_authorized("authorized/customer-repo") is True


def test_github_bot_diff_preview_generation():
    bot = GitHubPRBot(github_token="fake_token")
    custom_fixes = {
        "llms.txt": "# LLMs.txt\n> Guidance",
        "robots.txt": "User-agent: *\nAllow: /",
    }
    previews = bot.generate_diff_preview("https://example.com", custom_fixes=custom_fixes)
    assert "llms.txt" in previews
    assert "robots.txt" in previews
    assert "+# LLMs.txt" in previews["llms.txt"]
    assert "+User-agent: *" in previews["robots.txt"]


@patch("requests.get")
@patch("requests.post")
@patch("requests.put")
def test_github_bot_draft_pr_and_idempotency(mock_put, mock_post, mock_get):
    # Mock GitHub API responses
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"object": {"sha": "base123"}})
    mock_post.return_value = MagicMock(status_code=201, json=lambda: {"html_url": "https://github.com/org/repo/pull/1", "number": 1})
    mock_put.return_value = MagicMock(status_code=200)

    registry = RepoOptInRegistry()
    registry.register_repo("org/repo")
    bot = GitHubPRBot(github_token="fake_token", opt_in_registry=registry)

    custom_fixes = {"llms.txt": "# AgentReady Content"}

    # 1. First run creates draft PR
    res1 = bot.create_remediation_pr(
        repo="org/repo",
        site_url="https://example.com",
        custom_fixes=custom_fixes,
        as_draft=True,
    )
    assert res1["success"] is True
    assert res1["is_draft"] is True
    assert res1["pr_number"] == 1

    # 2. Duplicate run with identical content is skipped (Idempotency)
    res2 = bot.create_remediation_pr(
        repo="org/repo",
        site_url="https://example.com",
        custom_fixes=custom_fixes,
    )
    assert res2["success"] is True
    assert res2["status"] == "IDEMPOTENT_SKIPPED"
