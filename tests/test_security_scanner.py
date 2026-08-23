"""Unit tests for automated security scanner."""

from packages.core.security.scanner import SecurityScanner


def test_secret_scanner():
    scanner = SecurityScanner()
    clean_html = "<html><body><h1>Welcome to AgentReady</h1></body></html>"
    assert len(scanner.scan_content_for_secrets(clean_html)) == 0

    leaked_html = "<html><script>const key = 'sk-1234567890abcdef1234567890abcdef';</script></html>"
    findings = scanner.scan_content_for_secrets(leaked_html)
    assert len(findings) == 1
    assert findings[0]["type"] == "OpenAI API Key"


def test_robots_security_audit():
    scanner = SecurityScanner()
    robots_leaking = "User-agent: *\nDisallow: /admin\nDisallow: /internal/billing"
    findings = scanner.audit_robots_security(robots_leaking)
    assert len(findings) >= 2
    assert "Internal path disclosed" in findings[0]["issue"]
