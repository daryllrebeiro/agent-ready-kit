# AgentReady (agent-ready-kit) — Architectural Review & Strategic Roadmap

**Reviewer:** Principal Software Architect / Staff Engineer
**Date:** 2026-09-08
**Scope:** Full repository audit — `packages/`, `apps/`, `tests/`, CI, packaging, and all claims-bearing documentation (`README.md`, `FEATURES.md`, `Plan.md`, `FINAL_AUDIT_REPORT.md`, `LAUNCH_GATE.md`).
**Method:** Every runtime entrypoint (`packages/cli/main.py`, `apps/web/server.py`, `apps/worker/runner.py`, `packages/mcp/server.py`) traced transitively; all 67 test files inventoried; full suite executed locally (`153 passed in 98.06s`); grep-verified wiring of every "hardening" subsystem; schema and migration code path-checked line by line.

---

## 1. Executive Summary & Health Assessment

### 1.1 What This Codebase Actually Is

AgentReady has **two architectures living in one repository**:

1. **A real, working product core** (~30 modules, transitively reachable from all four entrypoints): the 4-signal scoring engine (`Scorer` → `llms_txt` / `structured_data` / `token_bloat` / `bot_permissions`), a 12-command CLI, a local dashboard (`http.server` + vanilla JS), a cron-style worker, a stdio MCP server with regex-based injection filtering, and SQLite persistence. This core is genuinely functional and reasonably well-factored.
2. **An unwired "enterprise SaaS" façade** (~30 additional modules): budget enforcement, Redis dedup cache, Postgres RLS, Stripe billing, DLQ, circuit breakers, graduated rollout, hypercare, compliance purges, remote config, SLO alerting. These exist as in-process, in-memory, or mock-backed classes that are **imported by tests and by nothing else**. No runtime entrypoint calls them. There is no `redis-py`, no `psycopg`, no `stripe` SDK anywhere in the dependency tree (`pyproject.toml` declares only `pydantic`, `beautifulsoup4`, `requests`, `rich`).

The governance documents (`FINAL_AUDIT_REPORT.md` claiming **"92.5% / FULLY PRODUCTION-READY (GA APPROVED)"**, `LAUNCH_GATE.md` claiming **"APPROVED FOR GENERAL AVAILABILITY"**, `FEATURES.md` claiming a 7-signal `score_v0.2` engine) assert infrastructure that the code does not contain. This is the single most important fact in this review.

### 1.2 Health Scorecard

| Dimension | Grade | Justification |
|---|:---:|---|
| **Architecture (design)** | **B−** | Clean layering intent: pure `packages/core`, thin CLI, pluggable `BaseProbe` ABC, Pydantic contracts in `schemas.py`, fixture-driven checks. The *shape* is right. |
| **Architecture (fidelity)** | **D** | The documented architecture (Postgres RLS, Redis, Stripe, edge KV, OTel, PagerDuty) is emulated by in-memory stand-ins and is not composed into any runtime path. Claimed 7-signal scorer; wired scorer has 4 signals. |
| **Code Quality** | **C+** | Readable, typed, docstringed, small functions. But: duplicate package dirs (`edge-proxy`/`edge_proxy`, `sdk-python`/`sdk_python`), two divergent auth models, three weight/version schemes, dead imports, broad `except Exception` swallows, `hash()` for entity IDs. |
| **Maintainability** | **C−** | A contributor reading `FEATURES.md` cannot map claims to code. Hyphenated non-importable directories hold the only Cloudflare deploy artifacts. `temp-fixes/` sits at repo root. Truth drift between docs and code is now the project's dominant maintenance cost. |
| **Performance** | **C** | Sequential synchronous `requests` with no session reuse; each scan = 4 serial HTTP fetches; probes are sequential with `time.sleep(0.05)` even in dry-run; the "load benchmark" harness serializes all work behind one global lock, so `docs/benchmarks.md` capacity numbers are not measurements of anything. |
| **Test Coverage** | **B−** | 153/153 pass — verified. Broad per-module coverage and good fixture discipline (no live network in CI). But composition coverage is near zero: nothing tests the CLI→Scorer→DB→dashboard chain, no entrypoint-level tests of the web server or worker, and the "hardening" suites assert behavior of *mocks* (e.g., `MockRedisClient`, `MockPostgresConnection`), which is why broken code like `save_probe` (see §3) survives a 100% green suite. |
| **Security** | **C−** | Real SSRF validator exists (`scanner.py:is_safe_public_url`) but is **never called** by `Scorer.fetch_resource`, the web `/api/scan`, or MCP tools — the actual fetch boundaries. Web API is unauthenticated with `Access-Control-Allow-Origin: *`. Gemini API key is transmitted in the URL query string. MCP auth is opt-out by default (`auth_required=False`). API key material stored plaintext in `~/.agentready/credentials.json` with no permission tightening. |
| **Documentation Accuracy** | **F** | `FINAL_AUDIT_REPORT.md` cites as "verified" the exact components that are unwired, and cites drill results produced by `IncidentTabletopSimulator`, which **hardcodes `rehearsal_status: "COMPLETED_SUCCESSFULLY"`** (`apm.py:176–196`). Docs are polished, copious, and materially false. |

**Overall system maturity: Functional MVP core with an unwired enterprise façade.** Honest classification: **Active MVP / Prototype** — not Scaling Production, and definitively not GA. The one claim that checks out is the test count (153/153).

### 1.3 Architectural Philosophy — Strengths and Structural Risks

**Genuine strengths worth preserving:**

- **The `Plan.md` tenets are excellent** — "prove before you build," "boring technology first," "the scoring engine is the product: `packages/core` stays pure, versioned, delivery-agnostic." The core code actually honors tenet 3: `Scorer` and all checks are framework-free and run identically in CLI, worker, web, and MCP.
- **Pydantic contracts first** (`schemas.py`) with round-trip serialization tests — the right Phase-0 artifact, done correctly.
- **Fixture-based check testing** (`fixtures/good_site`, `bad_site`, `bloated_spa`, `malformed`) — deterministic, no network, fast.
- **Dry-run-as-default posture** on anything that spends money (`compare --dry-run` defaults true; probes simulate without keys) — a good safety instinct.
- **Fail-open instinct in the edge design** (both `worker.js` and `EdgeProxySimulator` wrap everything in try/passthrough) — the right instinct for a proxy in front of customer traffic.

**Fundamental structural risks:**

