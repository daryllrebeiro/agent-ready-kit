"""Automated probe runner and cron worker for tracking domain readiness and citations."""

import argparse
import time

from rich.console import Console

from packages.core.probes.extractor import extract_domain_from_url
from packages.core.probes.runner import MultiModelProber
from packages.core.scorer import Scorer
from packages.core.storage.repository import StorageRepository


def run_worker_cycle(
    domains: list[str],
    dry_run: bool = False,
    max_prompts: int = 3,
    repo: StorageRepository | None = None,
) -> None:
    """Execute a complete scan and probing cycle for a list of domains."""

    from packages.core.integrations.notifications import dispatch_dlq_escalation
    from packages.core.observability.logger import TraceContext, get_structured_logger
    from packages.core.pipeline.budget_enforcer import BudgetExceededError
    from packages.core.pipeline.dlq import DeadLetterQueue
    from packages.core.probes.pipeline import ProbePipeline

    console = Console()
    logger = get_structured_logger("agentready.worker")
    storage = repo or StorageRepository()
    scorer = Scorer()
    prober = MultiModelProber()
    dlq = DeadLetterQueue()
    pipeline = ProbePipeline(dlq=dlq)
    providers_by_name = {p.provider_name: p for p in prober.providers}

    console.print(f"[bold cyan]Starting AgentReady worker cycle for {len(domains)} domain(s)...[/bold cyan]")

    for domain_url in domains:
        console.print("\n[dim]----------------------------------------[/dim]")
        console.print(f"[bold white]Processing:[/bold white] [cyan]{domain_url}[/cyan]")

        with TraceContext(tenant_id=domain_url):
            # 1. Scan and store score
            try:
                score = scorer.score_url(domain_url)
                score_id = storage.save_score(domain_url, score)
                console.print(
                    f"  [green][OK] Scored:[/green] {score.overall_score:.1f}/100 (Grade: {score.grade}) [dim](Saved record #{score_id})[/dim]"
                )
                logger.info(f"worker scored {domain_url} {score.overall_score}/100")
            except Exception:
                console.print("[red][FAIL] Scoring failed[/red]")
                logger.warning(f"worker scoring failed for {domain_url}")
                continue

        # 2. Run multi-model probe suite via the guarded pipeline
        # (budget -> cache -> breaker -> provider -> DLQ on failure).
        from packages.core.probes.prompts import STANDARD_PROBE_PROMPTS

        base_domain = extract_domain_from_url(domain_url)
        console.print(f"  [dim]Running multi-model citation probes for '{base_domain}'...[/dim]")

        total_probes = 0
        total_citations = 0

        pipeline.tenant_id = domain_url
        pipeline.target_url = domain_url

        try:
            suite_results = pipeline.run_suite(
                prober,
                STANDARD_PROBE_PROMPTS[:max_prompts],
                target_domain=base_domain,
                dry_run=dry_run,
            )
        except BudgetExceededError:
            console.print("  [yellow]Budget exhausted — stopping probe loop[/yellow]")
            logger.warning(f"worker budget exhausted for {domain_url}")
            suite_results = []

        for prompt_run in suite_results:
            for probe_res in prompt_run["results"]:
                total_probes += 1
                storage.save_probe_run(domain_url, probe_res)
                if base_domain in [d.lower() for d in probe_res.cited_domains]:
                    total_citations += 1

        cit_pct = (total_citations / max(1, total_probes)) * 100.0
        console.print(
            f"  [bold green][OK] Probing complete:[/bold green] {total_citations}/{total_probes} citations detected ({cit_pct:.1f}% citation share)"
        )

    # 3. DLQ replay pass at cycle end: real re-execution through the same
    # guarded pipeline; exhausted jobs escalate to a real outbound webhook
    # (Task 9). dispatch_dlq_escalation returns False honestly when no
    # webhook URL is configured — nothing is faked.
    if len(dlq) and not dry_run:

        def _replay(job) -> bool:
            provider = providers_by_name.get(job.provider)
            if provider is None:
                return False
            try:
                pipeline.run(provider, job.prompt, dry_run=False)
                return True
            except Exception:
                return False

        results = dlq.replay_failed_jobs(
            _replay,
            max_retries=3,
            escalation_callback=lambda job: dispatch_dlq_escalation(job),
        )
        logger.info(f"worker dlq replay: {results}")
        console.print(f"[dim]DLQ replay: {results}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentReady Background Tracking Worker")
    parser.add_argument("--domain", "-d", help="Single domain to scan and probe")
    parser.add_argument("--cron", action="store_true", help="Run in continuous recurring cron mode")
    parser.add_argument(
        "--interval", type=int, default=3600, help="Interval in seconds for cron mode (default: 3600s / 1hr)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run simulation mode without consuming LLM API credits",
    )
    parser.add_argument("--max-prompts", type=int, default=3, help="Max discovery prompts to run per cycle")
    args = parser.parse_args()

    storage = StorageRepository()

    def get_target_domains() -> list[str]:
        if args.domain:
            return [args.domain]
        all_domains = storage.list_domains()
        if not all_domains:
            # Seed default if empty
            return ["https://agentready.dev"]
        return [d["domain_url"] for d in all_domains]

    if args.cron:
        import random

        console = Console()
        console.print(
            f"[bold green]AgentReady Worker started in daemon cron mode (Interval: {args.interval}s)[/bold green]"
        )
        while True:
            targets = get_target_domains()
            run_worker_cycle(targets, dry_run=args.dry_run, max_prompts=args.max_prompts, repo=storage)
            # Jitter so overlapping deployments do not stampede providers at once.
            delay = args.interval + random.uniform(0, min(60, args.interval * 0.1))
            console.print(f"\n[dim]Sleeping {delay:.0f}s until next scheduled run...[/dim]")
            time.sleep(delay)
    else:
        targets = get_target_domains()
        run_worker_cycle(targets, dry_run=args.dry_run, max_prompts=args.max_prompts, repo=storage)


if __name__ == "__main__":
    main()
