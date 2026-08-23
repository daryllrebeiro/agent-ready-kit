"""Unit tests for multilingual and internationalization (i18n) checks."""

from packages.core.checks.i18n import check_multilingual
from packages.core.schemas import ComponentStatus


def test_multilingual_check_good():
    html = """
    <html lang="en">
    <head>
      <link rel="alternate" hreflang="es" href="https://example.com/es/">
      <link rel="alternate" hreflang="ja" href="https://example.com/ja/">
      <link rel="alternate" hreflang="x-default" href="https://example.com/">
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "Global Corp",
        "inLanguage": ["en", "es", "ja"]
      }
      </script>
    </head>
    <body>
      <h1>Global Operations</h1>
    </body>
    </html>
    """
    comp = check_multilingual(html)
    assert comp.name == "multilingual_readiness"
    assert comp.status == ComponentStatus.PASS
    assert comp.score >= 80.0
    assert comp.evidence["html_lang"] == "en"
    assert comp.evidence["has_x_default"] is True
    assert len(comp.evidence["hreflang_tags"]) >= 3


def test_multilingual_check_empty_and_minimal():
    comp_empty = check_multilingual("")
    assert comp_empty.status == ComponentStatus.FAIL

    comp_minimal = check_multilingual("<html><body><h1>Hello</h1></body></html>")
    assert comp_minimal.score < 50.0
