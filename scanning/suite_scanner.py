"""
suite_scanner.py
────────────────
Walks a test directory, collects conftest fixtures, analyses every test
file, and assembles a complete SuiteReport with metrics and score.
"""
from __future__ import annotations

import datetime
from collections import defaultdict
from pathlib import Path

from core.models import INFO, WARNING, FileReport, Issue, SuiteReport
from reporting.config import (
    collect_conftest_fixtures,
    is_excluded,
    read_config,
    read_coverage,
)

from scanning.file_analyzer import analyse_file


def scan(root: Path) -> SuiteReport:
    root        = root.resolve()
    config_root = root.parent if root.name == "tests" else root
    reg_marks, _    = read_config(config_root)
    mark_set        = set(reg_marks)
    cov_pct, cov_miss = read_coverage(config_root)

    report = SuiteReport(
        root             = str(root),
        generated_at     = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        registered_marks = reg_marks,
        coverage_pct     = cov_pct,
        coverage_missing = cov_miss,
    )

    # ── conftest hierarchy ─────────────────────────────────────────────────
    conftest_files = sorted(
        f for f in root.rglob("conftest.py") if not is_excluded(f)
    )
    report.conftest_paths = [str(p) for p in conftest_files]

    conftest_fixtures: dict[str, str] = {}
    fixture_sources: dict[str, list[str]] = defaultdict(list)
    for cf in conftest_files:
        for name, scope in collect_conftest_fixtures(cf).items():
            fixture_sources[name].append(str(cf))
            conftest_fixtures[name] = scope

    # OR08: same fixture name in multiple conftest files
    for fname, sources in fixture_sources.items():
        if len(sources) > 1:
            stub = FileReport(path=str(root))
            stub.issues.append(Issue(WARNING, "OR08",
                f"Fixture '{fname}' defined in multiple conftest files: "
                f"{[str(Path(s).relative_to(root)) for s in sources]} — inner shadows outer",
                str(root)))
            report.files.append(stub)

    # S001: no conftest at root
    if not (root / "conftest.py").exists():
        stub = FileReport(path=str(root / "conftest.py"))
        stub.issues.append(Issue(INFO, "S001",
            f"No conftest.py in {root}", str(root)))
        report.files.append(stub)

    # ── collect and analyse test files ─────────────────────────────────────
    test_files = _collect_test_files(root)
    for tf in test_files:
        report.files.append(analyse_file(tf, mark_set, conftest_fixtures))

    # ── suite-wide structural checks ───────────────────────────────────────
    _check_suite_structure(report, root, test_files)

    # ── aggregates, metrics, score ─────────────────────────────────────────
    _aggregate(report)
    _compute_metrics(report)
    _compute_score(report)

    return report


# ── helpers ───────────────────────────────────────────────────────────────────

def _collect_test_files(root: Path) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for pat in ("test_*.py", "*_test.py"):
        for f in sorted(root.rglob(pat)):
            if f not in seen and not is_excluded(f):
                seen.add(f)
                files.append(f)
    return files


def _check_suite_structure(report: SuiteReport, root: Path, test_files: list[Path]) -> None:
    # OR11: no __init__.py
    if test_files and not any([
        (root / "__init__.py").exists(),
        (root / "tests" / "__init__.py").exists(),
    ]):
        stub = FileReport(path=str(root))
        stub.issues.append(Issue(INFO, "OR11",
            "No __init__.py in tests directory — cross-file imports may fail",
            str(root)))
        report.files.append(stub)

    # OR12: deeply nested
    for tf in test_files:
        if len(tf.relative_to(root).parts) > 4:
            stub = FileReport(path=str(tf))
            stub.issues.append(Issue(INFO, "OR12",
                f"'{tf.relative_to(root)}' is {len(tf.relative_to(root).parts)} levels deep",
                str(tf)))
            report.files.append(stub)
            break

    # S004: no marks anywhere — includes pytestmark assignments
    all_marks = [m for f in report.files for t in f.tests for m in t.get("marks", [])]
    if test_files and not all_marks:
        stub = FileReport(path=str(root))
        stub.issues.append(Issue(INFO, "S004",
            "No tests have any marks — consider tagging slow/integration/smoke tests",
            str(root)))
        report.files.append(stub)


def _aggregate(report: SuiteReport) -> None:
    report.total_files    = sum(1 for f in report.files if f.test_count > 0)
    report.total_tests    = sum(f.test_count for f in report.files)
    report.total_fixtures = sum(f.fixture_count for f in report.files)
    report.async_count    = sum(f.async_count for f in report.files)

    all_issues = [i for f in report.files for i in f.issues]
    report.total_issues = len(all_issues)
    report.errors   = sum(1 for i in all_issues if i.level == "error")
    report.warnings = sum(1 for i in all_issues if i.level == "warning")
    report.infos    = sum(1 for i in all_issues if i.level == "info")


def _compute_metrics(report: SuiteReport) -> None:
    all_tests = [t for f in report.files for t in f.tests]

    skip_tests  = sum(1 for t in all_tests
                      if any(m in t.get("marks", []) for m in ("skip", "skipif")))
    xfail_tests = sum(1 for t in all_tests if "xfail" in t.get("marks", []))
    report.skip_count  = skip_tests
    report.xfail_count = xfail_tests

    if report.total_tests:
        report.test_debt_pct = round(
            (skip_tests + xfail_tests) / report.total_tests * 100, 1
        )

    all_fx = [fx for f in report.files for fx in f.fixtures]
    if all_fx:
        fn_scope = sum(1 for fx in all_fx if fx.get("scope") == "function")
        report.isolation_score = round(fn_scope / len(all_fx) * 100, 1)

    dir_data: dict[str, dict] = defaultdict(lambda: {"tests": 0, "issues": 0, "errors": 0})
    root = Path(report.root)
    for f in report.files:
        try:
            d = str(Path(f.path).parent.relative_to(root)) if Path(f.path).parent != root else "."
        except ValueError:
            d = "."
        dir_data[d]["tests"]  += f.test_count
        dir_data[d]["issues"] += len(f.issues)
        dir_data[d]["errors"] += sum(1 for i in f.issues if i.level == "error")
    report.dir_breakdown = dict(dir_data)


def _compute_score(report: SuiteReport) -> None:
    score = 100
    score -= report.errors   * 8
    score -= report.warnings * 3
    score -= report.infos    * 1
    if report.coverage_pct is not None and report.coverage_pct < 80:
        score -= int((80 - report.coverage_pct) * 0.5)
    if report.test_debt_pct > 10:
        score -= int(report.test_debt_pct * 0.3)
    report.score = max(0, min(100, score))