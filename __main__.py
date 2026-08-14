"""
pytest-auditor — CLI entry point and pytest plugin.
__main__.py lives at the project root alongside core/, io/, scanning/.

Usage:
    python __main__.py tests/
    python __main__.py --file test_foo.py
    python __main__.py --file test_foo.py --test test_something
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _bootstrap():
    """Add HERE to sys.path so subpackages (core/, io/, scanning/) are importable."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))


# ── standalone CLI ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    _bootstrap()

    from reporting.html_report import generate_html
    from reporting.terminal import console, print_report
    from scanning.scanner import scan, scan_file, scan_test

    parser = argparse.ArgumentParser(
        prog="pytest-auditor",
        description="Audit a pytest test suite — 59 checks, terminal + HTML report",
    )
    parser.add_argument("path", nargs="?", default="tests",
                        help="Path to tests directory or single .py file (default: tests/)")
    parser.add_argument("--file", metavar="FILE",
                        help="Audit a single test file only")
    parser.add_argument("--test", metavar="TEST_NAME",
                        help="Audit a single test function (requires --file)")
    parser.add_argument("--html", metavar="FILE",
                        help="HTML report path (default: pytest_audit.html)")
    parser.add_argument("--json", metavar="FILE",
                        help="JSON report path")
    parser.add_argument("--no-terminal", action="store_true",
                        help="Suppress terminal output")
    parser.add_argument("--fail-under", type=int, default=0, metavar="SCORE",
                        help="Exit 1 if quality score < SCORE")
    args = parser.parse_args(argv)

    if args.test and not args.file:
        print("Error: --test requires --file", file=sys.stderr)
        return 2

    def resolve(p: str) -> Path:
        """Expand ~ and make absolute, regardless of how the path was passed."""
        import os
        return Path(os.path.abspath(os.path.expanduser(p)))

    try:
        if args.test:
            report = scan_test(resolve(args.file), args.test)
        elif args.file:
            report = scan_file(resolve(args.file))
        else:
            root = resolve(args.path)
            if not root.exists():
                print(f"Error: path not found: {root}", file=sys.stderr)
                return 2
            report = scan_file(root) if root.is_file() else scan(root)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if not args.no_terminal:
        print_report(report)

    html_path = resolve(args.html) if args.html else Path("pytest_audit.html").resolve()
    generate_html(report, html_path)
    if not args.no_terminal:
        console.print(f"  [dim]HTML report → {html_path.resolve()}[/dim]")

    if args.json:
        Path(args.json).write_text(
            json.dumps(asdict(report), indent=2, default=str), encoding="utf-8"
        )
        if not args.no_terminal:
            console.print(f"  [dim]JSON → {args.json}[/dim]")

    if args.fail_under and report.score < args.fail_under:
        print(f"\nScore {report.score} below threshold {args.fail_under}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())


# ── pytest plugin ─────────────────────────────────────────────────────────────

def pytest_addoption(parser):
    group = parser.getgroup("audit", "pytest-auditor")
    group.addoption("--quality-report", action="store_true", default=False,
                    help="Run quality audit after tests")
    group.addoption("--report-html", metavar="PATH", default="pytest_audit.html",
                    help="HTML report path")
    group.addoption("--report-json", metavar="PATH", default=None,
                    help="JSON report path")
    group.addoption("--report-fail-under", type=int, default=0, metavar="SCORE",
                    help="Fail if score below SCORE")


def pytest_sessionfinish(session, exitstatus):
    if not session.config.getoption("--quality-report", default=False):
        return

    _bootstrap()

    from reporting.html_report import generate_html
    from reporting.terminal import console, print_report
    from scanning.scanner import scan

    rootdir    = Path(session.config.rootdir)
    testpaths  = session.config.getini("testpaths") or ["tests"]
    tests_root = rootdir / testpaths[0]
    if not tests_root.exists():
        tests_root = rootdir

    report = scan(tests_root)
    console.print("\n")
    print_report(report)

    html_path = Path(session.config.getoption("--report-html"))
    generate_html(report, html_path)
    console.print(f"  [dim]HTML → [bold]{html_path}[/bold][/dim]\n")

    json_path = session.config.getoption("--report-json")
    if json_path:
        Path(json_path).write_text(
            json.dumps(asdict(report), indent=2, default=str)
        )

    fail_under = session.config.getoption("--report-fail-under")
    if fail_under and report.score < fail_under:
        console.print(f"[bold red]Score {report.score} < {fail_under} — failing[/bold red]")
        session.exitstatus = 1