1. **Audit theater.** The readiness-score narrative (48% → 57.2% → 76.8% → 91.5% → 93% across "Phases 5–15") is a self-graded rubric whose "evidence" is unit tests of mocks. `IncidentTabletopSimulator` literally returns hardcoded success. Once one stakeholder discovers this, *every* claim in the repo — including the true ones — becomes suspect.
2. **No composition root.** The codebase has components but no place where they are assembled into the documented system. `BudgetEnforcer`, `CircuitBreaker`, `DeadLetterQueue`, `DistributedProbeCache`, `AuthManager`, `get_structured_logger`, `TraceContext` — grep confirms each is imported **only by tests** (except `AuthManager`, used by MCP with auth off). Resilience, cost control, and observability are therefore *properties of the test suite*, not of the product.
3. **Identity fragmentation.** Two edge-proxy packages (hyphenated dir holds `worker.js` + `wrangler.toml`; underscored dir holds the tested Python simulator — the deployable artifact and the tested artifact are in *different, diverging directories*). Two Python SDK dirs (one a byte-identical, unimportable copy). Two auth models (`auth/middleware.py` `ak_live_` vs `auth/keys.py` `ark_live_`). Three scoring weight sets (`config.py` v0.1, `drift.py` WEIGHTS_V0_2, `FEATURES.md` 7-signal v0.2). The CLI help text says keys look like `ark_live_...` while docs say `ak_live_...`.

### 1.4 Primary Bottlenecks (Top 3)

| # | Bottleneck | Consequence |
|---|---|---|
| **1** | **Claim–implementation gap.** GA/SOC2/RLS/Redis/Stripe claims are unsupported by code. | Every engineering, sales, and hiring decision made from this repo is made on false data. External publication (README badge, PyPI, HN launch) would create reputational and potentially legal exposure. |
| **2** | **Absent runtime composition.** No auth, budgets, caching, retries, DLQ, or structured telemetry in any live path; worker is a bare `while True: sleep` loop. | The product cannot safely take a single paying customer today: one `agentready probe --max-prompts 50` with keys set spends unbounded money with no quota, no dedup cache, no breaker. |
| **3** | **Correctness rot in the core scorer.** robots.txt group parser cross-contaminates rules (`bot_permissions.py:12–37`); migration silently drops 100% of score history (`migration.py:61`); `/api/badge` crashes with `NameError` on missing param (`server.py` — `Score` never imported). | The scoring number — the product's entire value proposition — is wrong for any site whose `robots.txt` groups bots (i.e., most real robots.txt files). |

---

## 2. In-Depth Engineering Review

### 2.1 Design Patterns & Modularity

**Cohesion / coupling in the wired core — good.** Checks are pure functions over fetched content; `Scorer` orchestrates fetch + check + aggregate; CLI is a thin arg-parsing shell; `StorageRepository` is the only stateful dependency and is injected. `BaseProbe` is a proper abstraction with four interchangeable implementations.

**Findings:**

