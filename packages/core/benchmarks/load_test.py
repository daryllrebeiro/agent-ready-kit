"""High-concurrency synthetic load testing harness for multi-tenant platform and edge proxy."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List
import sqlite3

from packages.core.auth.context import TenantContext, UserRole
from packages.core.schemas import Score
from packages.core.storage.tenant_repository import MultiTenantRepository


class LoadTestHarness:
    """Simulates realistic multi-tenant traffic spikes to measure throughput and latency."""

    def __init__(self, tenant_count: int = 50, operations_per_tenant: int = 20):
        self.tenant_count = tenant_count
        self.operations_per_tenant = operations_per_tenant

    def run_multi_tenant_benchmark(self) -> Dict[str, Any]:
        """Execute concurrent multi-tenant read/write operations against repository."""
        # Use shared in-memory SQLite with WAL
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        repo = MultiTenantRepository(conn)

        # 1. Provision synthetic tenants
        contexts: List[TenantContext] = []
        for i in range(self.tenant_count):
            org_id = f"org_bench_{i}"
            repo.create_organization(org_id, f"Synthetic Corp {i}", tier="growth", monthly_quota=5000)
            ctx = TenantContext(org_id=org_id, user_id=f"user_{i}", role=UserRole.ADMIN, monthly_probe_quota=5000)
            contexts.append(ctx)
            # Add domains
            repo.add_domain(ctx, f"https://tenant{i}-prod.example.com")

        start_time = time.time()
        latencies: List[float] = []
        errors = 0
        total_ops = self.tenant_count * self.operations_per_tenant

        dummy_score = Score(
            url="https://tenant-bench.com",
            version="score_v0.1",
            overall_score=85.0,
            grade="A",
            components=[],
            summary="Benchmark test score",
            recommendations=[],
        )

        import threading
        db_lock = threading.Lock()

        def worker_task(ctx: TenantContext) -> List[float]:
            task_latencies = []
            nonlocal errors
            for _ in range(self.operations_per_tenant):
                t0 = time.time()
                try:
                    with db_lock:
                        domains = repo.list_domains(ctx)
                        if domains:
                            d_id = domains[0]["id"]
                            repo.save_score(ctx, d_id, dummy_score)
                            repo.list_scores(ctx, d_id, limit=5)
                except Exception:
                    errors += 1
                task_latencies.append((time.time() - t0) * 1000.0)
            return task_latencies

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker_task, ctx) for ctx in contexts]
            for f in as_completed(futures):
                latencies.extend(f.result())

        total_time = time.time() - start_time
        ops_per_sec = total_ops / max(0.001, total_time)
        avg_latency = sum(latencies) / max(1, len(latencies))
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0

        return {
            "tenants_tested": self.tenant_count,
            "total_operations": total_ops,
            "duration_seconds": round(total_time, 3),
            "throughput_ops_per_sec": round(ops_per_sec, 1),
            "average_latency_ms": round(avg_latency, 2),
            "p95_latency_ms": round(p95_latency, 2),
            "errors_encountered": errors,
        }
