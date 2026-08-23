"""Rich terminal output formatting for AgentReady CLI."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from packages.core.schemas import ComponentStatus, Score


def get_status_badge(status: ComponentStatus) -> Text:
    """Format status badge with color."""
    if status == ComponentStatus.PASS:
        return Text(" PASS ", style="bold black on green")
    elif status == ComponentStatus.WARN:
        return Text(" WARN ", style="bold black on yellow")
    else:
        return Text(" FAIL ", style="bold white on red")


def get_grade_style(grade: str) -> str:
    """Return styling for letter grade."""
    if grade in ["A+", "A"]:
        return "bold green"
    elif grade in ["B"]:
        return "bold cyan"
    elif grade in ["C"]:
        return "bold yellow"
    else:
        return "bold red"


def print_rich_score(score: Score, console: Console | None = None) -> None:
    """Render a comprehensive, beautiful terminal dashboard for a score report."""
    if console is None:
        console = Console()

    # Header Panel
    grade_style = get_grade_style(score.grade)
    header_text = Text()
    header_text.append("AGENT-READINESS REPORT\n", style="bold white")
    header_text.append("Target: ", style="bold dim")
    header_text.append(f"{score.url}\n", style="bold underline white")
    header_text.append("Overall Score: ", style="bold dim")
    header_text.append(f"{score.overall_score:.1f} / 100  ", style="bold magenta")
    header_text.append("Grade: ", style="bold dim")
    header_text.append(f"[{score.grade}]  ", style=grade_style)
    header_text.append(f"({score.version})\n\n", style="dim")
    header_text.append(f"{score.summary}", style="italic white")

    console.print(Panel(header_text, title="[bold cyan]AgentReady[/bold cyan]", border_style="cyan", padding=(1, 2)))

    # Component Table
    table = Table(title="Readiness Signal Breakdown", show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Status", width=10, justify="center")
    table.add_column("Signal Check", width=28, style="bold")
    table.add_column("Score", width=10, justify="right")
    table.add_column("Weight", width=8, justify="right")
    table.add_column("Key Findings & Diagnostics", style="dim")

    for comp in score.components:
        badge = get_status_badge(comp.status)
        score_styled = f"{comp.score:.1f}"
        if comp.score >= 80:
            score_styled = f"[green]{score_styled}[/green]"
        elif comp.score >= 50:
            score_styled = f"[yellow]{score_styled}[/yellow]"
        else:
            score_styled = f"[red]{score_styled}[/red]"

        table.add_row(
            badge,
            comp.display_name,
            score_styled,
            f"{int(comp.weight * 100)}%",
            comp.details,
        )

    console.print(table)

    # Bot Permissions sub-table if present
    for comp in score.components:
        if comp.name == "bot_permissions" and "bot_status" in comp.evidence:
            bots = comp.evidence["bot_status"]
            if bots:
                bot_table = Table(title="AI Crawler Permissions (robots.txt)", show_header=True, header_style="bold blue")
                bot_table.add_column("Crawler Bot", style="bold")
                bot_table.add_column("Status", justify="center")
                bot_table.add_column("Matched Rule")

                for bot_name, binfo in bots.items():
                    b_status = binfo.get("status", "UNKNOWN")
                    if b_status == "ALLOWED":
                        b_badge = "[green]ALLOWED[/green]"
                    elif b_status == "BLOCKED":
                        b_badge = "[red]BLOCKED[/red]"
                    else:
                        b_badge = "[yellow]PARTIAL[/yellow]"
                    bot_table.add_row(bot_name, b_badge, binfo.get("matched_by", "-"))
                console.print(bot_table)

    # Recommendations Panel
    if score.recommendations:
        rec_text = Text()
        for idx, rec in enumerate(score.recommendations, 1):
            rec_text.append(f"{idx}. ", style="bold cyan")
            rec_text.append(f"{rec}\n", style="white")

        console.print(Panel(rec_text, title="[bold yellow]Actionable Remediation Plan[/bold yellow]", border_style="yellow", padding=(1, 2)))

