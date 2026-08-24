"""Automated security posture, SSRF prevention, and vulnerability scanner for AgentReady configurations and CI."""

import ipaddress
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Tuple

SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE), "OpenAI API Key"),
    (re.compile(r"sk-ant-[a-zA-Z0-9]{20,}", re.IGNORECASE), "Anthropic API Key"),
    (re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE), "Google API Key"),
    (re.compile(r"pplx-[a-zA-Z0-9]{20,}", re.IGNORECASE), "Perplexity API Key"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE), "GitHub Personal Access Token"),
    (re.compile(r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+", re.IGNORECASE), "Slack Webhook URL"),
    (re.compile(r"https://discord\.com/api/webhooks/[0-9]+/[a-zA-Z0-9_-]+", re.IGNORECASE), "Discord Webhook URL"),
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
}


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

    @staticmethod
    def is_safe_public_url(url: str) -> Tuple[bool, str]:
        """Validates that a URL is a safe public endpoint, preventing SSRF attacks against internal networks."""
        try:
            parsed = urllib.parse.urlparse(url.strip())
            if parsed.scheme not in ["http", "https"]:
                return False, f"Invalid URL scheme '{parsed.scheme}'. Only http/https supported."

            hostname = (parsed.hostname or "").lower().strip()
            if not hostname:
                return False, "Missing hostname in URL."

            if hostname in BLOCKED_HOSTNAMES:
                return False, f"SSRF Blocked: Prohibited hostname/metadata endpoint '{hostname}'"

            # Check for direct IP address literals
            try:
                ip_obj = ipaddress.ip_address(hostname)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved:
                    return False, f"SSRF Blocked: Private or internal IP range '{hostname}'"
            except ValueError:
                # Not an IP literal (is a domain name like example.com)
                pass

            return True, "URL is safe public target."
        except Exception as e:
            return False, f"URL validation failed: {str(e)}"

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
                            findings = self.scan_content_for_secrets(content)
                            if findings:
                                violations.append({
                                    "file": file_path,
                                    "findings": findings,
                                })
                    except Exception:
                        pass
        return violations


if __name__ == "__main__":
    scanner = SecurityScanner()
    workspace_root = str(Path(__file__).parent.parent.parent.parent)
    leaks = scanner.scan_workspace_tree(workspace_root)
    if leaks:
        print(f"[SECURITY ALERT] {len(leaks)} files contained potential secrets!")
        for l in leaks:
            print(f" - {l['file']}: {l['findings']}")
        sys.exit(1)
    else:
        print("[PASS] Security CI Gate: Zero secrets detected in codebase.")
        sys.exit(0)