- **Leaky abstraction — mock-coupled repository.** `PostgresRLSRepository` methods execute `?`-placeholder SQL (SQLite dialect) and delegate to `MockPostgresConnection` (a SQLite in-memory DB). Against a *real* psycopg connection every method fails on the placeholder style. The class name promises Postgres; the implementation is a simulation whose RLS "enforcement" is a post-fetch Python filter (`postgres_rls.py:169–184`) that only runs if you call `execute_rls_query` — which none of the repository's own methods do. The repository's methods just embed `tenant_id = ?` in SQL, i.e., ordinary application-level filtering. **The "database-enforced RLS, immune to application bugs" claim (`FEATURES.md` rationale #5) is not implemented anywhere.**
- **SQL injection vector in the tenant context.** `postgres_rls.py:210`: `cursor.execute(f"SET LOCAL app.tenant_id = '{tenant_id}';")` — string interpolation into SQL. On real Postgres with attacker-influenced tenant IDs this is injectable. Parameterization via `SET` is impossible; the correct primitive is `SELECT set_config('app.tenant_id', %s, true)`.
- **Broken untested method.** `postgres_rls.py:301` references `probe.model_name`; `ProbeResult` (`schemas.py:53–66`) has no such field → `AttributeError` on every call. Grep confirms **no test invokes `save_probe`**, which is how a 100%-green suite hides a crash.
- **Dead / duplicated modules.** `packages/edge-proxy/` (hyphenated, unimportable) holds the only real Cloudflare artifacts and a *stale* copy of the simulator (missing the `EdgeBotRateLimiter` hardening present in `packages/edge_proxy/simulator.py`). `packages/sdk-python/` is a byte-identical, `__init__`-less copy of `packages/sdk_python/`. `probes/scheduler.py` has a dead persistence loop: it iterates `prompt_run.get("probes", {})` (`scheduler.py:43`) while `runner.probe_prompt` returns key `"results"`, and calls `self.storage.save_probe_result(...)` — a method that does not exist (`StorageRepository` defines `save_probe_run`). The loop body never executes; velocity metrics are always zero.
- **Dead dependencies inside wired modules.** `fixer/engine.py` imports and instantiates `Scorer` (never used). `onboarding/wizard.py` imports `PostgresRLSRepository` (never used) and fakes its step 3 ("competitor benchmark" records a count without running anything, always returns `SUCCESS_FULLY_ONBOARDED`).
- **Two parallel auth models.** `auth/middleware.py` (AuthManager/AuthContext/UserRole, in-memory key store) vs `auth/context.py` + `pipeline/quotas.py` (TenantContext, different UserRole, in-memory quota dict with a comment claiming "atomic" increment — there is no lock). MCP uses the former; nothing runtime uses the latter.
- **Packaging namespace smell.** `pyproject.toml` ships top-level package `packages` (`include = ["packages*"]`), so `pip install agentready` puts a module literally named `packages` on the user's site-packages. It works, but it pollutes a generic namespace and signals the layout was never designed for distribution.

### 2.2 Data Architecture & Persistence

**Real storage today:** single-tenant SQLite, `agentready.db` created via `os.getcwd()` (`storage/db.py:7`) — meaning **the database file materializes in whatever directory the user happens to run the CLI from**. Schema is sensible (domains / scores / probe_runs, FKs, WAL, indexes on `(domain_id, created_at)`), and JSON-blob columns (`components_json`, `raw_response`) are a pragmatic v1 choice.

**Findings:**

- **Migration silently destroys data (P0).** `storage/migration.py:61` reads `s_dict["raw_json"]`, but the SQLite `scores` table column is `components_json`. The resulting `KeyError` is swallowed by the surrounding `except Exception` (`migration.py:65–66`), a warning is printed, and — because "reconciliation" is `stats >= 0` (`migration.py:69–72`) — the migrator reports **`is_reconciled = True` with zero scores migrated**. Any future SQLite→Postgres cutover using this code loses all score history while reporting success.
- **Non-deterministic IDs.** `postgres_rls.py:237,249,288` derive IDs from `abs(hash(...))`. Python randomizes string hashing per process (`PYTHONHASHSEED`), so the same domain gets different IDs across runs, and `hash()` collisions are unhandled. Use UUIDs.
- **Concurrency.** `get_connection` uses `check_same_thread=False` with no lock; the worker and web server each open their own connection per request (`StorageRepository()` re-runs `init_db` on **every** request in `apps/web/server.py` — an executescript per HTTP call). Fine for one local user; broken for the multi-tenant story the docs tell.
- **Cache tiers.** The real dedup cache that exists (`probes/cache.py`, in-process TTL dict) is never used at runtime; the documented one (`redis_cache.py` "Distributed Redis, 6h TTL") defaults to `MockRedisClient` and is never used at runtime. `DistributedProbeCache.get_tenant_usage` (`redis_cache.py:129–130`) reaches into the client's private `_counters` attribute — the abstraction only functions with the mock.
- **Budget counter semantics.** `budget_enforcer.py` does a read-then-increment on tenant usage (non-atomic check-then-act). Under the GIL with `MockRedisClient` the "zero double-billing" chaos test passes trivially; against real Redis this exact code races. Also, the global spend counter at `budget_enforcer.py:81` increments **before** the trip decision, so every tripped request permanently inflates the counter (side effect on the failure path).
- **Migration hygiene.** No schema-version table, no `alembic`, no forward-only migration tooling anywhere. The Postgres DDL (`postgres_rls.py:15–93`) is real SQL and reasonably well-designed (RLS policies, FKs, tenant FK on every table) — it is simply never executed against Postgres by anything.

### 2.3 Error Handling & Fault Tolerance

- **Swallow-first culture in wired paths.** `generator.py:35–36,52–53` — `except Exception: pass` on page fetches, silently degrading titles to path-derived guesses. `server.py` handlers catch broad `Exception` and return `{"error": str(e)}` with status 500, leaking raw internals — directly contradicting the "zero raw tracebacks" claim of `errors/humanized.py`, which itself is never used at runtime.
- **Resilience primitives exist but are unwired (see §1.4-2).** The provider calls in `probes/providers.py` have **no retry, no backoff, no circuit breaker, no cache, no budget check** — a 429/500 from OpenAI is recorded as a `ProbeResult` containing `"[API Error 429]"` as its *citation text* and flows into the DB as if it were a real answer. A single flaky provider pollutes citation-share statistics.
- **Fail-open correctness.** The edge simulators' fail-open envelope is genuinely well-formed (`simulator.py:57–66`, `worker.js:12–22`): any exception → passthrough. Two caveats: (a) shadow mode still 429s rate-limited bots *before* the shadow check (`simulator.py:88–107`), violating "shadow mode intercepts nothing"; (b) when origin itself is down, the "fail-open" path returns 502 — semantically correct (nothing to fail open *to*) but the docs describe this as zero-downtime guarantee without that caveat.
- **Worker fault tolerance.** `apps/worker/runner.py:91–95` is `while True: run_cycle(); sleep(interval)` — no jitter, no leader lock (two workers = duplicate probing and double API spend), no failure isolation between domains (a domain that crashes `score_url` is `continue`d, good, but a crash in the loop scaffolding kills the daemon), no DLQ, no alerting.
- **GitHub PR bot.** Commits files one-by-one via the Contents API (no tree-level commit, no rollback on partial failure — a mid-loop failure leaves a half-populated branch), branch names use `int(time.time())` (collision-prone on retry within the same second), and the idempotency set `_processed_hashes` is in-memory. The *guardrails* (opt-in registry, draft-by-default, content-hash dedup) are a genuinely good design.

### 2.4 Observability & Diagnostics

- `observability/logger.py` is a **good** design: ContextVar-based `trace_id`/`tenant_id`, JSON lines, `TraceContext` manager. **Zero runtime call sites.** The CLI, web, worker, and MCP all emit via `print`/`rich`/raw strings. There is no `/healthz` route in the web server; `health.py`'s "Redis readiness" pings `MockRedisClient` and therefore **cannot ever fail** — a readiness probe that reports UP by construction.
- `apm.py`'s `OpenTelemetryTraceExporterBridge` produces structurally plausible OTLP JSON but never sends it anywhere; `IncidentTabletopSimulator.run_edge_proxy_failclosed_drill` returns hardcoded `True/True/"COMPLETED_SUCCESSFULLY"` — this is the "verified tabletop rehearsal" cited as checkpoint 5.4 evidence in `FINAL_AUDIT_REPORT.md`.
- `docs/runbooks/edge-proxy-incident.md` instructs on-call to inspect a DLQ admin dashboard that **does not exist** (the web server has no DLQ endpoints) and to flip a kill switch that exists only as an env var in the never-deployed hyphenated directory.
- Metrics: `apm.py` keeps in-process lists of latencies. No counters, histograms, or exporters; no alert routing (the Slack/PagerDuty payload builders in `integrations/notifications.py` are the one genuinely real outbound integration in the tree — and nothing calls them outside tests).

### 2.5 Testing & Quality Assurance

**Verified: 153 tests, 153 passing, ~98s, offline.** That is the project's strongest real asset. Composition of the suite:

- **Good:** per-check unit tests against fixtures (including malformed input); schema round-trips; CLI command tests; provider dry-run tests; auth/BudgetEnforcer/DLQ behavior tests.
- **Structural weakness — tested-in-isolation, never-in-composition.** The "GA blocking" suites (`test_phase12_*`, `test_phase13_*`, `test_e2e_launch_matrix.py`) instantiate mocks and assert interactions with those mocks. `test_postgres_rls.py` never calls `save_probe` (hence the `model_name` crash is invisible). `test_load_chaos_harness.py` "verifies zero double-billing" across threads against `MockRedisClient`, where the GIL serializes the increments — this proves nothing about Redis. `test_benchmarks.py` drives `load_test.py`, whose global `db_lock` around every op (`load_test.py:60–65`) means the published "~1,200 ops/s" is serialized sequential access — yet `docs/benchmarks.md` markets these as capacity-planning numbers with Postgres/Redis graduation triggers.
- **No entrypoint-level tests.** Nothing boots `apps/web/server.py` and issues HTTP requests (the `/api/badge` `NameError` would be caught by one such test). Nothing runs the CLI against the fixture site end-to-end (`agentready scan fixtures/good_site/...` via a local HTTP fixture server). Nothing exercises the worker cycle function.
- **CI (`.github/workflows/ci.yml`)** is a real, sensible gate: 3-version Python matrix, install-then-pytest, and a repo secret scan step. Missing: `ruff` (a declared dev dependency, never run), any type checking, coverage thresholds, TS build for `sdk-ts`, a publish job, and any test of `action.yml` (which `pip install agentready` from PyPI — a package that must be verified/published, and whose hyphen/underscore import naming will bite at install time: the entrypoint `packages.cli.main:cli_entrypoint` only resolves because the top-level package is literally `packages`).
- **Flakiness risks:** `time.sleep(0.05)` per simulated probe plus ~98s wall time is acceptable now, but load/chaos suites will become the long pole; mark them with a slow-suite marker and split CI lanes.
- **sdk-ts has never been compiled.** No `dist/`, no lockfile, no tests (the "test" is a Python file-existence check, `test_sdk_ts.py`). It requires Node ≥18 (global `fetch`) but declares no `engines` field.

---

## 3. Critical Modifications & Technical Debt Remediation

### 3.1 Prioritized Debt Register

| Priority | Category | Component / Module | Issue / Technical Debt | Impact If Ignored | Recommended Fix |
|:---:|---|---|---|---|---|
| **P0** | Security / SSRF | `scorer.py:39–59`, `apps/web/server.py` (`/api/scan`), `mcp/server.py` tools | `is_safe_public_url` exists (`security/scanner.py:60–86`) but is **never invoked at any fetch boundary**. Any user-supplied URL is fetched server-side: private subnets, `169.254.169.254`, internal hostnames. | Hosted deployment = internal network scanner / cloud-metadata credential theft. Single most dangerous gap. | Call the validator in `Scorer.fetch_resource` (and MCP/web before dispatch); resolve DNS once and re-validate the IP (blocks hostname-of-internal-IP tricks); reject redirects to private targets. |
| **P0** | Correctness / Core product | `checks/bot_permissions.py:12–51` | `current_agents` accumulates across groups and is never reset on a new `User-agent` line. `Disallow: /` under `User-agent: *` also applies to every previously-seen specific bot; directives bleed between groups. | **Wrong scores for the majority of real robots.txt files** (most group `*` after specific bots). This corrupts the product's headline number. | Reset `current_agents` when a `User-agent` follows a directive (consecutive UA lines share a group). Add spec-compliance property tests (see §3.2-B). |
| **P0** | Data integrity | `storage/migration.py:61, 69–72` | Reads nonexistent `raw_json` column; `KeyError` swallowed; reconciliation is `stats >= 0` (always true). | Future cutover migrates **zero scores while reporting success**. Silent, total data loss. | Read the actual schema; reconcile by row counts + sampled checksums; fail loudly (`is_reconciled=False`, non-zero exit) on any exception; integration-test against a seeded SQLite file. |
| **P0** | Integrity / Governance | `FINAL_AUDIT_REPORT.md`, `LAUNCH_GATE.md`, `FEATURES.md`, `README.md` | Docs assert GA, 93% readiness, 7-signal `score_v0.2`, RLS/Redis/Stripe/SOC2/postgres "verified" — unsupported by code; drill results are hardcoded. | Reputational, legal, and engineering-decision hazard; every onboarding contributor is misinformed. | Rewrite as accurate MVP documentation (single source of truth, generated where possible); move aspirational architecture to a clearly-labeled "target state" doc; delete or rewrite the audit-score narrative. |
| **P1** | Auth / Multi-tenancy | `auth/middleware.py`, `auth/keys.py`, `apps/web/server.py` | Two key schemes (`ak_live_` vs `ark_live_`), in-memory key store (restart = all keys invalid), web API has **no auth at all**, `CORS: *`, CLI `auth login` stores a key nothing ever uses (plaintext, permissive file perms). | Cannot host anything; key storage is a local credential leak. | One key module; persist hashed keys in the DB; wire auth middleware into the web server (deny by default); tighten credential file to `0600`; delete the unused duplicate. |
| **P1** | Broken code | `apps/web/server.py` badge path | `Score` is referenced (`server.py:97`) but never imported → `NameError` (unhandled, connection reset) when `/api/badge` is hit without `?domain=`. | Public endpoint crash; trivially discovered by any port scan. | Import `Score`; return a 400 JSON error for missing domain; add handler-level error envelope. |
| **P1** | Broken code | `storage/postgres_rls.py:285–309` | `save_probe` uses `probe.model_name` (not on `ProbeResult`) → `AttributeError`; zero test coverage of the method. | Any future caller crashes; suite stays green — trust in tests erodes. | Add `model_name: Optional[str]` to `ProbeResult` (populate from provider metadata) **and** a test that calls `save_probe`. |
| **P1** | SQL safety | `storage/postgres_rls.py:210` | f-string interpolation of `tenant_id` into `SET LOCAL app.tenant_id = '...'`. | Injectable on real Postgres. | `SELECT set_config('app.tenant_id', %s, true)` parameterized; add an injection fixture test. |
| **P1** | Cost safety | `probes/providers.py`, `runner.py`, `worker/runner.py` | No budget check, dedup cache, circuit breaker, retry, or DLQ in the live probe path; a keyed `probe` run is unbounded spend. | First real customer with a loop = real money lost; provider outage corrupts citation stats. | Compose `BudgetEnforcer` + `DistributedProbeCache` + `CircuitBreaker` + `DeadLetterQueue` around provider calls (see §3.2-C). |
| **P1** | Security | `probes/providers.py:217` | Gemini API key in URL query string (`?key=...`). | Key leakage into proxy/access logs. | Use the `x-goog-api-key` header. |
| **P1** | Security | `mcp/server.py:39–48` | `auth_required=False` default; rate limiter is per-process in-memory; injection defense is a regex blocklist (NFKD does not defeat Cyrillic homoglyphs). | Anonymous MCP access by default; trivially bypassable filters; rate limit void across processes. | Default auth on; move rate limiting to shared store; treat blocklist as one layer plus output-sanitization and strict schema validation; document residual risk. |
| **P1** | Structure / Duplication | `packages/edge-proxy/`, `packages/sdk-python/` | Hyphenated dirs are unimportable duplicates; deployable Worker lives next to a *stale* simulator; SDK copy is dead bytes. | Divergence between tested and deployed artifacts; contributor confusion. | Merge: one `packages/edge_proxy/` (Python + `worker.js` + `wrangler.toml` together), delete `sdk-python/`, keep `sdk_python/` (or rename both to hyphen-free real packages). |
| **P1** | Observability | All entrypoints | Structured logger exists, zero call sites; no `/healthz`; "Redis readiness" pings a mock that cannot fail. | Production incidents are undebuggable; readiness is fiction. | Wire `get_structured_logger` + `TraceContext` into CLI/web/worker/MCP request paths; add real `/healthz`/`/readyz` routes to the web server; delete or truthfully relabel mock-based checks. |
| **P1** | Worker reliability | `apps/worker/runner.py:88–95` | `while True/sleep`, no leader lock, no jitter, no failure alerting. | Duplicate workers double-spend; silent daemon death. | DB-backed leader lease (or systemd timer/cron with `SingletonLock`), jitter, cycle summary log, dead-man alert (healthchecks.io-style ping). |
| **P2** | Packaging | `pyproject.toml` | Top-level package named `packages`; `action.yml` pip-installs from PyPI (unverified); version constants disagree (`CLI_VERSION 0.1.0`, `health.py "1.0.0"`, FEATURES `v1.0.0-GA`). | Ugly install footprint on customer machines; broken GitHub Action if unpublished; version confusion. | Restructure to `src/agentready/...` (or `agentready_core`), single version constant, add CI publish job + smoke-install test of the wheel. |
| **P2** | Schema drift | `config.py` vs `drift.py` vs `FEATURES.md` | Three weight sets; scorer default UA says `0.1.0`; `Score.version` default `score_v0.1`. | Score comparability across time breaks; users can't tell which algorithm produced a number. | One `weights.toml`/config source; version stamped from one constant; record weights in `Score.metadata`. |
| **P2** | Dead/stub code | `probes/scheduler.py`, `onboarding/wizard.py`, `compliance/retention.py`, `apm.py` tabletop, `fixer/engine.py` (unused Scorer), `probes/cache.py`, `pipeline/quotas.py` | Dead loops, fake steps, hardcoded drill results, stub purges ("Simulate execution", returns 0). | Maintenance noise; false capability signals. | Fix or delete. Purges: implement against the real repository or remove the module. Tabletop: remove or make it drive real components. |
| **P2** | Benchmarks | `benchmarks/load_test.py:60–67` | Global lock serializes all ops; `errors` counter raced across threads; numbers published as capacity planning. | Capacity decisions from meaningless data. | Remove the global lock (use per-connection or a pool), fix the counter, or relabel docs as smoke-test timing. |
| **P2** | Hygiene | `temp-fixes/`, `agentready.db` in CWD, `send_json_response(data: any)` typo, README badge pointing at `localhost:3000` | Root clutter; DB file lands in arbitrary CWDs; builtin `any` as annotation; broken badge in the first thing users read. | Poor first impressions; file pollution. | `.gitignore` already covers them — delete from working tree; default DB path → platform config dir; fix annotation; point badge at a real deployment or remove it. |

### 3.2 Refactorings for the Top P0/P1 Concerns

#### A. SSRF guard at the fetch boundary (`Scorer.fetch_resource`)

```python
# BEFORE — packages/core/scorer.py:39-59 (abridged)
def fetch_resource(self, url: str) -> Dict[str, Any]:
    try:
        resp = requests.get(url, headers=..., timeout=..., allow_redirects=True)
        ...

# AFTER — validate pre-fetch, and pin redirect destinations
from packages.core.security.scanner import SecurityScanner
import ipaddress, socket

class UnsafeTargetError(Exception): ...

def resolve_and_validate(self, url: str) -> None:
    ok, reason = SecurityScanner.is_safe_public_url(url)
    if not ok:
        raise UnsafeTargetError(reason)
    host = urlparse(url).hostname
    for family_ip in {info[4][0] for info in socket.getaddrinfo(host, None)}:
        ip = ipaddress.ip_address(family_ip)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise UnsafeTargetError(f"DNS resolves to private address {ip}")

def fetch_resource(self, url: str) -> Dict[str, Any]:
    try:
        self.resolve_and_validate(url)
    except UnsafeTargetError as e:
        return {"success": False, "status_code": None, "content": "",
                "headers": {}, "url": url, "error": f"unsafe-target: {e}"}
    resp = requests.get(url, headers=..., timeout=...,
                        allow_redirects=True, hooks={...})  # re-validate each redirect hop
    ...
```

Wire the same guard in `mcp/server.py` tool dispatch and `web/server.py` `/api/scan` (defense in depth: guard once at the boundary, again in the tool layer).

#### B. robots.txt group semantics (`bot_permissions.parse_robots_txt`)

```python
# BEFORE — packages/core/checks/bot_permissions.py:12-37 (abridged)
current_agents: List[str] = []
...
if key == "user-agent":
    ...
    current_agents.append(agent)      # BUG: never reset; rules bleed across groups
elif key == "disallow":
    for agent in current_agents:      # 'User-agent: *' + 'Disallow: /' now also
        rules[agent]["disallows"].append(val)   # blocks GPTBot seen earlier

# AFTER — consecutive UA lines form one group; a UA after a directive starts a new one
current_agents: List[str] = []
last_line_was_agent = False
...
if key == "user-agent":
    if not last_line_was_agent:       # new group begins
        current_agents = []
    agent = val.lower()
    rules.setdefault(agent, {"disallows": [], "allows": [], "crawl_delay": None})
    current_agents.append(agent)
    last_line_was_agent = True
else:
    last_line_was_agent = False       # directives close the UA block
    if key == "disallow":
        for agent in current_agents:
            rules[agent]["disallows"].append(val)
    ...
```

Add regression fixtures covering: `*` after specific bot; specific bot after `*`; multi-line UA groups (`User-agent: A\nUser-agent: B`); empty `Disallow:` (unblock). These cases exist in the wild constantly.

#### C. Compose the resilience stack into the probe path

```python
# BEFORE — packages/core/probes/runner.py (abridged): bare sequential provider calls
for provider in self.providers:
    res = provider.probe(prompt, dry_run=dry_run)

# AFTER — every live call passes through the guard stack that already exists
class ProbePipeline:
    def __init__(self, budget: BudgetEnforcer, cache: DistributedProbeCache,
                 breakers: Dict[str, CircuitBreaker], dlq: DeadLetterQueue):
        ...

    def run(self, ctx: TenantContext, provider: BaseProbe, prompt: str) -> ProbeResult:
        budget.check_and_reserve_budget(ctx.tenant_id, ctx.tier)          # P: pre-call stop
        cached = self.cache.get_cached_probe(ctx.tenant_id, provider.provider_name, prompt)
        if cached:
            return cached                                                # 6h dedup
        breaker = self.breakers[provider.provider_name]
        if not breaker.can_execute():
            raise ProviderCircuitOpen(provider.provider_name)
        try:
            result = provider.probe(prompt, dry_run=False)
            breaker.record_success()
            self.cache.store_cached_probe(ctx.tenant_id, provider.provider_name, prompt, result)
            return result
        except Exception as e:
            breaker.record_failure()
            self.dlq.push(ctx.org_id, provider.provider_name, ctx.target_url, prompt, str(e))
            raise
```

This is the payoff of the Phase-0 "pure core, swap orchestration" tenet: the pieces already exist and are individually tested — they were simply never assembled. The worker loop becomes `for domain: for prompt: ProbePipeline.run(...)` with a `replay_failed_jobs` pass at cycle end.

---

## 4. Optimization & Enhancement Recommendations

### 4.1 Performance & Scalability

- **HTTP connection pooling + parallel fetches.** Each `score_url` performs 4 sequential `requests.get` calls with fresh connections. Share one `requests.Session` per scan (TCP/TLS reuse) and fetch `robots.txt`/`llms.txt`/`llms-full.txt` concurrently (`ThreadPoolExecutor(3)`). Expected: scan wall-time cut roughly 2–3× with ~10 lines of change — the single highest-leverage performance fix in the codebase.
- **Kill `time.sleep(0.05)` in dry-run providers.** 4 providers × N prompts of pure sleep; a dry-run suite of 8 prompts wastes ~1.6s simulating latency nobody asked for. Make it opt-in (`--simulate-latency`).
- **Batch crawler already exists** (`crawler/batch.py`) — good. Promote it to back the worker's domain loop instead of the serial `for domain_url in domains`.
- **Async I/O decision.** The runtime is fully synchronous. Do not rewrite to asyncio now; wrap blocking calls in thread pools at the edges (web server). Revisit only when a hosted API lands (ADR-003).
- **Cache tiering.** Layer 1: in-process TTL dict for badge/report endpoints (already exists as `probes/cache.py` — actually wire it). Layer 2: the dedup cache in front of LLM calls (§3.2-C). SQLite query cache for `get_latest_score` on the badge path to stop re-scoring sites on every badge render.
- **SQLite for real scale.** `PRAGMA journal_mode=WAL` is already set; add `busy_timeout`, and stop re-running `init_db` per request in the web server (one repository instance, or a small pool).
- **Edge worker.** `worker.js` interception only covers `/llms.txt` (72 lines). If the "markdown CDN" story is real, add a routes manifest from the generator output (object storage / KV as origin for `/llms-full.txt` and rendered markdown), plus `caches.default` usage and `Cache-Control` propagation — currently absent.

### 4.2 Developer Experience (DX) & Tooling

- **Run the linter you already ship.** `ruff` is a dev dependency; CI never runs it. Add `ruff check` + `ruff format --check` as a failing CI step; add `[tool.ruff]` config (line-length, target py311) to `pyproject.toml`.
- **Type checking.** The codebase is annotated but never checked. Add `mypy --strict` on `packages/core` first (it's the purest), widen gradually. The `data: any` annotation bug and `probe.model_name` crash are exactly the class of defect mypy catches.
- **Config object.** Replace scattered `os.environ.get(...)` with a single `pydantic-settings` `Settings` (env prefix `AGENTREADY_`), injected once. Kills the "which env vars exist?" archaeology (`LAUNCH_GATE.md` lists 15+; `.env.example` documents 4).
- **DB path ergonomics.** Default `AGENTREADY_DB_PATH` to `~/.agentready/agentready.db` (platform-appropriate via `platformdirs`), not CWD.
- **Test suite lane split.** `pytest -m "not slow"` for the default lane; mark `test_load_chaos_harness`, `test_benchmarks`, phase-12/13 suites as `slow`, run them in a separate CI job. Keeps the feedback loop under ~30s.
- **Entrypoint smoke tests.** Boot `apps/web/server.py` on an ephemeral port and hit `/api/badge`, `/api/scan` (against a local fixture HTTP server); run `cli_entrypoint(["scan", ...])` in-process; run one `run_worker_cycle` against fixtures. These would have caught every P1 "broken code" item in §3.1.
- **TS SDK build.** Add `tsc --noEmit` + a publish dry-run to CI, `engines: { node: ">=18" }`, a lockfile, and one real test (vitest, against a mocked fetch) — or delete the package until it's real.
- **Pre-commit hooks** for ruff/mypy-fast/secret-scan (the scanner already runs in CI; make it local too). The Plan.md Phase 0 spec called for this; it was never done.

### 4.3 Security & Hardening Quick-Wins

- **SSRF wiring** (P0, §3.2-A) — one day of work, closes the worst hole.
- **MCP: default `auth_required=True`**, and reject the `api_key` in JSON-RPC *params* (currently accepted there — keys in message bodies get logged by clients/proxies); accept headers only on the transport.
- **Gemini header auth** (`x-goog-api-key`) instead of the URL query (§3.1).
- **Web server:** bind to `127.0.0.1` by default (currently `("", port)` — listens on all interfaces), drop `Access-Control-Allow-Origin: *` (same-origin dashboard needs none), add `X-Content-Type-Options: nosniff` on static responses.
- **Credential file perms** (`chmod 600` on `~/.agentready/credentials.json`) and a warning that the stored key is currently unused by any command.
- **Error responses:** stop echoing `str(e)` from internal exceptions to HTTP clients; map to the existing (unwired) `HumanizedError` payloads.
- **GitHub PR bot:** move to tree-level commits (create-blob → tree → commit) so partial failures can't strand half-written branches; namespace branch names with the content hash (idempotent retries).
- **Secrets scanning** is genuinely present in CI — good. Extend patterns to cover `ak_live_`/`dst_`/`ark_live_` key formats the system itself mints.

---

## 5. Future Engineering & Feature Roadmap

The strategic through-line: **close the claim–reality gap first, then scale what's real.** Nothing in Phase 3 is buildable on the current foundation because the foundation's documented load-bearing walls (auth, storage, quotas, observability) are not attached to the frame.

### Phase 1: Stabilization & Hardening (Short-Term: Weeks 1–4)

**Goal:** Make the codebase honest, the core scorer correct, and the live paths safe. No new features.

| Workstream | Items | Exit Criteria |
|---|---|---|
| **1.1 Truth reset** | Rewrite `README.md`/`FEATURES.md` to describe the actual MVP; move target architecture to `docs/target-architecture.md`; correct or remove `FINAL_AUDIT_REPORT.md`/`LAUNCH_GATE.md`; fix README badge (currently points at `localhost:3000`). | A new contributor reads the README and every claim maps to a file that exists. |
| **1.2 P0 fixes** | SSRF guard wiring (§3.2-A); robots.txt group parser fix + regression fixtures (§3.2-B); migration reconciliation fix + seeded-SQLite integration test; `/api/badge` NameError; delete hyphenated duplicate dirs. | New property/fixture tests green; a seeded migration run migrates and reconciles 100% of rows or fails loudly. |
| **1.3 Wire the existing guards** | Compose BudgetEnforcer + dedup cache + CircuitBreaker + DLQ into the probe path (§3.2-C); wire structured logging + `TraceContext` into CLI/web/worker/MCP; real `/healthz` in the web server; remove/replace mock-based readiness checks. | A keyed probe run with an exhausted budget refuses before spend; a forced provider 500 trips the breaker and lands in the DLQ; logs are JSON lines with trace IDs. |
| **1.4 CI quality gates** | `ruff check` + `ruff format --check` failing; mypy on `packages/core`; coverage floor on `packages/core` (≥80%); entrypoint smoke tests (web, CLI, worker); test lane split (`-m "not slow"`). | CI red on lint/type/coverage regressions; default lane < 60s. |
| **1.5 Hygiene** | Single version constant; one weights source (recorded into `Score.metadata`); DB path to config dir; delete dead code from §3.1 P2 row; fix Gemini key header; bind web server to localhost; MCP auth-on by default. | `grep` finds one key prefix, one version string, one weight table. |

### Phase 2: Architectural Scaling & Performance (Medium-Term: Month 2–3)

**Goal:** Replace emulated infrastructure with real, swappable implementations behind interfaces — one subsystem at a time, each shipped behind a feature flag with a rollback.

| Workstream | Items | Exit Criteria |
|---|---|---|
| **2.1 Real persistence** | Port/adapter split: `StorageProtocol` (repository.py already approximates this) with `SQLiteRepository` and a genuine `PostgresRepository` (psycopg 3, parameterized `set_config('app.tenant_id', %s, true)` per transaction, real RLS policies from the existing DDL). Alembic migrations with a schema-version table. | Tenant-isolation test suite passes against **real Postgres with RLS enforced** (the test that actually matters, per `Plan.md` Step 3.1.5). |
| **2.2 Real cache/counters** | `redis-py` client behind the existing `DistributedProbeCache` interface; atomic `INCR`-based budget reservation (Lua or `INCR`+check) replacing read-then-incr; TTLs unchanged. | Chaos test re-run against real Redis (or `fakeredis` with transactional semantics) shows no double-reservation under concurrency. |
| **2.3 API service** | Replace `http.server` with FastAPI (or Starlette) hosting the existing handler logic; auth middleware (persisted hashed keys) on every route; OpenAPI generated from code (retire the hand-written `openapi.json`); CORS scoped. | Authenticated API contract tests pass; unauthenticated route fuzzing rejected (reuse the phase-12 suite — this time against the real router). |
| **2.4 Worker maturity** | Leader lease, jitter, batch-crawler concurrency, DLQ replay pass per cycle, cycle metrics emitted; scheduler options decided via ADR-001. | Two concurrent workers → exactly one active cycle; forced provider outage completes a cycle with DLQ capture and zero lost probes. |
| **2.5 Packaging & distribution** | `src/`-layout rename to `agentready` namespace; PyPI publish workflow with Trusted Publishing + wheel smoke-install test; `action.yml` exercised in CI against a fixture site (composite action calling the repo's own action); TS SDK compiled, tested, published. | `pip install agentready && agentready scan <fixture>` works on a clean machine; GitHub Action demo run green. |
| **2.6 Performance** | Session reuse + parallel fetches in `Scorer`; dry-run latency made optional; badge/report result caching. | Scan p95 ≤ 2s on a fixture site locally; dashboard badge re-render served from cache. |

### Phase 3: Next-Generation Feature Expansion (Long-Term: Month 4–6+)

Each feature below is sequenced on the Phase-2 prerequisites that make it safe to build.

| Feature | Business / Technical Value | Complexity | Architectural Prerequisites |
|---|---|:---:|---|
| **7-Signal Scoring Engine (`score_v0.3`)** — wire `semantic_graph`, `multimodal`, `i18n` checks (already written and unit-tested, currently unreachable) into the Scorer; recalibrate weights on a real, checked-in dataset. | The single largest credibility gap between marketing and product; makes the score materially more predictive (semantic graph and i18n are genuine GEO signals). | **Medium** — checks exist; the work is weight calibration + empirical validation + a versioned rollout of the score. | Phase 1.5 (one weights source); a published calibration dataset + harness (today `agentready correlate` uses 5 hardcoded samples — the "r ≥ 0.65 across 250 domains" claim is unreproducible). |
| **Empirical Correlation Dataset & Public Methodology Page** | Converts the scoring engine from "vibes" to defensible product IP; the core moat for a GEO platform. | **Medium** | Live probe pipeline with cost controls (Phase 2.4), verbatim raw-response storage (already implemented — keep it). |
| **Hosted Multi-Tenant SaaS (signup → tracked domains → billing)** | Converts the CLI project into revenue. Real Stripe integration behind the existing webhook/signature logic (which is a decent start); usage metering from the real Redis counters. | **High** | Phase 2.1/2.3 (real Postgres + auth'd API). Managed auth provider (ADR-003) — do not build in-house. |
| **MCP Gateway over Streamable HTTP (SSE)** | MCP over stdio is local-only; hosted MCP is the distribution channel into agent ecosystems. | **Medium** | Phase 2.3 (API service) + Phase 1.5 (auth-on default). Keep read-only tool boundary; re-run the adversarial corpus as transport-level tests. |
| **Edge Proxy: Deployed Worker + KV Kill Switch + Shadow Analytics Pipeline** | The current `worker.js` is 72 lines and undeployed; this feature is the "zero-downtime markdown CDN" story. Shadow-mode log shipping (Workers Analytics Engine / Logpush) replaces the in-process `shadow_logs` list. | **High** | Merge edge dirs (Phase 1.2), object storage or KV for rendered markdown, `wrangler` deploy in CI, synthetic monitoring. Per-tenant kill switch in Workers KV before any customer traffic (Plan.md 3.3.6 was right — keep that discipline). |
| **Continuous Tracking + Citation-Drop Alerting** | Retention/recurring revenue driver; the anomaly detector and Slack payload builders already exist — unwired. | **Medium** | Phase 2.4 worker + real history in Postgres; notification dispatch with retries and a signed-customer-facing webhook (add expiry to the existing HMAC scheme — it currently has no replay window). |
| **Automated Remediation PRs (GA of the GitHub bot)** | Highest-leverage "fix" loop: scan → generate → draft PR. Guardrails (opt-in, draft, content-hash) are the good part; needs tree-level commits + a GitHub App installation flow. | **Medium** | Phase 2.5 packaging; sandboxed repo integration tests (a real throwaway repo in CI). |
| **WCAG 2.1 AA / Dashboard v2 (Next.js or keep server-rendered)** | Only if the dashboard becomes a hosted surface. The current vanilla-JS dashboard is honest for a local tool — resist rebuilding it as "glassmorphic v2.0" (per FEATURES.md) before there are users. | **Medium** | Hosted SaaS decision. |

**Explicitly deferred:** SOC2 Type 1, pentest engagement, sharding/partitioning, Kubernetes, multi-region. These are Phase-2+ of a *hosted* product that does not yet exist; starting them now is the same pattern that produced the façade.

---

## 6. Technical Decision Log (ADR Recommendations)

Four decisions must be made formally — with a written ADR in `docs/decisions/` — before Phase 2 begins. Each currently has competing half-implementations in the tree, which is precisely why they need deciding.

### ADR-001 — Probe pipeline orchestration: cron-loop vs. job queue vs. workflow engine

- **Context:** The worker is a `while True/sleep` loop. `Plan.md` 3.2.1 already scheduled this decision ("Celery+Redis vs Temporal — decide before building, not after") and it was never made; instead an unwired DLQ, circuit breaker, and scheduler daemon appeared.
- **Options:** (a) Keep the single-process loop + cron/systemd timers (boring, matches current scale); (b) Celery/Redis or RQ (retry semantics, DLQ, mature); (c) Temporal (durable workflows, best fit for "call 4 flaky APIs on a schedule," highest operational cost).
- **Recommendation:** (a) now with the §3.2-C guard stack, with an explicit trigger to (b) at ~50 tracked domains or the first missed-schedule incident. Write the trigger into the ADR — the plan document's own "boring technology first" tenet.
- **Consequences if deferred:** The unwired scheduler.py/DLQ divergence grows; cost controls stay un-testable end to end.

### ADR-002 — Persistence & tenancy: real Postgres+RLS vs. app-scoped SQLite/Postgres

- **Context:** Three repositories coexist: single-tenant SQLite (wired), `MultiTenantRepository` (app-level scoping, test-only), `PostgresRLSRepository` (mock-backed, broken `save_probe`, injectable `SET LOCAL`). The docs claim database-enforced RLS; the code has none.
- **Decision required:** When does Postgres become real, and is isolation enforced by RLS or by the query layer? If RLS: connection pooling strategy (PgBouncer transaction mode + `set_config(..., true)` — the pooling-reset test that exists must run against real PgBouncer, not a mock). If app-level: the tenant-isolation test suite becomes the only guard and must be a release blocker.
- **Recommendation:** Postgres + RLS at the moment a second tenant exists, Alembic from day one of that migration, and the existing (good) DDL in `postgres_rls.py:15–93` becomes the first Alembic revision — after the placeholder dialect and `model_name` bugs are fixed.
- **Consequences if deferred:** Every new feature multiplies the mock/repository divergence and the migration debt.

### ADR-003 — API surface & identity: framework and auth ownership

- **Context:** The web layer is a hand-rolled `SimpleHTTPRequestHandler` with no auth; two auth models exist (`AuthManager` in-memory, `TenantContext` + in-memory quotas); the CLI stores a key nothing uses; docs advertise an OpenAPI 3.1 portal, SDKs, and scoped share tokens.
- **Decision required:** (a) FastAPI vs. Starlette vs. keep-stdlib for the hosted API; (b) in-house API keys vs. managed auth (Clerk/Auth0/WorkOS) vs. both (managed for humans, API keys for machines — the likely correct answer); (c) the single key format (`ak_live_` vs `ark_live_` must die).
- **Recommendation:** FastAPI (Pydantic-native, generated OpenAPI, mature auth middleware), managed provider for human auth, hashed in-DB keys for machine auth, share tokens as a signed, expiring JWT-style format rather than the current in-memory map.
- **Consequences if deferred:** The web server cannot be exposed beyond localhost; the SDK story stays fake.

### ADR-004 — Documentation & readiness-claims policy

- **Context:** The project's most damaging artifact is not code — it is `FINAL_AUDIT_REPORT.md`. Its 93% score, "verified" checkpoint table, and hardcoded drill results have already shaped the repo's commit narrative ("achieve GA readiness (score 93.0%)" in commit `066bc86`).
- **Decision required:** What is the source of truth for capability claims, and what evidence standard must a claim meet? Options: (a) docs-generated-from-code (capabilities doc generated from import graph / entrypoint manifest); (b) claims require a linked, CI-executed test that exercises the claim **through a runtime entrypoint**; (c) status quo.
- **Recommendation:** (b), enforced by review checklist, plus an immediate one-time rewrite of the claim documents (Phase 1.1). A "readiness score" may only be cited when produced by a CI job that runs against real dependencies.
- **Consequences if deferred:** Repeat of the current state after the next feature push: green suite, red truth.

---

## Appendix: Verified Evidence Index

| Claim audited | Verdict | Evidence |
|---|---|---|
| "153 / 153 Tests Passing (100%)" | **TRUE** | Suite executed: `153 passed in 98.06s` |
| "Fully Production-Ready (GA), 92.5–93.0%" | **FALSE** | No runtime wiring of auth/budget/queue/cache; no Postgres/Redis/Stripe deps in `pyproject.toml`; hosting the web server would be an unauthenticated SSRF-capable endpoint |
| "Scoring engine `score_v0.2`, 7 signals, weights 20/25/20/15/10/5/5" | **FALSE** | `scorer.py:101` aggregates 4 components; `config.py` = v0.1 weights 30/30/20/20; `drift.py` has a third set; the other 3 checks are unreachable at runtime |
| "PostgreSQL RLS ... `SET LOCAL app.tenant_id`" | **EMULATED** | `postgres_rls.py` executes SQLite-dialect `?` SQL against `MockPostgresConnection`; `save_probe` crashes (`probe.model_name`); tenant context is f-string interpolated |
| "Distributed Redis 6-hour TTL cache" | **EMULATED** | Defaults to `MockRedisClient`; not imported by any runtime path; `redis-py` not a dependency |
| "Incident tabletop rehearsal" | **FABRICATED** | `apm.py:176–196` returns hardcoded `COMPLETED_SUCCESSFULLY` |
| "Load test / capacity planning (~1,200 ops/s)" | **INVALID** | `load_test.py:60–65` global lock serializes all operations |
| "External validation, SOC2, pentest (Phase 13)" | **ABSENT** | No artifacts, no engagement letters; only in-repo tests named after the phase |
| PyPI package `agentready` installable (README, `action.yml`) | **UNVERIFIED** | No publish workflow in repo; top-level package is named `packages`; `action.yml` installs from PyPI and is never tested |

---

*This review is itself subject to the standard it advocates: every finding above is traceable to a file and line in this repository, and the one quantitative claim it re-verified (the test suite) was executed, not assumed.*
