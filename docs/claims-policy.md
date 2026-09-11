# Capability Claims Policy (ADR-004, lightweight)

**Rule:** every capability claim in a user-facing doc (`README.md`,
`FEATURES.md`) must name the file that implements it and the test that
exercises it **through a runtime entrypoint** (CLI, HTTP, worker — never
a mock in isolation).

**Forbidden:** readiness percentages, GA/production-ready labels, SOC2 /
pentest / audit claims, and performance numbers, unless produced by a CI
job running against real dependencies with its output linked.

**Checklist (reviewers):**
1. Does the claim name a file? Link it.
2. Does the linked test touch an entrypoint? If mock-only, the claim goes
   in `docs/target-architecture.md`, not `FEATURES.md`.
3. Does any number come from a CI run? Link the run.

Adopted 2026-09-11 after the 92.5%-against-mocks incident. See
`REVIEW_AND_ROADMAP.md` §6 ADR-004 and Appendix evidence index.
