"""
targeted.py
───────────
Focused audit modes: scan a single file, or a single test function.
When scanning a single test, also checks its fixtures and called helpers.
"""
from __future__ import annotations

import ast
import datetime
from pathlib import Path

from core import ast_helpers as h
from core import checks
from core.models import INFO, FileReport, Issue, SuiteReport
from reporting.config import (
    collect_conftest_fixtures,
    is_excluded,
    read_config,
    read_coverage,
)

from scanning.file_analyzer import analyse_file
from scanning.suite_scanner import _aggregate, _compute_score

# ── single file ───────────────────────────────────────────────────────────────

def scan_file(file_path: Path) -> SuiteReport:
    """
    Audit one test file. Reads config and conftest fixtures from the
    directory hierarchy as normal, but only analyses the specified file.
    """
    file_path   = file_path.resolve()
    config_root = _find_config_root(file_path)
    reg_marks, _ = read_config(config_root)
    cov_pct, cov_miss = read_coverage(config_root)

    report = SuiteReport(
        root             = str(file_path),
        generated_at     = _now(),
        registered_marks = reg_marks,
        coverage_pct     = cov_pct,
        coverage_missing = cov_miss,
        conftest_paths   = _conftest_paths(file_path),
    )

    conftest_fixtures = _load_conftest_fixtures(file_path)
    report.files.append(analyse_file(file_path, set(reg_marks), conftest_fixtures))

    _aggregate(report)
    _compute_score(report)
    return report


# ── single test function ──────────────────────────────────────────────────────

def scan_test(file_path: Path, test_name: str) -> SuiteReport:
    """
    Audit one test function within a file.

    Checks run against:
      - the test function itself
      - every fixture it declares as a parameter
      - every helper function it calls (including self.method())
    """
    file_path   = file_path.resolve()
    config_root = _find_config_root(file_path)
    reg_marks, _ = read_config(config_root)
    cov_pct, cov_miss = read_coverage(config_root)

    conftest_fixtures = _load_conftest_fixtures(file_path)
    tree, _source     = _parse(file_path)

    # locate target test
    target_node, target_class = _find_test(tree, test_name, file_path)

    # collect fixtures and helpers defined in the file
    file_fixtures = {
        node.name: node
        for node in ast.walk(tree)
        if h.is_fixture(node)
    }
    file_helpers = {
        node.name: node
        for node in ast.walk(tree)
        if h.is_func(node)
        and not h.is_fixture(node)
        and not h.is_test_func(node)
    }

    # run checks on the target test
    all_fixture_names = set(file_fixtures) | set(conftest_fixtures)
    module_marks      = h.get_module_marks(tree)
    test_issues       = checks.check_test(
        target_node, file_path, target_class, all_fixture_names, set(reg_marks), tree
    )

    focused = FileReport(path=str(file_path), test_count=1)
    focused.tests.append({
        "name":    target_node.name,
        "line":    target_node.lineno,
        "class":   target_class,
        "asserts": h.assert_count(target_node),
        "async":   h.is_async(target_node),
        "marks":   h.get_marks(target_node) + module_marks,
        "lines":   len(target_node.body),
        "flags":   [i.code for i in test_issues],
    })
    focused.issues += test_issues

    # check fixtures the test uses
    used_fixture_names = [
        arg.arg for arg in target_node.args.args
        if arg.arg in file_fixtures or arg.arg in conftest_fixtures
    ]
    for fname in used_fixture_names:
        if fname in file_fixtures:
            fnode = file_fixtures[fname]
            focused.fixture_count += 1
            focused.fixtures.append({
                "name":    fname,
                "scope":   h.fixture_scope(fnode),
                "line":    fnode.lineno,
                "async":   h.is_async(fnode),
                "yield":   h.uses_yield(fnode),
                "autouse": h.fixture_autouse(fnode),
                "bodylen": len(fnode.body),
            })
            focused.issues += checks.check_fixture(fnode, file_path)
        elif fname in conftest_fixtures:
            focused.fixture_count += 1
            focused.fixtures.append({
                "name": fname, "scope": conftest_fixtures[fname],
                "line": 0, "async": False, "yield": True,
                "autouse": False, "bodylen": 0,
            })

    # note helper functions called by the test
    for hname in _called_helpers(target_node, file_helpers):
        focused.issues.append(Issue(INFO, "INFO",
            f"Helper used: {hname}() — not a test or fixture, not checked separately",
            str(file_path)))

    report = SuiteReport(
        root             = str(file_path),
        generated_at     = _now(),
        registered_marks = reg_marks,
        coverage_pct     = cov_pct,
        coverage_missing = cov_miss,
        conftest_paths   = _conftest_paths(file_path),
    )
    report.files.append(focused)
    _aggregate(report)
    _compute_score(report)
    return report


# ── internal helpers ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _find_config_root(file_path: Path) -> Path:
    for parent in file_path.parents:
        if (parent / "pyproject.toml").exists() or (parent / "pytest.ini").exists():
            return parent
    return file_path.parent


def _conftest_paths(file_path: Path) -> list[str]:
    return [
        str(p / "conftest.py")
        for p in reversed(file_path.parents)
        if (p / "conftest.py").exists() and not is_excluded(p / "conftest.py")
    ]


def _load_conftest_fixtures(file_path: Path) -> dict[str, str]:
    fixtures: dict[str, str] = {}
    for parent in reversed(file_path.parents):
        cf = parent / "conftest.py"
        if cf.exists() and not is_excluded(cf):
            fixtures.update(collect_conftest_fixtures(cf))
    return fixtures


def _parse(file_path: Path) -> tuple[ast.AST, str]:
    try:
        source = file_path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(file_path)), source
    except (SyntaxError, OSError, UnicodeDecodeError) as e:
        raise ValueError(f"Cannot parse {file_path}: {e}") from e


def _find_test(
    tree: ast.AST, test_name: str, file_path: Path
) -> tuple[ast.AST, str | None]:
    """Find the named test node. Searches top level and inside classes."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if h.is_func(child) and child.name == test_name:
                    return child, node.name
        if h.is_func(node) and node.name == test_name:
            return node, None

    available = [n.name for n in ast.walk(tree) if h.is_test_func(n)]
    raise ValueError(
        f"Test '{test_name}' not found in {file_path.name}.\n"
        f"Available tests: {available}"
    )


def _called_helpers(node: ast.AST, candidates: dict[str, ast.AST]) -> list[str]:
    """Names from candidates that are called or referenced inside node."""
    used = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in candidates:
            used.append(n.id)
        if isinstance(n, ast.Attribute) and n.attr in candidates:
            used.append(n.attr)
    return list(dict.fromkeys(used))