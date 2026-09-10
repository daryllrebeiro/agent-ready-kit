# AgentReady — Implementation Plan (derived from REVIEW_AND_ROADMAP.md)

**Source:** `REVIEW_AND_ROADMAP.md` (2026-09-08) + `Plan.md` v2 + codebase verification
**Current truth:** Functional MVP core (4-signal scorer, 12-command CLI, stdio MCP, SQLite, local dashboard) + unwired enterprise façade. 153/153 tests pass but composition coverage ≈ 0.
**Goal of this plan:** Close the claim–reality gap first, make live paths safe, then scale what's real. No new features until Phase 0/1 exit.
**Status:** Draft for execution — start at Sprint 0.

---

## 0. How this plan improves on REVIEW_AND_ROADMAP.md §5

The review's Phase 1/2/3 direction is correct. This plan makes it executable by adding what the review left implicit:

1. **Sprint 0 (Days 1–3) truth freeze first** — docs rewrite + claim policy + version/weights/auth single-sourcing *before* any code fix, so no new work re-diverges. Review bundled this into Phase 1.1; it must be a blocking gate.
2. **Composition-root-first ordering** — review §3.2-C shows *what* to compose but not *where*. This plan defines `ProbePipeline`, `Settings`, `StorageProtocol` interfaces up front (Milestone 1), then wires guards through them. Prevents a second façade.
3. **Test-pyramid fix ordered before fixes** — entrypoint smoke tests (web/CLI/worker) land in M1, *before* P0 fixes, so P0 fixes are proven through a live path, not another unit test of a mock.
4. **File-level backlog with estimates + dependencies** — review has a debt register; this plan converts every P0/P1 into an assignable task with files, DoD, and test.
5. **Risk-gated Phase 2** — real Postgres/Redis/FastAPI only start after M1 exit criteria (SSRF closed, robots fixed, migration honest, auth-on-localhost). Review implies this; this plan enforces it with a checklist.
6. **Explicit Do-Not-Build list** — SOC2, K8s, sharding, dashboard v2, MCP actions, 7-signal scorer are deferred with trigger conditions. Stops façade regrowth.
7. **Docs-as-code enforcement (ADR-004 concrete)** — claim → test-through-entrypoint rule + CI check (`docs_claims_test.py` / import-graph lint) so `FINAL_AUDIT_REPORT.md`-style drift cannot recur.

---

## 1. Ground truth table (what is real vs emulated — do not re-litigate)

| Capability claimed | Verdict | Runtime evidence | Plan action |
|---|---|---|---|
| 4-signal scorer (`llms_txt`, `structured_data`, `token_bloat`, `bot_permissions`) | REAL, BUGGY | `packages/core/scorer.py:101-154`, `config.py:8-13` (v0.1 30/30/20/20) | Fix P0s, keep as `score_v0.1` |
| 7-signal `score_v0.2` (20/25/20/15/10/5/5) + semantic/i18n/multimodal | UNWIRED | checks exist (`semantic_graph.py`, `multimodal.py`, `i18n.py`) but `scorer.py` never calls them; `drift.py` has 3rd weight set | Defer to Phase 3; single-source weights in M1 |
| SSRF validator | EXISTS, UNWIRED | `security/scanner.py:is_safe_public_url` never called by `scorer.fetch_resource`, `/api/scan`, MCP | P0 wire in M1 |
| robots.txt parser | WIRED, WRONG | `bot_permissions.py:12-37` cross-contaminates groups | P0 fix in M1 |
| SQLite persistence | REAL, single-tenant | `storage/db.py:7` (`os.getcwd()/agentready.db`), `repository.py` | Keep; fix DB path; add version table |
| SQLite→Postgres migrator | BROKEN, LYING | `migration.py:61` reads `raw_json` (real col `components_json`), `69-72` always `True` | P0 fix in M1 |
| Postgres RLS repo | EMULATED + BROKEN | `postgres_rls.py` SQLite-dialect `?` vs real psycopg `%s`, `SET LOCAL` f-string `:210`, `save_probe` crash (`probe.model_name`) | Quarantine in M1; real impl in Phase 2 only |
| Redis dedup cache / BudgetEnforcer / CircuitBreaker / DLQ | EXIST, UNWIRED | imported only by tests; no call in `probes/providers.py`, `runner.py`, `worker/runner.py` | Compose via `ProbePipeline` in M1 (in-process adapters), real Redis in Phase 2 |
| Web dashboard + `/api/badge` | REAL, BROKEN | `apps/web/server.py:97` `Score` NameError; no auth; `("", port)` binds all interfaces; `CORS: *` | Fix + localhost + auth stub in M1 |
| MCP server | REAL, UNSAFE DEFAULTS | `packages/mcp/server.py:39-48` `auth_required=False`; regex blocklist | Default auth on in M1; full gateway in Phase 3 |
| Structured logger / OTel / DLQ / health | EXIST, UNWIRED | `observability/logger.py` 0 call sites; `apm.py:176-196` hardcoded drill; `health.py` pings mock | Wire logger + real `/healthz` in M1; delete/retag mock checks |
| `FINAL_AUDIT_REPORT.md` 92.5% / `LAUNCH_GATE.md` GA / `FEATURES.md` v1.0.0-GA | FALSE | No Postgres/Redis/Stripe deps in `pyproject.toml` (only pydantic/bs4/requests/rich) | Rewrite in Sprint 0 |
| Packaging (`pip install agentready`, `action.yml`) | UNVERIFIED | Top-level pkg literally `packages`, no publish workflow | Smoke-install test in M1; `src/` rename in Phase 2 |

