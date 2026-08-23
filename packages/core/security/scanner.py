"""Automated security posture and vulnerability scanner for AgentReady configurations and CI."""

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE), "OpenAI API Key"),
    (re.compile(r"sk-ant-[a-zA-Z0-9]{20,}", re.IGNORECASE), "Anthropic API Key"),
    (re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE), "Google API Key"),
    (re.compile(r"pplx-[a-zA-Z0-9]{20,}", re.IGNORECASE), "Perplexity API Key"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE), "GitHub Personal Access Token"),
    (re.compile(r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+", re.IGNORECASE), "Slack Webhook URL"),
    (re.compile(r"https://discord\.com/api/webhooks/[0-9]+/[a-zA-Z0-9_-]+", re.IGNORECASE), "Discord Webhook URL"),
]


class SecurityScanner:
    """Audits configurations, HTML source, robots.txt, and repository files for security risks."""

    def scan_content_for_secrets(self, content: str) -> List[Dict[str, str]]:
        """Identify exposed API keys or credentials."""
        findings = []
        for pattern, label in SECRET_PATTERNS:
            matches = pattern.findall(content)
            for m in matches:
                masked = m[:6] + "..." + m[-4:] if len(m) > 10 else "***"
                findings.append({"type": label, "match": masked})
        return findings

    def audit_robots_security(self, robots_txt: str) -> List[Dict[str, str]]:
        """Check for sensitive internal path disclosures in robots.txt."""
        findings = []
        sensitive_paths = ["/admin", "/internal", "/staging", "/api/v1/internal", "/.env", "/backup", "/config"]

        for line in robots_txt.splitlines():
            line_str = line.strip().lower()
            if line_str.startswith("disallow:"):
                path = line_str.split(":", 1)[1].strip()
                for sensitive in sensitive_paths:
                    if path.startswith(sensitive):
                        findings.append({
                            "severity": "MEDIUM",
                            "issue": f"Internal path disclosed in robots.txt: '{path}'",
                            "recommendation": "Use authentication/firewall rules rather than robots.txt disallows for sensitive routes.",
                        })
        return findings

    def scan_workspace_tree(self, root_dir: str) -> List[Dict[str, Any]]:
        """Recursively scan codebase for accidental hardcoded secrets."""
        violations = []
        ignored_dirs = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", "tests"}

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for file in files:
                if file.endswith((".py", ".js", ".ts", ".html", ".json", ".md", ".env")):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            # Skip scanning .env.example with dummy placeholders
                            if file == ".env.example":
                                continue
                            findings = self.scan_content_for_secrets(content)
                            for finding in findings:
                                violations.append({
                                    "file": file_path,
                                    "secret_type": finding["type"],
                                    "snippet": finding["match"],
                                })
                    except Exception:
                        pass
        return violations


if __name__ == "__main__":
    scanner = SecurityScanner()
    workspace = os.getcwd()
    issues = scanner.scan_workspace_tree(workspace)
    if issues:
        print(f"[FAIL] Security CI Gate: Found {len(issues)} exposed secret(s) in codebase:")
        for iss in issues:
            print(f"  - {iss['file']}: {iss['secret_type']} ({iss['snippet']})")
        sys.exit(1)
    else:
        print("[PASS] Security CI Gate: Zero secrets detected in codebase.")
        sys.exit(0)
