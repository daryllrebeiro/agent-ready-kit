"""Automated security posture and vulnerability scanner for AgentReady configurations."""

import re
from typing import Any, Dict, List

SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE), "OpenAI API Key"),
    (re.compile(r"sk-ant-[a-zA-Z0-9]{20,}", re.IGNORECASE), "Anthropic API Key"),
    (re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE), "Google API Key"),
    (re.compile(r"pplx-[a-zA-Z0-9]{20,}", re.IGNORECASE), "Perplexity API Key"),
]


class SecurityScanner:
    """Audits configurations, HTML source, and robots.txt for security risks."""

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
