"""Unit tests for AI agent persona simulation engine."""

from packages.core.personas.simulator import AgentPersonaSimulator


def test_persona_simulator_all_archetypes():
    html = """
    <html>
    <head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Super AI SaaS",
        "offers": {
          "@type": "Offer",
          "price": "99.00",
          "priceCurrency": "USD"
        }
      }
      </script>
    </head>
    <body>
      <main>
        <h1>Super AI SaaS Documentation</h1>
        <h2>API Reference</h2>
        <pre><code>curl https://api.mysaas.com/v1/data</code></pre>
        <table>
          <tr><th>Feature</th><th>Tier</th></tr>
          <tr><td>Probes</td><td>Growth</td></tr>
        </table>
        <a href="https://github.com/daryllrebeiro">GitHub Repo</a>
        <a href="https://docs.mysaas.com">Docs</a>
        <a href="https://status.mysaas.com">Status</a>
      </main>
    </body>
    </html>
    """
    sim = AgentPersonaSimulator()
    res = sim.simulate_all_personas("https://mysaas.com", html=html)

    assert res["overall_compatibility"] > 40.0
    assert "research_agent" in res["personas"]
    assert "commerce_agent" in res["personas"]
    assert "coding_agent" in res["personas"]
    assert "local_discovery_agent" in res["personas"]

    assert res["personas"]["commerce_agent"]["compatibility_score"] >= 60.0
    assert res["personas"]["coding_agent"]["compatibility_score"] >= 40.0
