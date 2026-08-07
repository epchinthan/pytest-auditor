"""
pytest_auditor/terminal.py
──────────────────────────
Rich terminal output for the audit report.
"""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.columns import Columns
from rich.padding import Padding
from rich.rule import Rule
from rich.progress import track

from .analyse import SuiteReport, FileReport, Issue

console = Console()

LEVEL_STYLE = {
    "error":   "bold red",
    "warning": "yellow",
    "info":    "cyan",
}
LEVEL_ICON = {
    "error":   "✖",
    "warning": "⚠",
    "info":    "ℹ",
}


def _score_colour(score: int) -> str:
    if score >= 85: return "bold green"
    if score >= 65: return "bold yellow"
    return "bold red"


def _score_label(score: int) -> str:
    if score >= 90: return "Excellent"
    if score >= 80: return "Good"
    if score >= 65: return "Needs attention"
    if score >= 50: return "Poor"
    return "Critical"


def print_report(report: SuiteReport) -> None:
    console.print()

    # ── header ────────────────────────────────────────────────────────────
    console.print(Panel.fit(
        f"[bold white]pytest Audit Report[/bold white]\n"
        f"[dim]{report.root}[/dim]\n"
        f"[dim]Generated: {report.generated_at}[/dim]",
        border_style="bright_blue",
        padding=(0, 2),
    ))
    console.print()

    # ── score card ────────────────────────────────────────────────────────
    sc = report.score
    sc_col = _score_colour(sc)
    sc_label = _score_label(sc)
    bar_len = 40
    filled = int(bar_len * sc / 100)
    bar = "█" * filled + "░" * (bar_len - filled)

    console.print(f"  Quality score  [{sc_col}]{sc:3d}/100  {sc_label}[/{sc_col}]")
    console.print(f"  [{sc_col}]{bar}[/{sc_col}]")
    console.print()

    # ── summary stats ─────────────────────────────────────────────────────
    stats = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    stats.add_column("metric", style="dim")
    stats.add_column("value",  style="bold white")
    stats.add_column("metric", style="dim")
    stats.add_column("value",  style="bold white")

    cov = f"{report.coverage_pct:.1f}%" if report.coverage_pct is not None else "n/a"
    cov_style = "green" if (report.coverage_pct or 0) >= 80 else "yellow" if (report.coverage_pct or 0) >= 60 else "red"

    stats.add_row("Test files",   str(report.total_files),
                  "Total tests",  str(report.total_tests))
    stats.add_row("Fixtures",     str(report.total_fixtures),
                  "Coverage",     f"[{cov_style}]{cov}[/{cov_style}]")
    stats.add_row("Errors",       f"[red]{report.errors}[/red]",
                  "Warnings",     f"[yellow]{report.warnings}[/yellow]")
    stats.add_row("Info notes",   f"[cyan]{report.infos}[/cyan]",
                  "conftest.py",  str(len(report.conftest_paths)))
    console.print(stats)
    console.print()

    # ── issues by file ────────────────────────────────────────────────────
    files_with_issues = [f for f in report.files if f.issues]
    if not files_with_issues:
        console.print("  [bold green]✔  No issues found.[/bold green]")
        console.print()
    else:
        console.print(Rule("[bold]Issues by file[/bold]", style="bright_blue"))
        console.print()
        for fr in files_with_issues:
            rel = str(Path(fr.path).relative_to(Path(report.root).parent)
                      if Path(report.root).parent in Path(fr.path).parents
                      else Path(fr.path))
            console.print(f"  [bold white]{rel}[/bold white]  "
                          f"[dim]{fr.test_count} tests · {fr.fixture_count} fixtures[/dim]")
            for issue in fr.issues:
                icon  = LEVEL_ICON[issue.level]
                style = LEVEL_STYLE[issue.level]
                loc   = f"[dim]:{issue.line}[/dim]" if issue.line else ""
                console.print(f"    [{style}]{icon}[/{style}] "
                              f"[dim]{issue.code}[/dim]{loc}  {issue.message}")
            console.print()

    # ── issue summary table ───────────────────────────────────────────────
    if report.total_issues:
        # group by code
        from collections import Counter
        codes: Counter = Counter()
        msgs: dict = {}
        for f in report.files:
            for i in f.issues:
                codes[i.code] += 1
                msgs[i.code]   = (i.level, i.message.split(":")[0] if ":" in i.message else i.message[:60])

        tbl = Table(title="Issue Summary", box=box.ROUNDED, border_style="bright_blue",
                    title_style="bold white", padding=(0, 1))
        tbl.add_column("Code",    style="dim",        width=6)
        tbl.add_column("Level",   width=9)
        tbl.add_column("Count",   justify="right",    width=6)
        tbl.add_column("Description")

        for code, count in sorted(codes.items(), key=lambda x: -x[1]):
            level, msg = msgs[code]
            style = LEVEL_STYLE[level]
            tbl.add_row(code, f"[{style}]{level}[/{style}]", str(count), msg)

        console.print(tbl)
        console.print()

    # ── fixture scope breakdown ───────────────────────────────────────────
    all_fixtures = [fx for f in report.files for fx in f.fixtures]
    if all_fixtures:
        from collections import Counter
        scopes = Counter(fx["scope"] for fx in all_fixtures)
        console.print(Rule("[bold]Fixture scope breakdown[/bold]", style="bright_blue"))
        for scope, count in sorted(scopes.items(), key=lambda x: -x[1]):
            bar = "▓" * min(count, 30)
            console.print(f"  [cyan]{scope:10s}[/cyan] {bar}  {count}")
        console.print()

    # ── coverage detail ───────────────────────────────────────────────────
    if report.coverage_pct is not None and report.coverage_missing:
        console.print(Rule("[bold]Coverage gaps (top 10)[/bold]", style="bright_blue"))
        for line in report.coverage_missing:
            console.print(f"  [dim]  •  {line}[/dim]")
        console.print()

    # ── registered marks ─────────────────────────────────────────────────
    if report.registered_marks:
        marks_str = "  ".join(f"[cyan]@{m}[/cyan]" for m in report.registered_marks)
        console.print(Rule("[bold]Registered marks[/bold]", style="bright_blue"))
        console.print(f"  {marks_str}")
        console.print()

    # ── footer ────────────────────────────────────────────────────────────
    console.print(Panel(
        f"[dim]Run [bold]pytest --quality-report[/bold] to integrate into your test run  "
        f"·  Add [bold]--html-report=report.html[/bold] for full HTML output[/dim]",
        border_style="dim", padding=(0, 1),
    ))
    console.print()
