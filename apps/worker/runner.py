"""Automated probe runner and cron worker for tracking domain readiness and citations."""

import argparse
import sys
import time
from typing import List, Optional
from rich.console import Console

from packages.core.probes.extractor import extract_domain_from_url
from packages.core.probes.runner import MultiModelProber
from packages.core.scorer import Scorer
from packages.core.storage.repository import StorageRepository


def run_worker_cycle(
    domains: List[str],
    dry_run: bool = False,
    max_prompts: int = 3,
    repo: Optional[StorageRepository] = None,
) -> None:
    """Execute a complete scan and probing cycle for a list of domains."""
    console = Console()
    storage = repo or StorageRepository()
    scorer = Scorer()
    prober = MultiModelProber()

    console.print(f"[bold cyan]Starting AgentReady worker cycle for {len(domains)} domain(s)...[/bold cyan]")

    for domain_url in domains:
        console.print(f"\n[dim]----------------------------------------[/dim]")
        console.print(f"[bold white]Processing:[/bold white] [cyan]{domain_url}[/cyan]")

        # 1. Scan and store score
        try:
            score = scorer.score_url(domain_url)
            score_id = storage.save_score(domain_url, score)
            console.print(f"  [green][OK] Scored:[/green] {score.overall_score:.1f}/100 (Grade: {score.grade}) [dim](Saved record #{score_id})[/dim]")
        except Exception as e:
            console.print(f"  [red][FAIL] Scoring failed:[/red] {e}")
            continue

        # 2. Run multi-model probe suite
        base_domain = extract_domain_from_url(domain_url)
        console.print(f"  [dim]Running multi-model citation probes for '{base_domain}'...[/dim]")

        suite_results = prober.run_standard_probe_suite(
            target_domain=base_domain,
            max_prompts=max_prompts,
            dry_run=dry_run,
        )

        total_probes = 0
        total_citations = 0

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


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentReady Background Tracking Worker")
    parser.add_argument("--domain", "-d", help="Single domain to scan and probe")
    parser.add_argument("--cron", action="store_true", help="Run in continuous recurring cron mode")
    parser.add_argument("--interval", type=int, default=3600, help="Interval in seconds for cron mode (default: 3600s / 1hr)")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run simulation mode without consuming LLM API credits")
    parser.add_argument("--max-prompts", type=int, default=3, help="Max discovery prompts to run per cycle")
    args = parser.parse_args()

    storage = StorageRepository()

    def get_target_domains() -> List[str]:
        if args.domain:
            return [args.domain]
        all_domains = storage.list_domains()
        if not all_domains:
            # Seed default if empty
            return ["https://agentready.dev"]
        return [d["domain_url"] for d in all_domains]

    if args.cron:
        console = Console()
        console.print(f"[bold green]AgentReady Worker started in daemon cron mode (Interval: {args.interval}s)[/bold green]")
        while True:
            targets = get_target_domains()
            run_worker_cycle(targets, dry_run=args.dry_run, max_prompts=args.max_prompts, repo=storage)
            console.print(f"\n[dim]Sleeping {args.interval}s until next scheduled run...[/dim]")
            time.sleep(args.interval)
    else:
        targets = get_target_domains()
        run_worker_cycle(targets, dry_run=args.dry_run, max_prompts=args.max_prompts, repo=storage)


if __name__ == "__main__":
    main()
