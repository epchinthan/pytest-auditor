"""
scanner.py
──────────
File discovery, config reading, coverage parsing, conftest collection,
and suite-level aggregation. Orchestrates checks.py and ast_helpers.py
into a complete SuiteReport.
"""
from __future__ import annotations

import ast
import datetime
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import ast_helpers as h
import checks
from models import (
    EXCLUDE_DIRS,
    INFO,
    WARNING,
    FileReport,
    Issue,
    SuiteReport,
)

# ── path filtering ────────────────────────────────────────────────────────────

def is_excluded(path: Path) -> bool:
    return any(
        part in EXCLUDE_DIRS or part.endswith(".egg-info")
        for part in path.parts
    )


# ── config reader ─────────────────────────────────────────────────────────────

def read_config(root: Path) -> tuple[list[str], list[str]]:
    """Return (registered_marks, testpaths) from pyproject.toml or pytest.ini."""
    marks: list[str] = []
    paths: list[str] = []

    for candidate in (root / "pyproject.toml", root.parent / "pyproject.toml"):
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            m = re.search(r"markers\s*=\s*\[(.*?)\]", text, re.DOTALL)
            if m:
                marks = re.findall(r'["\'](\w+)["\']', m.group(1))
            m2 = re.search(r"testpaths\s*=\s*\[(.*?)\]", text, re.DOTALL)
            if m2:
                paths = re.findall(r'["\']([^"\']+)["\']', m2.group(1))
            break

    for candidate in (root / "pytest.ini", root.parent / "pytest.ini"):
        if candidate.exists() and not marks:
            text = candidate.read_text(encoding="utf-8")
            sec = re.search(r"\[pytest\](.*?)(?:\[|$)", text, re.DOTALL)
            if sec:
                marks.extend(re.findall(r"^\s+(\w+):", sec.group(1), re.MULTILINE))
            break

    return marks, paths


# ── coverage reader ───────────────────────────────────────────────────────────

def read_coverage(root: Path) -> tuple[float | None, list[str]]:
    """Parse coverage.json if present."""
    for candidate in (root / "coverage.json", root.parent / "coverage.json"):
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                pct = data.get("totals", {}).get("percent_covered")
                missing = [
                    f"{fn}: lines {','.join(str(l) for l in fd.get('missing_lines', [])[:5])}"
                    for fn, fd in data.get("files", {}).items()
                    if fd.get("missing_lines")
                ][:10]
                return pct, missing
            except (OSError, KeyError, ValueError, json.JSONDecodeError):
                pass

    return None, []


# ── conftest fixture collector ────────────────────────────────────────────────