---

## 2. Milestones & exit gates (no phase starts until prior gate is green)

### Sprint 0 — Truth Reset (Days 1–3) — BLOCKS ALL CODE

| # | Task | Files | DoD |
|---|---|---|---|
| 0.1 | Rewrite `README.md`: MVP-only claims, real quickstart (`pip install -e .` + fixture scan), remove localhost badge + `score_v0.2`/GA language | `README.md` | Every claim links to a file; badge either real or removed |
| 0.2 | Demote `FEATURES.md` → `docs/target-architecture.md` (aspiration) + new 2-page `FEATURES.md` describing wired 4-signal core only | `FEATURES.md`, `docs/target-architecture.md` | `grep -r "score_v0.2\|RLS\|Stripe\|SOC2" FEATURES.md README.md` = 0 hits for present-tense claims |
| 0.3 | Quarantine governance docs: rename `FINAL_AUDIT_REPORT.md` → `docs/historical/FINAL_AUDIT_REPORT.v1-ARCHIVED.md` with header banner "SUPERSEDED — mock-backed, do not cite"; same for `LAUNCH_GATE.md`, `GA_RELEASE_MANIFEST.md` | 3 files + `docs/historical/` | Banner present; root no longer asserts GA |
| 0.4 | Adopt claim policy (ADR-004): every capability claim must link a CI-executed test **through a runtime entrypoint** | `docs/decisions/ADR-004-claims-policy.md`, `CONTRIBUTING.md` checklist | Policy merged; PR template updated |
| 0.5 | Single-source constants: one `VERSION`, one `KEY_PREFIX`, one `WEIGHTS` source | `packages/core/version.py` (new), `config.py`, `drift.py`, `packages/cli/main.py`, `health.py` | `grep` finds 1 version string, 1 key prefix, 1 weight table; `Score.metadata.weights` stamped |

**Exit gate S0:** reviewer who has not read the old docs can map every README sentence to code. If not, do not proceed.

### Milestone 1 — Stabilization & Safe Live Paths (Weeks 1–4) — THE CORE OF THIS PLAN

#### M1a. Safety + correctness P0s (parallel, Days 4–10)

| # | Task (P0) | Files & change | Test (must be new) |
|---|---|---|---|
| 1.1 | **SSRF guard at all fetch boundaries** — `resolve_and_validate()` pre-fetch (existing `is_safe_public_url` + DNS-pin + private-IP reject) + per-redirect re-validation; wire in `Scorer.fetch_resource`, `web/server.py:/api/scan`, `mcp/server.py` dispatch | `packages/core/scorer.py:39-59`, `packages/core/security/scanner.py:60-86`, `apps/web/server.py`, `packages/mcp/server.py` | `tests/test_ssrf_wired.py`: parametrized SSRF URLs (`169.254.169.254`, `metadata.google.internal`, `http://127.0.0.1`, redirect-to-private via local fixture server) assert `success=False` + `unsafe-target`; no real network |
| 1.2 | **robots.txt group semantics fix** — reset `current_agents` on UA-after-directive; consecutive UA lines = one group (review §3.2-B exact patch) | `packages/core/checks/bot_permissions.py:12-37` | `tests/test_robots_groups.py`: `*`-after-specific, specific-after-`*`, multi-UA group, empty `Disallow:`; golden fixtures from real-world robots.txt |
| 1.3 | **Migration honesty** — read `components_json` (not `raw_json`), reconcile by row counts + sampled checksum, fail loudly | `packages/core/storage/migration.py:61,69-72`, `storage/db.py` schema | `tests/test_migration_seeded.py`: seeded SQLite (N domains/scores) → migrate → assert counts + spot-check `overall_score` equality; corrupt-fixture case asserts `is_reconciled=False` + nonzero exit |
| 1.4 | **Badge crash + error envelope** — import `Score`, 400 on missing `domain`, JSON error envelope, no `str(e)` leak | `apps/web/server.py:89-112` | Entrypoint test hits `/api/badge` without `?domain=` → 400 JSON (see M1c) |

