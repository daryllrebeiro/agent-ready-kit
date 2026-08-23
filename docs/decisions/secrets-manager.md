# Architecture Decision: Secrets Management

## Context
In Phase 0 through Phase 2 (PoC and early MVP), API keys for probing (OpenAI, Anthropic, Gemini, Perplexity) are stored in local `.env` files or environment variables on the single worker VM.

## Decision
Do not introduce a hosted cloud secrets manager (e.g. AWS Secrets Manager, GCP Secret Manager, Vault) during Phase 0–2.

## Revisit When
Multiple engineers or distributed production worker fleets need shared, rotated, and audit-logged secrets access in Phase 3.1+.
