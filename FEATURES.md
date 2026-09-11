# AgentReady — What Exists (v1)

This document describes **only what is wired and tested**. The aspirational
7-layer architecture (hosted SaaS, edge CDN, MCP gateway, billing, PR bot)
lives in `docs/target-architecture.md` — it is a plan, not the product.

Test suite: **186 passed, 2 skipped** (`pytest tests/ -q -m "not slow"`).

---

## 1. Scoring engine (`score_v0.1`)

`packages/core/scorer.py` — 4 signals, weights in `packages/core/version.py`:

| Signal | Weight | Module |
|---|---|---|
| `llms_txt` | 0.30 | `packages/core/checks/llms_txt.py` |
| `structured_data` | 0.30 | `packages/core/checks/structured_data.py` |
| `token_bloat` | 0.20 | `packages/core/checks/token_bloat.py` |
| `bot_permissions` | 0.20 | `packages/core/checks/bot_permissions.py` |

SSRF-guarded fetching (blocklist + DNS pin + per-redirect re-validation).
Weights are stamped into every `Score.metadata["weights"]`.

## 2. CLI — `scan`, `probe`, `generate`, `dashboard`, `auth`

`packages/cli/main.py`. `probe` enforces budget pre-call (402 + humanized
error when exhausted). `compare`, `batch`, `correlate`, `fix`, `simulate`,
`report` exist in code but are **not** in the v1 surface.

## 3. Local dashboard + API — `apps/web/server.py`

Localhost-only by default. Authenticated (`Authorization: Bearer ark_live_…`):
`/api/domains`, `/api/scores`, `/api/probes`, `/api/scan`, `/api/probe`,
`/api/simulate`, `/api/compare`, `/api/report`, plus `POST /api/auth/register`
(dev key minting) and `POST /api/webhooks/stripe` (503 until
`STRIPE_WEBHOOK_SECRET` is set). Public: `/healthz`, `/readyz`, `/api/badge`.

## 4. Storage

Default: single-tenant SQLite (`StorageRepository`). With
`AGENTREADY_STORAGE=postgres`: tenant-scoped reads/writes through
`PostgresRLSRepository` on real Postgres 16 with engine-enforced RLS
(`TenantStore`). Migration ships SHA-256 checksum reconciliation.

## 5. Guarded probing

`ProbePipeline`: budget → dedup cache → circuit breaker → provider → DLQ.
Backends: real Redis 7 when reachable (`REDIS_URL`, default
`redis://127.0.0.1:6380/0`), in-process fallback flagged `.emulated`.
Worker runs DLQ replay with real re-execution + webhook escalation each cycle.

## 6. Auth

`AuthManager` (in-process, dev) or `PgAuthManager` (Postgres-persisted
hashes, expiry, revocation) under `AGENTREADY_STORAGE=postgres`.
Scoped read-only share tokens (`dst_…`). Keys never stored raw.

## 7. Explicitly NOT in v1

Hosted multi-tenant SaaS, live Stripe billing, deployed edge worker,
MCP-over-HTTP, GitHub PR bot, SOC2/pentest, 7-signal scorer, measured
citation correlation (`r ≥ 0.65` retracted; dataset:
`data/real_domains_correlation.csv`).
