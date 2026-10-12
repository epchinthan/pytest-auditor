"""
file_analyzer.py
────────────────
Parses a single test file, runs all checks against it, and returns
a FileReport. This is the core AST-walk + check-orchestration layer.
"""
from __future__ import annotations

import ast
from collections import Counter, defaultdict
from pathlib import Path

from core import ast_helpers as h
from core import checks
from core import playwright as pw
from core.models import INFO, FileReport, Issue


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

    playwright_file = bool(pw.imports(tree)) or any(
        h.is_test_func(n) and pw.is_playwright(n, tree) for n in ast.walk(tree)
    )
    if playwright_file:
        registered_marks = registered_marks | pw.MARKS

    report.line_count = source.count("\n") + 1

    # ── file-level checks ──────────────────────────────────────────────────
    report.issues += checks.check_file_naming(path)
    report.issues += checks.check_file_length(path, report.line_count)
    report.issues += checks.check_credentials(source, path)
    report.issues += checks.check_unittest_mock_import(tree, path)
    report.issues += checks.check_module_level_mock(tree, path)
    report.issues += checks.check_import_style(tree, path)
    report.issues += checks.check_function_comments(tree, source, path)

    # ── collect fixtures defined in this file ──────────────────────────────
    file_fixtures: dict[str, ast.AST] = {}
    fixture_meta:  dict[str, dict]    = {}

    for node in ast.walk(tree):
        if not h.is_fixture(node):
            continue

        name    = node.name
        scope   = h.fixture_scope(node)
        autouse = h.fixture_autouse(node)

        if name in file_fixtures:
            report.issues.append(Issue("warning", "FX11",
                f"Fixture '{name}' is defined more than once in the same file",
                rel, node.lineno))
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
        report.issues += checks.check_fixture_style(node, path)

    # ── scope compatibility ────────────────────────────────────────────────
    all_scopes = {
        **(pw.FIXTURE_SCOPES if playwright_file else {}),
        **conftest_fixtures,
        **{n: fixture_meta[n]["scope"] for n in fixture_meta},
    }
    for name, node in file_fixtures.items():
        caller_scope = all_scopes.get(name, "function")
        for arg in node.args.args:
            if arg.arg in all_scopes:
                report.issues += checks.check_fixture_scope_compat(
                    name, caller_scope, arg.arg, all_scopes[arg.arg], path, node.lineno
                )

    # ── OR09: all in classes but no class-scoped fixture ──────────────────
    top_nodes = list(ast.iter_child_nodes(tree))
    if h.all_classes_no_class_fixtures(top_nodes, fixture_meta):
        report.issues.append(Issue(INFO, "OR09",
            "All tests in classes but no class-scoped fixture — plain functions may be simpler",
            rel))

    # ── walk test functions ────────────────────────────────────────────────
    known_fixture_names = set(file_fixtures) | set(conftest_fixtures)
    module_marks        = h.get_module_marks(tree)
    if module_marks:
        report.issues += checks.check_registered_marks(
            module_marks, registered_marks, path, 1, "module pytestmark"
        )
    name_lines: dict[str, list[int]] = defaultdict(list)
    fixture_usage: Counter = Counter()

    def walk_tests(nodes: list, class_name: str | None = None, unittest_class: bool = False) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                if h.is_test_class(node) or h.is_unittest_class(node, tree):
                    report.class_count += 1
                    report.issues += checks.check_class(node, path, tree)
                    if not h.is_unittest_class(node, tree):
                        report.issues += checks.check_class_init(node, path)
                    report.issues += checks.check_registered_marks(
                        h.get_marks(node), registered_marks, path, node.lineno,
                        f"class '{node.name}'",
                    )
                    walk_tests(node.body, class_name=node.name, unittest_class=h.is_unittest_class(node, tree))
                else:
                    report.issues += checks.check_non_test_class(node, path)
                continue

            if not h.is_func(node):
                continue
            if h.is_fixture(node):
                continue
            if not (h.is_test_func(node) or unittest_class and node.name.startswith("test")):
                report.issues += checks.check_check_prefix(node, path, tree)
                continue

            report.test_count += 1
            if h.is_async(node):
                report.async_count += 1

            name_lines[f"{class_name}.{node.name}" if class_name else node.name].append(node.lineno)

            for arg in node.args.args:
                if arg.arg in known_fixture_names:
                    fixture_usage[arg.arg] += 1

            issues = checks.check_test(
                node, path, class_name, known_fixture_names, registered_marks, tree
            )
            _pfx = f"[{class_name}] " if class_name else ""
            issues += checks.check_assert_style(node, path, _pfx)
            issues += checks.check_test_structure(node, path, _pfx)
            issues += checks.check_warns_usage(node, path, _pfx)
            if not unittest_class:
                issues += checks.check_unittest_style(node, path, _pfx)
            issues += checks.check_mock_style(node, path, _pfx)
            report.tests.append({
                "name":    node.name,
                "line":    node.lineno,
                "class":   class_name,
                "asserts": pw.assertion_count(node, tree),
                "framework": "unittest" if unittest_class else "playwright" if pw.is_playwright(node, tree) else "pytest",
                "async":   h.is_async(node),
                "marks":   h.get_marks(node) + module_marks,
                "lines":   len(node.body),
                "flags":   [i.code for i in issues],
            })
            report.issues += issues

    walk_tests(tree.body)

    # ── post-walk checks ───────────────────────────────────────────────────
    report.issues += checks.check_duplicate_names(name_lines, path)
    report.issues += checks.check_empty_file(path, report.test_count, report.fixture_count)

    return report