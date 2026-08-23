"""Unit tests for multimodal content and visual agent readiness."""

from packages.core.checks.multimodal import check_multimodal
from packages.core.schemas import ComponentStatus


def test_multimodal_check_good_assets():
    html = """
    <html>
    <head>
      <meta property="og:image" content="https://example.com/preview.png">
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "name": "Product Walkthrough",
        "description": "Video explaining platform capabilities"
      }
      </script>
    </head>
    <body>
      <img src="/hero.png" alt="Architecture diagram of agent ready scoring system">
      <img src="/chart.png" alt="Benchmark graph showing citation share lift">
    </body>
    </html>
    """
    comp = check_multimodal(html)
    assert comp.name == "multimodal_readiness"
    assert comp.score >= 80.0
    assert comp.status == ComponentStatus.PASS
    assert comp.evidence["images_with_descriptive_alt"] == 2
    assert comp.evidence["video_objects_detected"] == 1


def test_multimodal_check_missing_alt():
    html = """
    <html>
    <body>
      <img src="/1.png">
      <img src="/2.png" alt="img">
    </body>
    </html>
    """
    comp = check_multimodal(html)
    assert comp.evidence["images_missing_alt"] == 2
    assert comp.score < 60.0
