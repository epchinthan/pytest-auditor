"""
pytest_auditor/__main__.py
──────────────────────────
Standalone CLI:   python -m pytest_auditor <tests_dir> [--html report.html] [--json report.json]
pytest plugin:    pytest --quality-report [--report-html=report.html]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


# ── standalone CLI ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pytest_auditor",
        description="Audit a pytest test suite for quality, coverage, and best practices",
    )
    parser.add_argument("path", nargs="?", default="tests",
                        help="Path to tests directory (default: tests/)")
    parser.add_argument("--html", metavar="FILE",
                        help="Write HTML report to FILE (default: pytest_audit.html)")
    parser.add_argument("--json", metavar="FILE",
                        help="Write JSON report to FILE")
    parser.add_argument("--no-terminal", action="store_true",
                        help="Suppress terminal output")
    parser.add_argument("--fail-under", type=int, default=0, metavar="SCORE",
                        help="Exit with code 1 if quality score < SCORE")
    args = parser.parse_args(argv)

    from .analyse   import scan
    from .terminal  import print_report
    from .html_report import generate_html

    root = Path(args.path)
    if not root.exists():
        print(f"[error] Path not found: {root}", file=sys.stderr)
        return 2

    report = scan(root)

    if not args.no_terminal:
        print_report(report)

    # HTML output
    html_path = Path(args.html) if args.html else Path("pytest_audit.html")
    generate_html(report, html_path)
    if not args.no_terminal:
        from rich.console import Console
        Console().print(f"  [dim]HTML report → [link={html_path.resolve().as_uri()}]{html_path}[/link][/dim]")

    # JSON output
    if args.json:
        jpath = Path(args.json)

        def _serialise(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return asdict(obj)
            raise TypeError(type(obj))

        jpath.write_text(
            json.dumps(asdict(report), indent=2, default=str),
            encoding="utf-8",
        )
        if not args.no_terminal:
            from rich.console import Console
            Console().print(f"  [dim]JSON report → {jpath}[/dim]")

    if args.fail_under and report.score < args.fail_under:
        print(f"\n[fail] Quality score {report.score} is below threshold {args.fail_under}",
              file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())


# ── pytest plugin ─────────────────────────────────────────────────────────────

def pytest_addoption(parser):
    group = parser.getgroup("audit", "pytest-auditor quality report")
    group.addoption("--quality-report", action="store_true", default=False,
                    help="Run quality audit after tests and print report")
    group.addoption("--report-html", metavar="PATH", default="pytest_audit.html",
                    help="HTML audit report output path (default: pytest_audit.html)")
    group.addoption("--report-json", metavar="PATH", default=None,
                    help="JSON audit report output path")
    group.addoption("--report-fail-under", type=int, default=0, metavar="SCORE",
                    help="Fail if quality score below SCORE")


def pytest_sessionfinish(session, exitstatus):
    if not session.config.getoption("--quality-report", default=False):
        return

    from .analyse     import scan
    from .terminal    import print_report, console
    from .html_report import generate_html
    from dataclasses  import asdict
    import json

    # find the tests root from rootdir + testpaths
    rootdir = Path(session.config.rootdir)
    testpaths = session.config.getini("testpaths") or ["tests"]
    tests_root = rootdir / testpaths[0]
    if not tests_root.exists():
        tests_root = rootdir

    report = scan(tests_root)
    console.print("\n")
    print_report(report)

    html_path = Path(session.config.getoption("--report-html"))
    generate_html(report, html_path)
    console.print(f"  [dim]HTML report → [bold]{html_path}[/bold][/dim]\n")

    json_path = session.config.getoption("--report-json")
    if json_path:
        Path(json_path).write_text(json.dumps(asdict(report), indent=2, default=str))

    fail_under = session.config.getoption("--report-fail-under")
    if fail_under and report.score < fail_under:
        console.print(
            f"[bold red]Quality score {report.score} < threshold {fail_under} — failing build[/bold red]"
        )
        session.exitstatus = 1
