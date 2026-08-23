# AgentReady 🤖🚀

[![AgentReady](http://localhost:3000/api/badge?domain=agentready.dev&label=Agent-Ready)](https://github.com/daryllrebeiro/agent-ready-kit)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen.svg)]()

> **The complete infrastructure and scoring platform between your website and AI agents.** Optimize your web properties for AI crawlers, LLM search engines (Perplexity, ChatGPT Search, Claude, Gemini), and autonomous agents.

---

## 🌟 Key Features

- 🎯 **Predictive Scoring Engine (`score_v0.2`)**: Evaluates `llms.txt`, JSON-LD Semantic Graphs, Content Token Density, and AI Bot Permissions.
- 🔍 **Multi-Model Citation Probing**: Tests live search visibility across OpenAI, Anthropic, Gemini, and Perplexity with prompt deduplication caching.
- ⚡ **Fail-Open Edge Proxy**: Cloudflare Worker markdown CDN delivering optimized context to AI bots with zero origin downtime risk.
- 🌐 **Hosted Model Context Protocol (MCP) Gateway**: Turnkey JSON-RPC MCP server with built-in prompt-injection sanitization.
- 🥊 **Competitor GEO Benchmarking (`agentready compare`)**: Head-to-head citation share battles, win rate calculations, and content gap discovery.
- 🛠 **Automated Site Fixer (`agentready fix`)**: Generates drop-in `/llms.txt`, `robots.txt`, and Schema.org templates in seconds.
- 🚀 **Official Client SDKs**: First-class Python and TypeScript/Node.js SDKs with full typing.
- 🏷 **Dynamic Vector SVG Badges**: Embeddable live badges for READMEs (`/api/badge?domain=...`).
- 🤖 **GitHub Action CI Gate**: Enforce minimum readiness scores on pull requests with markdown comments.

---

## 📦 Quickstart

### 1. Installation

```bash
pip install agentready
```

### 2. Scan Any Website

```bash
agentready scan https://example.com --min-score 80
```

### 3. Automatically Generate Fixes

```bash
agentready fix https://example.com --output-dir ./public
```

### 4. Benchmark Against Competitors

```bash
agentready compare https://mysite.com --vs https://competitor-a.com https://competitor-b.com
```

### 5. Launch the Local Dashboard

```bash
agentready dashboard --port 3000 --open
```

---

## 🐍 Python SDK

```python
from packages.sdk_python.agentready import AgentReadyClient

client = AgentReadyClient()

# Scan a website
score = client.scan("https://agentready.dev")
print(f"Overall Score: {score.overall_score} (Grade: {score.grade})")

# Generate SVG Badge
svg = client.get_badge_svg("https://agentready.dev")
```

---

## ☕ TypeScript SDK

```typescript
import { AgentReadyClient } from "@agentready/sdk";

const client = new AgentReadyClient({ baseUrl: "http://localhost:3000" });

const score = await client.scan("https://agentready.dev");
console.log(`Grade: ${score.grade}, Score: ${score.overall_score}`);
```

---

## 🧪 Running Tests

```bash
pytest tests/ -v
```

---

## 📄 License

MIT © [Daryll Rebeiro](https://github.com/daryllrebeiro/agent-ready-kit)
