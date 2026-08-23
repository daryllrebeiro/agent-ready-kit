"""Unit tests for GitHub Pull Request bot."""

from unittest.mock import MagicMock, patch
from packages.core.fixer.github_bot import GitHubPRBot


@patch("requests.get")
@patch("requests.post")
@patch("requests.put")
def test_github_pr_bot_flow(mock_put, mock_post, mock_get):
    # Mock branch ref lookup
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"object": {"sha": "mock_base_sha_12345"}}

    # Mock branch creation and PR creation
    mock_post.return_value.status_code = 201
    mock_post.return_value.json.return_value = {
        "html_url": "https://github.com/daryllrebeiro/agent-ready-kit/pull/42",
        "number": 42,
    }

    # Mock file commit
    mock_put.return_value.status_code = 201

    bot = GitHubPRBot(github_token="ghp_mock_token_12345")
    res = bot.create_remediation_pr(
        repo="daryllrebeiro/agent-ready-kit",
        site_url="https://agentready.dev",
        base_branch="main",
    )

    assert res["success"] is True
    assert res["pr_number"] == 42
    assert "https://github.com" in res["pr_url"]
    assert len(res["committed_files"]) >= 3
