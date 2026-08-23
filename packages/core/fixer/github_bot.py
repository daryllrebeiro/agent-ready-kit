"""Automated GitHub Pull Request bot creating remediation PRs with safety guardrails."""

import base64
import hashlib
import time
from typing import Any, Dict, List, Optional, Set
import requests

from packages.core.fixer.engine import FixerEngine


class RepoOptInRegistry:
    """Registry tracking explicit customer repository permissions."""

    def __init__(self):
        self._authorized_repos: Set[str] = set()

    def register_repo(self, repo: str):
        self._authorized_repos.add(repo.strip().lower())

    def is_authorized(self, repo: str) -> bool:
        return repo.strip().lower() in self._authorized_repos


class GitHubPRBot:
    """Automates creation of remediation Pull Requests on customer GitHub repositories with safety guardrails."""

    def __init__(
        self,
        github_token: str,
        base_api_url: str = "https://api.github.com",
        opt_in_registry: Optional[RepoOptInRegistry] = None,
    ):
        self.token = github_token.strip()
        self.base_url = base_api_url.rstrip("/")
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        self.fixer = FixerEngine()
        self.registry = opt_in_registry or RepoOptInRegistry()
        self._processed_hashes: Set[str] = set()

    def generate_diff_preview(self, site_url: str, custom_fixes: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Generates a text diff preview of remediation files for in-dashboard inspection."""
        fixes = custom_fixes or self.fixer.generate_all_fixes(site_url)
        previews = {}
        for filename, content in fixes.items():
            previews[filename] = f"--- /dev/null\n+++ b/{filename}\n@@ -0,0 +1,{len(content.splitlines())} @@\n" + "\n".join(f"+{line}" for line in content.splitlines())
        return previews

    def compute_content_hash(self, fixes: Dict[str, str]) -> str:
        serialized = "".join(f"{k}:{fixes[k]}" for k in sorted(fixes.keys()))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def create_remediation_pr(
        self,
        repo: str,
        site_url: str,
        base_branch: str = "main",
        custom_fixes: Optional[Dict[str, str]] = None,
        as_draft: bool = True,
        enforce_opt_in: bool = True,
    ) -> Dict[str, Any]:
        """Generate and commit fixes directly into a new draft pull request on repo."""
        clean_repo = repo.strip().lower()

        # Guardrail 1: Explicit per-repo opt-in check
        if enforce_opt_in and not self.registry.is_authorized(clean_repo):
            return {
                "success": False,
                "error": f"Repository '{repo}' has not opted-in to automated PR creation. Please authorize repository first.",
            }

        fixes = custom_fixes or self.fixer.generate_all_fixes(site_url)

        # Guardrail 2: Idempotency check via content hash
        c_hash = f"{clean_repo}:{self.compute_content_hash(fixes)}"
        if c_hash in self._processed_hashes:
            return {
                "success": True,
                "status": "IDEMPOTENT_SKIPPED",
                "message": "PR with identical remediation content already opened.",
            }

        branch_name = f"agentready/remediation-{int(time.time())}"

        # 1. Get base branch commit SHA
        ref_resp = requests.get(f"{self.base_url}/repos/{repo}/git/ref/heads/{base_branch}", headers=self.headers, timeout=10.0)
        if ref_resp.status_code != 200:
            return {"success": False, "error": f"Failed to get base branch '{base_branch}': {ref_resp.text}"}

        base_sha = ref_resp.json()["object"]["sha"]

        # 2. Create new branch
        create_branch_resp = requests.post(
            f"{self.base_url}/repos/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
            headers=self.headers,
            timeout=10.0,
        )
        if create_branch_resp.status_code not in [200, 201]:
            return {"success": False, "error": f"Failed to create branch '{branch_name}': {create_branch_resp.text}"}

        # 3. Commit files
        committed_files = []
        for filename, content in fixes.items():
            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            commit_payload = {
                "message": f"feat(agentready): add AI agent-ready {filename}",
                "content": encoded,
                "branch": branch_name,
            }
            file_resp = requests.put(f"{self.base_url}/repos/{repo}/contents/{filename}", json=commit_payload, headers=self.headers, timeout=10.0)
            if file_resp.status_code in [200, 201]:
                committed_files.append(filename)

        # 4. Open Pull Request (Draft by default for safety)
        pr_body = (
            f"## 🤖 AgentReady Automated Remediation Bundle\n\n"
            f"This PR was generated automatically by **AgentReady** to optimize `{site_url}` for AI search engines and autonomous agents.\n\n"
            f"### 📦 Changes Included:\n"
            f"- **`/llms.txt`**: Standardized Markdown context for LLMs\n"
            f"- **`robots.txt`**: Explicit crawler permissions for `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`\n"
            f"- **`schema-ld.json`**: Schema.org structured data starter template\n\n"
            f"---\n*Generated by [AgentReady](https://github.com/daryllrebeiro/agent-ready-kit)*"
        )

        pr_payload = {
            "title": "feat(ai-readiness): add AgentReady llms.txt and crawler permissions",
            "head": branch_name,
            "base": base_branch,
            "body": pr_body,
            "draft": as_draft,
        }

        pr_resp = requests.post(
            f"{self.base_url}/repos/{repo}/pulls",
            json=pr_payload,
            headers=self.headers,
            timeout=10.0,
        )

        if pr_resp.status_code in [200, 201]:
            pr_data = pr_resp.json()
            self._processed_hashes.add(c_hash)
            return {
                "success": True,
                "pr_url": pr_data.get("html_url"),
                "pr_number": pr_data.get("number"),
                "branch": branch_name,
                "is_draft": as_draft,
                "committed_files": committed_files,
            }

        return {"success": False, "error": f"Failed to create PR: {pr_resp.text}"}
