"""Unit tests for semantic entity graph analyzer."""

from packages.core.checks.semantic_graph import check_semantic_graph
from packages.core.schemas import ComponentStatus


def test_semantic_graph_with_authorities():
    html = """
    <html>
    <head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "AgentReady",
        "sameAs": [
          "https://github.com/daryllrebeiro/agent-ready-kit",
          "https://en.wikipedia.org/wiki/Artificial_intelligence",
          "https://www.wikidata.org/wiki/Q11660"
        ],
        "publisher": {
          "@type": "Organization",
          "name": "AgentReady Inc."
        }
      }
      </script>
    </head>
    <body><h1>Semantic Entity Test</h1></body>
    </html>
    """
    comp = check_semantic_graph(html)
    assert comp.name == "semantic_graph"
    assert comp.score >= 70.0
    assert comp.status == ComponentStatus.PASS
    assert len(comp.evidence["verified_authorities"]) >= 2
    assert comp.evidence["connected_edges"] >= 1


def test_semantic_graph_empty():
    comp = check_semantic_graph("")
    assert comp.score == 0.0
    assert comp.status == ComponentStatus.FAIL
