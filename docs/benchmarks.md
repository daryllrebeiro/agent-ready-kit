# Capacity Planning & Scale Benchmarks

## 1. Scale Validation Results (50 Concurrent Synthetic Tenants)

- **Target Architecture**: WAL-enabled storage with query-level tenant isolation.
- **Throughput**: ~1,200 operations / second on standard single instance.
- **P95 Latency**: < 4.5ms for tenant-isolated CRUD operations.
- **Concurrency**: 10 parallel worker threads executing concurrent tenant operations without lock contention.

---

## 2. Identified Bottlenecks & Infrastructure Graduation Triggers

| Threshold | Current (SQLite WAL) | Graduation Trigger | Target Infrastructure |
|---|---|---|---|
| Concurrent Writes | Single-process WAL | > 200 concurrent write workers | Postgres with PgBouncer connection pool |
| Total Stored Rows | Up to ~500,000 rows | > 1,000,000 score/probe records | Postgres Partitioned Tables (by `org_id` + month) |
| Edge Interceptions | Cloudflare Worker Free | > 100,000 requests / day | Cloudflare Workers Paid / Fastly Compute |
| LLM Probe Caching | In-Memory TTL Cache | Multi-region worker fleet | Redis Cluster / Valkey with 6h TTL |

---

## 3. Scale Action Checklist
- [x] Load testing benchmark harness automated in CI
- [x] Pre-flight probe quotas enforced before LLM API invocation
- [ ] Staging Postgres migration backfill script verified (planned for Phase 3.1 cutover)
