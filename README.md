# AgentReady

> **Measure how ready your website is for AI agents.** Scan any site for `llms.txt`, structured data, token efficiency, and bot permissions — get a versioned score with concrete fixes.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Status: working MVP (local-first).** The scoring engine, CLI, dashboard, and probe pipeline are real and tested (186 passed). There is no hosted service, no signup page, and no SLA. The aspirational architecture (hosted SaaS, edge CDN, MCP gateway, billing) lives in `docs/target-architecture.md` — it is a plan, not the product.

---

## What it does today

- **4-signal scoring engine (`score_v0.1`)**: `llms_txt` (30%), `structured_data` (30%), `token_bloat` (20%), `bot_permissions` (20%). Weights: `packages/core/version.py`.
- **CLI (v1 surface)**: `scan`, `probe`, `generate`, `dashboard`, `auth`. Nothing else ships in v1.
- **Local dashboard**: `http://127.0.0.1:3000` with authenticated JSON API (`/api/scan`, `/api/scores`, `/api/probes`, `/api/domains`) plus public `/healthz`, `/readyz`, `/api/badge`.
- **Guarded probing**: budget enforcement, dedup cache, circuit breaker, and DLQ around every live LLM call. Dry-run is the default.
- **Real infrastructure (opt-in)**: Postgres 16 with row-level security + Redis 7 via `docker-compose.yml`. Default is SQLite + in-process cache for zero-dependency local use.

---

## Quickstart (verified)

```bash
pip install -e ".[dev]"
docker compose up -d            # optional: real Postgres + Redis (ports 5434/6380)

agentready scan https://example.com --min-score 80
agentready probe https://example.com --dry-run
agentready generate --url https://example.com --name "Example" --output-dir ./public
agentready dashboard --port 3000
```

With Postgres-backed tenancy:

```bash
AGENTREADY_STORAGE=postgres docker compose up -d
AGENTREADY_STORAGE=postgres agentready dashboard --port 3000
# POST /api/auth/register {"tenant_id": "acme"} -> {"api_key": "ark_live_..."}
# All /api/* (except /healthz, /readyz, /api/badge) require:
#   Authorization: Bearer ark_live_...
```

---

## Tests

```bash
pytest tests/ -q -m "not slow"        # default lane (~2 min)
pytest tests/ -q -m integration       # needs docker compose up -d
```

---

## What it is NOT (yet)

- No hosted API, no multi-user SaaS, no billing (Stripe receiver exists at `/api/webhooks/stripe` but no live account is connected).
- No deployed edge worker, no MCP-over-HTTP gateway, no GitHub PR bot in the v1 path.
- No SOC2, no pentest, no external audit. `FINAL_AUDIT_REPORT.md`, `LAUNCH_GATE.md`, and `GA_RELEASE_MANIFEST.md` are **superseded historical documents** — see the banner at the top of each file.
- The old `r ≥ 0.65` citation-correlation claim is **retracted**; the real-domain dataset is `data/real_domains_correlation.csv` (citation outcomes not yet measured).

---

## License

MIT © [Daryll Rebeiro](https://github.com/daryllrebeiro/agent-ready-kit)
