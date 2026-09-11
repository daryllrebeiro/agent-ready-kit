"""Unit tests for GitHub Pull Request bot (tree-level atomic commits)."""

from unittest.mock import MagicMock, patch

from packages.core.fixer.github_bot import GitHubPRBot


def _mock_github_tree_api(mock_get, mock_post):
    """Wire mocks for the tree API: ref -> blobs -> tree -> commit -> branch -> PR."""
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"object": {"sha": "mock_base_sha_12345"}}

    def post_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        if url.endswith("/git/blobs"):
            resp.json.return_value = {"sha": "mock_blob_sha"}
        elif url.endswith("/git/trees"):
            resp.json.return_value = {"sha": "mock_tree_sha"}
        elif url.endswith("/git/commits"):
            resp.json.return_value = {"sha": "mock_commit_sha"}
        elif url.endswith("/git/refs"):
            resp.json.return_value = {}
        elif url.endswith("/pulls"):
            resp.json.return_value = {
                "html_url": "https://github.com/daryllrebeiro/agent-ready-kit/pull/42",
                "number": 42,
            }
        else:
            raise AssertionError(f"unexpected POST {url}")
        return resp

    mock_post.side_effect = post_side_effect


@patch("requests.get")
@patch("requests.post")
def test_github_pr_bot_flow(mock_post, mock_get):
    _mock_github_tree_api(mock_get, mock_post)

    bot = GitHubPRBot(github_token="ghp_mock_token_12345")
    bot.registry.register_repo("daryllrebeiro/agent-ready-kit")
    res = bot.create_remediation_pr(
        repo="daryllrebeiro/agent-ready-kit",
        site_url="https://agentready.dev",
        base_branch="main",
    )

    assert res["success"] is True
    assert res["pr_number"] == 42
    assert "https://github.com" in res["pr_url"]
    assert len(res["committed_files"]) >= 3

    # Atomicity: exactly one tree and one commit for all files.
    urls = [c.args[0] for c in mock_post.call_args_list]
    assert sum(u.endswith("/git/trees") for u in urls) == 1
    assert sum(u.endswith("/git/commits") for u in urls) == 1
    # No per-file Contents API calls remain.
    assert not any("/contents/" in u for u in urls)

    # Content-hash branch namespace (deterministic, not timestamped).
    assert res["branch"].startswith("agentready/remediation-")
    assert "remediation-1" not in res["branch"]  # not a bare timestamp
    res2 = bot.create_remediation_pr(
        repo="daryllrebeiro/agent-ready-kit",
        site_url="https://agentready.dev",
        base_branch="main",
    )
    assert res2["status"] == "IDEMPOTENT_SKIPPED"


@patch("requests.get")
@patch("requests.post")
@patch("requests.delete")
def test_github_pr_bot_rolls_back_branch_on_pr_failure(mock_delete, mock_post, mock_get):
    _mock_github_tree_api(mock_get, mock_post)

    def failing_pr(url, **kwargs):
        if url.endswith("/pulls"):
            resp = MagicMock()
            resp.status_code = 422
            resp.text = "Validation Failed"
            return resp
        return _post_one(url, **kwargs)

    def _post_one(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"sha": "mock_sha"}
        return resp

    mock_post.side_effect = failing_pr
    mock_delete.return_value.status_code = 204

    bot = GitHubPRBot(github_token="ghp_mock_token_12345")
    bot.registry.register_repo("daryllrebeiro/agent-ready-kit")
    res = bot.create_remediation_pr(
        repo="daryllrebeiro/agent-ready-kit",
        site_url="https://agentready.dev",
        base_branch="main",
    )

    assert res["success"] is False
    assert "Failed to create PR" in res["error"]
    # Rollback: the branch ref created for the atomic commit is deleted.
    assert mock_delete.called
    del_url = mock_delete.call_args.args[0]
    assert (
        del_url.endswith(res.get("branch", "agentready/remediation-") or "x") or "git/refs/heads/" in del_url
    )