#### M1b. Composition root — wire what exists (Days 8–18, depends on 1.1 partial)

> Improvement over review: do not sprinkle `BudgetEnforcer` calls ad hoc. Create one seam.

| # | Task (P1) | Files & change | Test |
|---|---|---|---|
| 1.5 | **`ProbePipeline` seam** — new `packages/core/probes/pipeline.py`: `check_and_reserve_budget → cache.get → breaker.can_execute → provider.probe → breaker.record_* → cache.store → dlq.push on failure`. In-process adapters now; Redis impl later behind same interface | New `pipeline.py`; `probes/runner.py`, `probes/cache.py`, `pipeline/budget_enforcer.py`, `pipeline/circuit_breaker.py`, `pipeline/dlq.py`, `probes/redis_cache.py` (interface only) | `tests/test_probe_pipeline.py`: exhausted budget refuses pre-spend (no provider call); forced 500 trips breaker + DLQ entry; cached prompt makes zero provider calls |
| 1.6 | **Worker hardening (minimal)** — DB leader lease (or `SingletonLock` + jitter), per-domain isolation, DLQ replay pass at cycle end, cycle summary via structured logger | `apps/worker/runner.py:88-95`, `crawler/batch.py` for domain loop | `tests/test_worker_cycle.py`: 2 workers → 1 active cycle; provider outage → cycle completes with DLQ capture |
| 1.7 | **Structured logging + health** — `get_structured_logger` + `TraceContext` in CLI/web/worker/MCP request paths; real `/healthz` (+ `/readyz` checking SQLite only); delete/retag mock-based readiness | `observability/logger.py`, all 4 entrypoints, `observability/health.py`, `apps/web/server.py` | Assert JSON lines with `trace_id`; `/healthz` 200; `/readyz` fails when DB path unwritable |
| 1.8 | **Auth + transport quick-wins** — one key module (`ark_live_` vs `ak_live_` — pick one, delete other), hashed keys persisted in DB (not in-memory), web binds `127.0.0.1` + drops `CORS: *` + `nosniff`, MCP `auth_required=True` default, Gemini `x-goog-api-key` header, creds file `0600` | `auth/middleware.py`, `auth/keys.py`, `auth/context.py`, `pipeline/quotas.py`, `apps/web/server.py`, `packages/mcp/server.py`, `probes/providers.py:217`, `packages/cli/auth.py` | `tests/test_auth_wired.py`: unauth web request → 401; MCP anon → rejected; key restart persistence |

#### M1c. Quality gates + hygiene (parallel with M1b)

| # | Task (P1/P2) | Files & change | Test |
|---|---|---|---|
| 1.9 | **Entrypoint smoke suite** (highest ROI) — boot web on ephemeral port vs local fixture HTTP server; `cli_entrypoint(["scan",...])` in-process; one `run_worker_cycle` vs fixtures | `tests/test_entrypoints_smoke.py` (new), `fixtures/` | Catches all §3.1 P1 broken-code class; required green in CI default lane |
| 1.10 | **CI gates** — `ruff check` + `format --check` failing, `mypy` on `packages/core`, coverage floor ≥80% on `packages/core`, lane split (`-m "not slow"` default <60s) | `.github/workflows/ci.yml`, `pyproject.toml [tool.ruff]`, `pytest -m` markers | CI red on lint/type/coverage regression |
| 1.11 | **De-duplication + packaging hygiene** — merge `edge-proxy/`+`edge_proxy/` (keep one, co-locate `worker.js`+`wrangler.toml`+simulator), delete `sdk-python/` dup, fix `send_json_response(data: any)` → `Any`, DB default → `~/.agentready/` via `platformdirs`/`AGENTREADY_DB_PATH`, single version const, weights recorded in `Score.metadata`, `temp-fixes/` + stray `agentready.db` deleted | Listed dirs, `storage/db.py:7`, `apps/web/server.py`, `config.py`/`drift.py`/`schemas.py` | `pip install -e .` + `agentready scan <fixture-via-local-server>` works; wheel smoke-install job in CI |
| 1.12 | **Dead-code triage** — fix or delete: `probes/scheduler.py:43` (`"probes"` vs `"results"` + missing `save_probe_result`), `onboarding/wizard.py` fake step 3, `compliance/retention.py` stub purge, `apm.py` tabletop, `fixer/engine.py` unused Scorer, `ProbeResult.model_name` (add `Optional[str]` + populate, fix `postgres_rls.py:301`), `postgres_rls.py:210` → `set_config(%s)` | Each file | Each fix has a test calling the previously-dead path; deletions noted in CHANGELOG |