def collect_conftest_fixtures(conftest_path: Path) -> dict[str, str]:
    """Return {fixture_name: scope} for all fixtures in a conftest.py."""
    result: dict[str, str] = {}
    try:
        tree = ast.parse(conftest_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if h.is_fixture(node):
                result[node.name] = h.fixture_scope(node)
    except (SyntaxError, OSError, UnicodeDecodeError):
        pass
    return result


# ── single file analyser ──────────────────────────────────────────────────────

def analyse_file(
    path: Path,
    registered_marks: set[str],
    conftest_fixtures: dict[str, str],
) -> FileReport:
    report = FileReport(path=str(path))
    rel    = str(path)

    try:
        source = path.read_text(encoding="utf-8")
        tree   = ast.parse(source, filename=rel)
    except SyntaxError as e:
        report.issues.append(Issue("error", "F001", f"Syntax error: {e}", rel, e.lineno or 0))
        return report
    except (OSError, UnicodeDecodeError) as e:
        report.issues.append(Issue("error", "F002", f"Cannot parse: {e}", rel))
        return report

    report.line_count = source.count("\n") + 1

    # ── file-level checks ──────────────────────────────────────────────────
    report.issues += checks.check_file_naming(path)
    report.issues += checks.check_file_length(path, report.line_count)
    report.issues += checks.check_credentials(source, path)
    report.issues += checks.check_unittest_mock_import(tree, path)
    report.issues += checks.check_module_level_mock(tree, path)
    report.issues += checks.check_no_src_import(tree, path)

    # ── collect fixtures ───────────────────────────────────────────────────
    file_fixtures: dict[str, ast.AST] = {}
    fixture_meta:  dict[str, dict]    = {}

    for node in ast.walk(tree):
        if not h.is_fixture(node):
            continue

        name     = node.name
        scope    = h.fixture_scope(node)
        autouse  = h.fixture_autouse(node)

        file_fixtures[name] = node
        fixture_meta[name]  = {
            "name":    name,
            "scope":   scope,
            "line":    node.lineno,
            "async":   h.is_async(node),
            "yield":   h.uses_yield(node),
            "autouse": autouse,
            "bodylen": len(node.body),
        }
        report.fixture_count += 1
        report.fixtures.append(fixture_meta[name])

        report.issues += checks.check_fixture(node, path)
        report.issues += checks.check_fixture_shadow(name, conftest_fixtures, path, node.lineno)

    # ── scope compatibility ────────────────────────────────────────────────
    all_scopes = {
        **{n: fixture_meta[n]["scope"] for n in fixture_meta},
        **conftest_fixtures,
    }
    for name, node in file_fixtures.items():
        caller_scope = all_scopes.get(name, "function")
        for arg in node.args.args:
            if arg.arg in all_scopes:
                report.issues += checks.check_fixture_scope_compat(
                    name, caller_scope, arg.arg, all_scopes[arg.arg], path, node.lineno
                )

    # ── OR09: all in classes, no class fixture ─────────────────────────────
    top_nodes = list(ast.iter_child_nodes(tree))
    if h.all_classes_no_class_fixtures(top_nodes, fixture_meta):
        report.issues.append(Issue(INFO, "OR09",
            "All tests in classes but no class-scoped fixture — plain functions may be simpler",
            rel))

    # ── walk tests ─────────────────────────────────────────────────────────
    known_fixture_names = set(file_fixtures) | set(conftest_fixtures)
    name_lines: dict[str, list[int]] = defaultdict(list)
    fixture_usage: Counter = Counter()

    def walk_tests(nodes: list, class_name: str | None = None) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                if h.is_test_class(node):
                    report.class_count += 1
                    report.issues += checks.check_class(node, path)
                    walk_tests(node.body, class_name=node.name)
                else:
                    report.issues += checks.check_non_test_class(node, path)
                continue

            if not h.is_func(node):
                continue
            if h.is_fixture(node):
                continue
            if not h.is_test_func(node):
                report.issues += checks.check_check_prefix(node, path)
                continue

            report.test_count += 1
            if h.is_async(node):
                report.async_count += 1

            name_lines[node.name].append(node.lineno)

            for arg in node.args.args:
                if arg.arg in known_fixture_names:
                    fixture_usage[arg.arg] += 1

            issues = checks.check_test(
                node, path, class_name, known_fixture_names, registered_marks
            )

            td: dict = {
                "name":    node.name,
                "line":    node.lineno,
                "class":   class_name,
                "asserts": h.assert_count(node),
                "async":   h.is_async(node),
                "marks":   h.get_marks(node),
                "lines":   len(node.body),
                "flags":   [i.code for i in issues],
            }
            report.tests.append(td)
            report.issues += issues

    walk_tests(tree.body)

    # ── post-walk checks ───────────────────────────────────────────────────
    report.issues += checks.check_duplicate_names(name_lines, path)
    report.issues += checks.check_empty_file(path, report.test_count, report.fixture_count)

    for fname, meta in fixture_meta.items():
        report.issues += checks.check_fixture_used_once(
            fname, fixture_usage[fname], meta["autouse"], path, meta["line"]
        )

    return report


# ── suite scanner ─────────────────────────────────────────────────────────────

def scan(root: Path) -> SuiteReport:
    root           = root.resolve()
    config_root    = root.parent if root.name == "tests" else root
    reg_marks, _   = read_config(config_root)
    mark_set       = set(reg_marks)
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

    # OR08: same fixture in multiple conftest files
    for fname, sources in fixture_sources.items():
        if len(sources) > 1:
            stub = FileReport(path=str(root))
            stub.issues.append(Issue(WARNING, "OR08",
                f"Fixture '{fname}' in multiple conftest files: {sources} — inner shadows outer",
                str(root)))
            report.files.append(stub)

    # S001: no conftest at root
    if not (root / "conftest.py").exists():
        stub = FileReport(path=str(root / "conftest.py"))
        stub.issues.append(Issue(INFO, "S001",
            f"No conftest.py in {root}", str(root)))
        report.files.append(stub)

    # ── collect test files ─────────────────────────────────────────────────
    seen: set[Path] = set()
    test_files: list[Path] = []
    for pat in ("test_*.py", "*_test.py"):
        for f in sorted(root.rglob(pat)):
            if f not in seen and not is_excluded(f):
                seen.add(f)
                test_files.append(f)

    for tf in test_files:
        report.files.append(analyse_file(tf, mark_set, conftest_fixtures))

    # ── suite-wide checks ──────────────────────────────────────────────────

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

    # S004: no marks anywhere
    all_marks = [m for f in report.files for t in f.tests for m in t.get("marks", [])]
    if test_files and not all_marks:
        stub = FileReport(path=str(root))
        stub.issues.append(Issue(INFO, "S004",
            "No tests have any marks — consider tagging slow/integration/smoke tests",
            str(root)))
        report.files.append(stub)

    # ── aggregates ─────────────────────────────────────────────────────────
    report.total_files    = sum(1 for f in report.files if f.test_count > 0)
    report.total_tests    = sum(f.test_count for f in report.files)
    report.total_fixtures = sum(f.fixture_count for f in report.files)
    report.async_count    = sum(f.async_count for f in report.files)

    all_issues = [i for f in report.files for i in f.issues]
    report.total_issues = len(all_issues)
    report.errors   = sum(1 for i in all_issues if i.level == "error")
    report.warnings = sum(1 for i in all_issues if i.level == "warning")
    report.infos    = sum(1 for i in all_issues if i.level == "info")

    # ── metrics ────────────────────────────────────────────────────────────
    all_tests = [t for f in report.files for t in f.tests]
    skip_tests  = sum(1 for t in all_tests if "skip" in t.get("marks", [])
                      or "skipif" in t.get("marks", []))
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

    # per-directory breakdown
    dir_data: dict[str, dict] = defaultdict(lambda: {"tests": 0, "issues": 0, "errors": 0})
    for f in report.files:
        try:
            d = str(Path(f.path).parent.relative_to(root)) if Path(f.path).parent != root else "."
        except ValueError:
            d = "."
        dir_data[d]["tests"]  += f.test_count
        dir_data[d]["issues"] += len(f.issues)
        dir_data[d]["errors"] += sum(1 for i in f.issues if i.level == "error")
    report.dir_breakdown = dict(dir_data)

    # ── score ──────────────────────────────────────────────────────────────
    score = 100
    score -= report.errors   * 8
    score -= report.warnings * 3
    score -= report.infos    * 1
    if cov_pct is not None and cov_pct < 80:
        score -= int((80 - cov_pct) * 0.5)
    if report.test_debt_pct > 10:
        score -= int(report.test_debt_pct * 0.3)
    report.score = max(0, min(100, score))

    return report