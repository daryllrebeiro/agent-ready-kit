"""AgentReady Command Line Interface."""

import argparse
import json
import os
import sys
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from packages.cli.formatters import print_rich_score
from packages.core.config import ALGORITHM_VERSION
from packages.core.correlation import CorrelationHarness
from packages.core.generator import LLMsGenerator
from packages.core.probes.extractor import extract_domain_from_url
from packages.core.probes.runner import MultiModelProber
from packages.core.scorer import Scorer
from packages.core.storage.repository import StorageRepository

CLI_VERSION = "0.1.0"


def handle_scan_command(args: argparse.Namespace) -> int:
    """Execute scan against a target URL."""
    console = Console()
    err_console = Console(stderr=True)
    scorer = Scorer(timeout_seconds=args.timeout)

    if not args.json:
        console.print(f"[dim]Scanning [bold white]{args.url}[/bold white] for agent-readiness...[/dim]")

    try:
        score = scorer.score_url(args.url)
    except Exception as e:
        err_console.print(f"[bold red]Error during scan:[/bold red] {e}")
        return 2

    # Handle output format
    if getattr(args, "pr_comment", False):
        from packages.cli.pr_comment import format_pr_comment
        print(format_pr_comment(score, min_score=args.min_score))
    elif args.json:
        json_output = score.model_dump_json(indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(json_output)
        else:
            print(json_output)
    else:
        print_rich_score(score, console=console)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(score.model_dump_json(indent=2))
            console.print(f"[dim]Report saved to [bold cyan]{args.output}[/bold cyan][/dim]")

    # Check CI threshold
    if args.min_score is not None:
        if score.overall_score < args.min_score:
            if not args.json:
                err_console.print(
                    f"\n[bold red]CI FAILURE:[/bold red] Overall score {score.overall_score:.1f} is below minimum threshold of {args.min_score:.1f}"
                )
            return 1
        elif not args.json:
            console.print(
                f"\n[bold green]CI SUCCESS:[/bold green] Overall score {score.overall_score:.1f} meets minimum threshold of {args.min_score:.1f}"
            )

    return 0


def handle_generate_command(args: argparse.Namespace) -> int:
    """Execute generation of llms.txt and schema metadata."""
    console = Console()
    generator = LLMsGenerator()

    sitemap_url = args.sitemap
    target_url = args.url or (sitemap_url.rsplit("/", 1)[0] if sitemap_url else "https://example.com")
    site_name = args.name or target_url.split("//")[-1].split("/")[0].title()
    site_desc = args.description or f"Official agent-ready documentation and API guide for {site_name}."

    pages = []
    if sitemap_url:
        console.print(f"[dim]Fetching sitemap from [bold white]{sitemap_url}[/bold white]...[/dim]")
        urls = generator.parse_sitemap(sitemap_url, max_urls=args.max_pages)
        console.print(f"[dim]Discovered {len(urls)} pages. Extracting summaries...[/dim]")
        for u in urls[: args.max_pages]:
            pages.append(generator.extract_page_summary(u))
    elif target_url:
        pages.append(generator.extract_page_summary(target_url))

    if getattr(args, "languages", None):
        from packages.core.generator_i18n import MultilingualLLMsGenerator
        i18n_gen = MultilingualLLMsGenerator()
        langs = [l.strip() for l in args.languages.split(",") if l.strip()]
        bundle = i18n_gen.generate_multilingual_bundle(site_name, target_url or "https://example.com", languages=langs)
        written = i18n_gen.write_bundle_to_disk(bundle, args.output_dir or "./public")
        console.print(f"[bold green][OK] Successfully generated multilingual /llms.txt suite in '{args.output_dir or './public'}':[/bold green]")
        for rel_p, abs_p in written.items():
            console.print(f"  - [bold cyan]{rel_p}[/bold cyan] -> {abs_p}")
        return 0

    llms_content = generator.generate_llms_txt(site_name, site_desc, pages)
    jsonld_content = generator.generate_json_ld_template(site_name, target_url, site_desc)

    out_dir = args.output_dir or "."
    os.makedirs(out_dir, exist_ok=True)

    llms_path = os.path.join(out_dir, "llms.txt")
    jsonld_path = os.path.join(out_dir, "schema-ld.json")

    with open(llms_path, "w", encoding="utf-8") as f:
        f.write(llms_content)

    with open(jsonld_path, "w", encoding="utf-8") as f:
        f.write(jsonld_content)

    console.print(f"[bold green][OK] Successfully generated agent-ready files:[/bold green]")
    console.print(f"  - [bold cyan]{llms_path}[/bold cyan] (Spec-compliant /llms.txt)")
    console.print(f"  - [bold cyan]{jsonld_path}[/bold cyan] (Schema.org JSON-LD starter template)")
    return 0


def handle_probe_command(args: argparse.Namespace) -> int:
    """Execute multi-model probing against a target URL/domain."""
    console = Console()
    prober = MultiModelProber()
    storage = StorageRepository()

    target_domain = extract_domain_from_url(args.url)
    console.print(f"[dim]Probing multi-model citations for [bold white]{target_domain}[/bold white]...[/dim]")

    suite_results = prober.run_standard_probe_suite(
        target_domain=target_domain,
        max_prompts=args.max_prompts,
        dry_run=args.dry_run,
    )

    total_probes = 0
    total_citations = 0

    table = Table(title=f"Multi-Model LLM Probing Results: {target_domain}", show_header=True, header_style="bold cyan")
    table.add_column("Provider", style="bold")
    table.add_column("Prompt Sample", style="dim")
    table.add_column("Cited Domains", style="cyan")
    table.add_column("Target Cited?", justify="center")

    for prompt_run in suite_results:
        p_text = prompt_run["prompt"][:50] + "..."
        for res in prompt_run["results"]:
            total_probes += 1
            storage.save_probe_run(args.url, res)
            is_cited = target_domain.lower() in [d.lower() for d in res.cited_domains]
            if is_cited:
                total_citations += 1

            badge = "[bold green]YES[/bold green]" if is_cited else "[dim]NO[/dim]"
            table.add_row(
                res.provider.upper(),
                p_text,
                ", ".join(res.cited_domains[:3]) or "(none)",
                badge,
            )

    console.print(table)
    cit_share = (total_citations / max(1, total_probes)) * 100.0
    console.print(f"\n[bold]Citation Share:[/bold] [bold cyan]{cit_share:.1f}%[/bold cyan] ({total_citations}/{total_probes} probes)")
    return 0


def handle_dashboard_command(args: argparse.Namespace) -> int:
    """Start local web dashboard."""
    from apps.web.server import start_server
    console = Console()
    console.print(f"[bold cyan]Launching AgentReady Web Dashboard on port {args.port}...[/bold cyan]")
    start_server(port=args.port, open_browser=args.open)
    return 0


def handle_correlate_command(args: argparse.Namespace) -> int:
    """Run correlation evaluation harness on sample dataset."""
    console = Console()
    harness = CorrelationHarness()
    scorer = Scorer()

    console.print("[dim]Running correlation & calibration harness across test samples...[/dim]")

    # Build calibration dataset
    samples = [
        {"score": {"overall_score": 92.0, "components": [{"name": "llms_txt", "score": 95}, {"name": "structured_data", "score": 90}, {"name": "token_bloat", "score": 85}, {"name": "bot_permissions", "score": 95}]}, "citation_rate": 0.85},
        {"score": {"overall_score": 84.0, "components": [{"name": "llms_txt", "score": 80}, {"name": "structured_data", "score": 85}, {"name": "token_bloat", "score": 80}, {"name": "bot_permissions", "score": 90}]}, "citation_rate": 0.70},
        {"score": {"overall_score": 68.0, "components": [{"name": "llms_txt", "score": 50}, {"name": "structured_data", "score": 70}, {"name": "token_bloat", "score": 75}, {"name": "bot_permissions", "score": 70}]}, "citation_rate": 0.50},
        {"score": {"overall_score": 45.0, "components": [{"name": "llms_txt", "score": 0}, {"name": "structured_data", "score": 50}, {"name": "token_bloat", "score": 60}, {"name": "bot_permissions", "score": 60}]}, "citation_rate": 0.20},
        {"score": {"overall_score": 25.0, "components": [{"name": "llms_txt", "score": 0}, {"name": "structured_data", "score": 10}, {"name": "token_bloat", "score": 40}, {"name": "bot_permissions", "score": 20}]}, "citation_rate": 0.05},
    ]

    report = harness.analyze_dataset(samples)
    console.print(Panel(
        f"[bold white]{report['finding']}[/bold white]\n\n"
        f"Pearson r: [bold cyan]{report['overall_pearson_r']}[/bold cyan] | Spearman rho: [bold cyan]{report['overall_spearman_rho']}[/bold cyan]\n"
        f"Strongest Signal Driver: [bold magenta]{report['strongest_signal']}[/bold magenta]",
        title="[bold green]Correlation & Hypothesis Validation Report[/bold green]",
        border_style="green",
    ))
    return 0


def handle_fix_command(args: argparse.Namespace) -> int:
    """Generate turnkey remediation files for a website."""
    from packages.core.fixer.engine import FixerEngine
    console = Console()
    fixer = FixerEngine()

    console.print(f"[dim]Analyzing [bold white]{args.url}[/bold white] and generating remediation files...[/dim]")
    fixes = fixer.generate_all_fixes(args.url, site_name=args.name, site_description=args.description)
    out_dir = args.output_dir or "./agentready-fixes"
    written = fixer.apply_fixes_to_directory(fixes, out_dir)

    console.print(f"[bold green][OK] Successfully generated drop-in remediation bundle in '{out_dir}':[/bold green]")
    for fname, fpath in written.items():
        console.print(f"  - [bold cyan]{fname}[/bold cyan] -> {fpath}")
    return 0


def handle_compare_command(args: argparse.Namespace) -> int:
    """Run competitor benchmark comparison."""
    from packages.core.competitors.benchmark import CompetitorBenchmarkEngine
    console = Console()
    engine = CompetitorBenchmarkEngine()

    console.print(f"[dim]Running head-to-head citation benchmark for [bold white]{args.url}[/bold white] vs {args.competitors}...[/dim]")
    res = engine.compare_domains(args.url, args.competitors, dry_run=args.dry_run)

    console.print(f"\n[bold white]Target Domain:[/bold white] [bold cyan]{res['target_domain']}[/bold cyan]")
    console.print(f"[bold white]Benchmark Status:[/bold white] [bold {'green' if res['win_status'] == 'WINNING' else 'yellow' if res['win_status'] == 'TIED' else 'red'}]{res['win_status']}[/]")
    console.print(f"[bold white]Target Citation Share:[/bold white] {res['target_citation_share_pct']}%")

    console.print("\n[bold]Readiness & Citation Ranking:[/bold]")
    for idx, item in enumerate(res["readiness_ranking"], 1):
        c_count = res["citation_counts"].get(item["domain"], 0)
        console.print(f"  {idx}. [bold]{item['domain']}[/bold] — Score: {item['score']:.1f} ({item['grade']}) | Citations: {c_count}")
    return 0


def handle_batch_command(args: argparse.Namespace) -> int:
    """Run batch scanning across a list of URLs."""
    from packages.core.crawler.batch import BatchCrawler
    console = Console()
    crawler = BatchCrawler(concurrency=args.concurrency)

    with open(args.file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    console.print(f"[dim]Batch scanning {len(urls)} domains with concurrency={args.concurrency}...[/dim]")
    scores = crawler.scan_urls(urls)

    if args.output:
        crawler.export_to_csv(scores, args.output)
        console.print(f"[bold green][OK] Exported {len(scores)} results to [bold cyan]{args.output}[/bold cyan][/bold green]")
    else:
        console.print(f"\n[bold green][OK] Scanned {len(scores)} domains:[/bold green]")
        for s in scores[:10]:
            console.print(f"  - {s.url}: {s.overall_score:.1f} ({s.grade})")
        if len(scores) > 10:
            console.print(f"  ... and {len(scores) - 10} more domains.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(
        prog="agentready",
        description="AgentReady CLI: The missing layer between your website and AI agents.",
    )
    parser.add_argument("--version", action="version", version=f"AgentReady CLI {CLI_VERSION} (Algorithm: {ALGORITHM_VERSION})")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan a website for AI agent readiness and citation optimization")
    scan_parser.add_argument("url", help="URL of the website or endpoint to scan")
    scan_parser.add_argument("--min-score", type=float, help="Minimum score threshold (0-100) for CI/CD gates; exits with code 1 if failed")
    scan_parser.add_argument("--json", action="store_true", help="Output full report as machine-readable JSON")
    scan_parser.add_argument("--pr-comment", action="store_true", help="Output report formatted as a GitHub PR markdown comment")
    scan_parser.add_argument("--output", "-o", help="Path to write report output")
    scan_parser.add_argument("--timeout", type=float, default=10.0, help="HTTP request timeout in seconds (default: 10.0)")

    # Probe command
    probe_parser = subparsers.add_parser("probe", help="Probe LLM models to test live citation behavior")
    probe_parser.add_argument("url", help="Target URL or domain to test for citations")
    probe_parser.add_argument("--max-prompts", type=int, default=3, help="Number of benchmark discovery prompts to run")
    probe_parser.add_argument("--dry-run", action="store_true", help="Simulate probes without consuming LLM API keys")

    # Compare command
    comp_parser = subparsers.add_parser("compare", help="Compare citation share and readiness against competitor domains")
    comp_parser.add_argument("url", help="Target URL of your domain")
    comp_parser.add_argument("--competitors", "--vs", nargs="+", required=True, help="One or more competitor URLs/domains")
    comp_parser.add_argument("--dry-run", action="store_true", default=True, help="Simulate probes without consuming LLM API keys")

    # Batch command
    batch_parser = subparsers.add_parser("batch", help="Batch scan multiple domains from a text file")
    batch_parser.add_argument("file", help="File containing list of URLs/domains (one per line)")
    batch_parser.add_argument("--concurrency", "-c", type=int, default=5, help="Number of parallel workers (default: 5)")
    batch_parser.add_argument("--output", "-o", help="Path to export CSV report")

    # Dashboard command
    dash_parser = subparsers.add_parser("dashboard", help="Start local web dashboard")
    dash_parser.add_argument("--port", type=int, default=3000, help="Port to listen on (default: 3000)")
    dash_parser.add_argument("--open", action="store_true", help="Automatically open browser on start")

    # Correlate command
    subparsers.add_parser("correlate", help="Run hypothesis correlation analysis between scores and citations")

    # Fix command
    fix_parser = subparsers.add_parser("fix", help="Generate automated drop-in remediation files for a website")
    fix_parser.add_argument("url", help="Target URL to generate fixes for")
    fix_parser.add_argument("--name", help="Site/Product name")
    fix_parser.add_argument("--description", help="Site/Product brief summary")
    fix_parser.add_argument("--output-dir", "-o", default="./agentready-fixes", help="Output directory (default: ./agentready-fixes)")

    # Auth command
    auth_parser = subparsers.add_parser("auth", help="Manage AgentReady API keys and authentication credentials")
    auth_sub = auth_parser.add_subparsers(dest="auth_action", required=True)

    login_p = auth_sub.add_parser("login", help="Save API key")
    login_p.add_argument("--key", required=True, help="AgentReady API key (ark_live_...)")

    auth_sub.add_parser("whoami", help="View current authenticated credentials")
    auth_sub.add_parser("logout", help="Remove stored API key")

    # Simulate command
    sim_parser = subparsers.add_parser("simulate", help="Simulate specialized AI agent personas on a website")
    sim_parser.add_argument("url", help="Target URL to simulate agents on")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate compliant llms.txt and structured metadata templates")
    gen_parser.add_argument("--sitemap", help="URL to sitemap.xml to auto-discover pages")
    gen_parser.add_argument("--url", help="Root URL of the website")
    gen_parser.add_argument("--name", help="Site/Product name")
    gen_parser.add_argument("--description", help="Site/Product brief summary")
    gen_parser.add_argument("--languages", help="Comma-separated language codes for multilingual llms.txt suite (e.g. en,es,ja,de,fr,zh)")
    gen_parser.add_argument("--max-pages", type=int, default=20, help="Maximum number of sitemap pages to include (default: 20)")
    gen_parser.add_argument("--output-dir", "-o", default=".", help="Directory to save generated files (default: current directory)")

    return parser


def handle_simulate_command(args: argparse.Namespace) -> int:
    """Run AI agent persona simulations."""
    from packages.core.personas.simulator import AgentPersonaSimulator
    console = Console()
    sim = AgentPersonaSimulator()

    console.print(f"[dim]Simulating AI agent personas against [bold white]{args.url}[/bold white]...[/dim]")
    res = sim.simulate_all_personas(args.url)

    console.print(f"\n[bold white]Target URL:[/bold white] [bold cyan]{res['url']}[/bold cyan]")
    console.print(f"[bold white]Overall Persona Compatibility:[/bold white] [bold green]{res['overall_compatibility']}/100[/bold green]\n")

    console.print("[bold]Agent Archetype Compatibility Breakdown:[/bold]")
    for key, p in res["personas"].items():
        badge_color = "green" if p["status"] == "EXCELLENT" else "yellow" if p["status"] == "MODERATE" else "red"
        console.print(f"\n  * [bold]{p['name']}[/bold] - Score: [{badge_color}]{p['compatibility_score']:.1f}/100 ({p['status']})[/{badge_color}]")
        for strength in p.get("key_strengths", []):
            console.print(f"    - {strength}")
    return 0


def handle_auth_command(args: argparse.Namespace) -> int:
    """Manage authentication credentials."""
    from packages.cli.auth import clear_api_key, get_stored_api_key, save_api_key
    console = Console()

    if args.auth_action == "login":
        save_api_key(args.key)
        masked = args.key[:8] + "..." + args.key[-4:] if len(args.key) > 12 else "***"
        console.print(f"[bold green][OK] Successfully authenticated and saved API key: [bold cyan]{masked}[/bold cyan][/bold green]")
        return 0
    elif args.auth_action == "whoami":
        key = get_stored_api_key()
        if key:
            masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
            console.print(f"[bold white]Authenticated as API Key:[/bold white] [bold cyan]{masked}[/bold cyan]")
        else:
            console.print("[dim]No API key currently stored. Run `agentready auth login --key <key>` to log in.[/dim]")
        return 0
    elif args.auth_action == "logout":
        clear_api_key()
        console.print("[bold green][OK] Successfully logged out and cleared stored credentials.[/bold green]")
        return 0
    return 0


def cli_entrypoint(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        return handle_scan_command(args)
    elif args.command == "probe":
        return handle_probe_command(args)
    elif args.command == "compare":
        return handle_compare_command(args)
    elif args.command == "batch":
        return handle_batch_command(args)
    elif args.command == "dashboard":
        return handle_dashboard_command(args)
    elif args.command == "correlate":
        return handle_correlate_command(args)
    elif args.command == "fix":
        return handle_fix_command(args)
    elif args.command == "simulate":
        return handle_simulate_command(args)
    elif args.command == "auth":
        return handle_auth_command(args)
    elif args.command == "generate":
        return handle_generate_command(args)
    return 0


if __name__ == "__main__":
    sys.exit(cli_entrypoint())