**Exit gate M1 (do not enter Phase 2 until all true):**
- [ ] SSRF suite green; keyed probe with exhausted budget refuses pre-spend; forced 500 → breaker + DLQ
- [ ] Robots fixtures green; seeded migration reconciles 100% or fails loudly
- [ ] Entrypoint smoke (web/CLI/worker) green; `/api/badge` no-crash; logs are JSON with trace IDs
- [ ] CI: ruff + mypy(core) + coverage floor + lane split enforced; default lane <60s
- [ ] `grep` single version / single key prefix / single weights; DB no longer materializes in CWD
- [ ] Docs: README/FEATURES accurate; archived audit docs bannered

### Phase 2 — Real Infrastructure Behind Interfaces (Months 2–3, gated on M1)

Build one subsystem at a time behind the M1 interfaces, each behind a flag with rollback. Required ADRs first: ADR-001 (orchestration), ADR-002 (Postgres+RLS vs app-scoping), ADR-003 (FastAPI + auth ownership). See review §6.

| # | Workstream | Concrete steps | Exit |
|---|---|---|---|
| 2.1 | Real persistence | `StorageProtocol` (harden `repository.py`) → `SQLiteRepository` + genuine `PostgresRepository` (psycopg3, `set_config('app.tenant_id',%s,true)` per tx, DDL from `postgres_rls.py:15-93` as Alembic rev 1 after placeholder + `model_name` fixes). Alembic + version table | Tenant-isolation suite passes vs **real Postgres with RLS enforced** (Plan.md 3.1.5); SQLite path read-only during cutover |
| 2.2 | Real cache/counters | `redis-py` behind `DistributedProbeCache` interface; atomic `INCR`/Lua budget reservation; keep 6h TTL | Chaos test vs real Redis (or transactional `fakeredis`) shows zero double-reservation under concurrency |
| 2.3 | API service | Replace `http.server` with FastAPI (keep handler logic); persisted hashed-key auth on every route; OpenAPI generated (retire hand-written `openapi.json`); scoped CORS | Auth contract tests green; phase-12 fuzz suite re-run vs real router, 0 unauth findings |
| 2.4 | Worker maturity | Leader lease + jitter + batch-crawler concurrency + DLQ replay + cycle metrics; ADR-001 trigger written (cron now, RQ/Celery at ~50 domains or first missed schedule) | 2 workers → 1 cycle; forced outage → DLQ capture, zero lost probes |
| 2.5 | Packaging | `src/agentready` rename, Trusted Publishing + wheel smoke test, `action.yml` exercised vs fixture, TS SDK `tsc --noEmit` + vitest or delete | `pip install agentready && agentready scan <fixture>` on clean machine; Action demo green |
| 2.6 | Performance | `requests.Session` reuse + parallel `robots/llms.txt/llms-full.txt` fetch (`ThreadPoolExecutor(3)`), dry-run sleep opt-in, badge/report caching | Scan p95 ≤2s on fixture locally |

### Phase 3 — Feature Expansion (Month 4+, gated on Phase 2 per-feature prerequisites)

| Feature | Why sequenced here | Prereq |
|---|---|---|
| 7-signal `score_v0.3` (wire semantic/multimodal/i18n + recalibrate) | Closes marketing gap honestly | M1 single-weights + checked-in calibration dataset (replace 5-sample `correlate`) |
| Correlation dataset + methodology page | Product moat | Live pipeline with cost controls + verbatim storage (already done — keep) |
| Hosted SaaS + Stripe | Revenue | 2.1 + 2.3 + managed auth (ADR-003) |
| MCP over Streamable HTTP/SSE | Distribution | 2.3 + auth-on default; adversarial corpus as transport tests |
| Edge Worker deploy + KV kill switch + shadow analytics | Zero-downtime CDN story | Edge dir merge + KV + `wrangler` CI + synth monitoring |
| Citation-drop alerting | Retention | 2.4 + Postgres history; add HMAC expiry (no replay window today) |
| Remediation PRs GA | Fix loop | 2.5 + tree-level commits + GitHub App flow + sandbox repo CI |
| Dashboard v2 / WCAG | Only if hosted | SaaS decision; keep vanilla-JS until users exist |

**Explicitly deferred (with triggers):** SOC2/pentest (after first paying tenant on hosted API), sharding/K8s/multi-region (after measured bottleneck doc, review §5-13.3.1), MCP write actions (after read-only + security review).

---

## 3. Threat-model note (improvement: review lists holes, this orders them by exploitability)

1. **SSRF via scan URL** (M1.1) — hosted web/MCP fetches arbitrary URL server-side. Fix first.
2. **Unauth web on 0.0.0.0 + CORS *** (M1.8) — bind localhost until ADR-003 API lands.
3. **MCP anon + regex-only injection** (M1.8) — auth-on + schema validation; document residual homoglyph risk.
4. **Plaintext creds + unused key** (M1.8) — `0600` + warn-unused.
5. **Query-string API key (Gemini), `str(e)` leaks, f-string `SET LOCAL`** (M1.8/M1.12) — header auth, humanized errors, parameterized `set_config`.

---

## 4. Test strategy (improvement: composition over mocks)

- **New tests must go through entrypoints or `ProbePipeline`**, never bare mocks. Mock-only tests for Redis/Postgres/OTLP are tagged `emulated` and excluded from readiness claims per ADR-004.
- **Slow lane:** `test_load_chaos_harness`, `test_benchmarks`, phase-12/13 suites → `@pytest.mark.slow`, separate CI job.
- **Benchmarks:** remove `load_test.py:60-65` global lock or relabel `docs/benchmarks.md` as smoke timing, not capacity.
- **Calibration:** replace hardcoded 5-sample `correlate` with checked-in dataset + notebook; `r ≥ 0.65` claim forbidden until reproduced.

---

## 5. Timeline (aggressive but honest)

- **Days 1–3:** Sprint 0 truth reset
- **Weeks 1–2:** M1a P0s + entrypoint smoke skeleton
- **Weeks 3–4:** M1b composition + M1c gates/hygiene → **M1 exit review**
- **Months 2–3:** Phase 2, one workstream at a time (2.1 → 2.2 → 2.3 → 2.4 → 2.5/2.6 parallel)
- **Month 4+:** Phase 3 features only against listed prereqs

Gantt in `Plan.md` §16 is obsolete (dates in 2025, assumes façade is real) — do not follow it until M1 exit.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Docs rewrite seen as "downgrade" | Frame as trust repair: archived reports preserved with banners, new README links target-arch doc; readiness % frozen until CI-computed |
| `src/` rename breaks imports | Do last in Phase 2 (2.5), with smoke-install job; keep `packages.*` shims during transition |
| Real Postgres/Redis scope creep | Interface-first (M1.5/2.1/2.2); SQLite remains default until isolation suite passes on real PG |
| Probe spend during testing | Dry-run default stays; `ProbePipeline` budget check is first line; chaos tests use mocks tagged `emulated` |

---

## 7. Immediate next actions (pick up tomorrow)

1. Merge Sprint 0 (0.1–0.5) — 1 PR, docs-only, no code.
2. Land `tests/test_entrypoints_smoke.py` skeleton (failing) — forces M1a fixes to prove through live paths.
3. Fix 1.1 (SSRF) + 1.2 (robots) + 1.4 (badge) — 3 small PRs, each with its new test.
4. Write ADR-001/002/003/004 stubs in `docs/decisions/` before M1b composition work.
5. Schedule M1 exit review; freeze Phase 2 branches until gate passes.

---

## Appendix — P0/P1 → task traceability

Every review §3.1 P0/P1 maps to a task above: SSRF→1.1, robots→1.2, migration→1.3, docs-integrity→0.1-0.4, auth→1.8, badge→1.4, `save_probe`→1.12, SQLi→1.12, cost-safety→1.5, Gemini-key→1.8, MCP-auth→1.8, dup-dirs→1.11, observability→1.7, worker→1.6. P2 packaging/weights/dead-code/benchmarks/hygiene → 1.10/1.11/1.12/§4.
