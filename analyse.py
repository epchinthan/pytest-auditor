"""
pytest_auditor/analyse.py  v3
─────────────────────────────
Full audit engine — 70+ checks across 9 categories.
Pure stdlib; no pytest required at analysis time.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ── dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class Issue:
    level:   str   # "error" | "warning" | "info"
    code:    str
    message: str
    file:    str
    line:    int = 0

@dataclass
class FileReport:
    path:          str
    test_count:    int = 0
    class_count:   int = 0
    fixture_count: int = 0
    async_count:   int = 0
    line_count:    int = 0
    issues:        list[Issue] = field(default_factory=list)
    tests:         list[dict]  = field(default_factory=list)
    fixtures:      list[dict]  = field(default_factory=list)

@dataclass
class SuiteReport:
    root:              str
    generated_at:      str
    files:             list[FileReport] = field(default_factory=list)
    registered_marks:  list[str]        = field(default_factory=list)
    conftest_paths:    list[str]        = field(default_factory=list)
    coverage_pct:      float | None     = None
    coverage_missing:  list[str]        = field(default_factory=list)
    # aggregates
    total_tests:       int  = 0
    total_fixtures:    int  = 0
    total_files:       int  = 0
    total_issues:      int  = 0
    errors:            int  = 0
    warnings:          int  = 0
    infos:             int  = 0
    score:             int  = 100
    # extra metrics
    skip_count:        int  = 0
    xfail_count:       int  = 0
    async_count:       int  = 0
    test_debt_pct:     float = 0.0
    isolation_score:   float = 0.0   # % of tests with function-scoped fixtures
    dir_breakdown:     dict  = field(default_factory=dict)


# ── scope ordering ────────────────────────────────────────────────────────────
SCOPE_ORDER = {"function": 0, "class": 1, "module": 2, "session": 3}
BUILTIN_MARKS = {
    "slow", "skip", "skipif", "xfail", "parametrize",
    "usefixtures", "filterwarnings", "asyncio", "anyio",
    "smoke", "integration", "unit", "e2e",
}
PYTHON_BUILTINS = {
    "id", "type", "list", "dict", "set", "tuple", "str", "int",
    "float", "bool", "bytes", "range", "map", "filter", "zip",
    "len", "min", "max", "sum", "sorted", "reversed", "open",
    "print", "input", "format", "vars", "dir", "hash",
}
VAGUE_NAMES = re.compile(
    r'^test_(it|this|thing|run|go|do|check|a|b|c|1|2|3|temp|tmp|foo|bar|baz|x|y|z)$',
    re.IGNORECASE,
)
NUMBERED_NAMES = re.compile(r'^test_.*\d+$')
CREDENTIAL_PATTERN = re.compile(
    r'(password|passwd|token|api_key|apikey|secret|auth|credential)\s*=\s*["\'][^"\']{4,}["\']',
    re.IGNORECASE,
)


# ── AST helpers ───────────────────────────────────────────────────────────────

def _unparse(node: ast.AST) -> str:
    return ast.unparse(node)

def _is_func(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))

def _is_test_func(node: ast.AST) -> bool:
    return _is_func(node) and node.name.startswith("test_")

def _is_test_class(node: ast.AST) -> bool:
    return isinstance(node, ast.ClassDef) and node.name.startswith("Test")

def _is_async(node: ast.AST) -> bool:
    return isinstance(node, ast.AsyncFunctionDef)

def _is_fixture(node: ast.AST) -> bool:
    if not _is_func(node):
        return False
    return any("pytest.fixture" in _unparse(d) or _unparse(d).strip() == "fixture"
               for d in node.decorator_list)

def _fixture_scope(node: ast.AST) -> str:
    for d in node.decorator_list:
        src = _unparse(d)
        if "pytest.fixture" in src:
            m = re.search(r'scope=["\'](\w+)["\']', src)
            return m.group(1) if m else "function"
    return "function"

def _fixture_autouse(node: ast.AST) -> bool:
    return any("autouse" in _unparse(d) and "True" in _unparse(d)
               for d in node.decorator_list)

def _get_marks(node: ast.AST) -> list[str]:
    marks = []
    for d in node.decorator_list:
        marks.extend(re.findall(r'pytest\.mark\.(\w+)', _unparse(d)))
    return marks

def _assert_count(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.Assert))

def _has_loop_with_assert(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, (ast.For, ast.While)) and n is not node:
            if any(isinstance(c, ast.Assert) for c in ast.walk(n)):
                return True
    return False

def _calls_fixture(node: ast.AST, known: set[str]) -> list[str]:
    return [
        n.func.id for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in known
    ]

def _has_hardcoded_tmp(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str)
        and re.search(r'^/tmp/', n.value)
        for n in ast.walk(node)
    )

def _has_write_to_real_path(node: ast.AST) -> bool:
    """open("some/absolute/path", "w") outside tmp_path."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            fn = _unparse(n.func)
            if fn == "open" and n.args:
                first = _unparse(n.args[0])
                # look for write mode
                if len(n.args) > 1 or n.keywords:
                    mode_arg = (
                        _unparse(n.args[1]) if len(n.args) > 1 else
                        next((_unparse(k.value) for k in n.keywords if k.arg == "mode"), "")
                    )
                    if any(m in mode_arg for m in ('"w"', "'w'", '"a"', "'a'", '"x"', "'x'")):
                        # not a tmp_path-based path
                        if "tmp_path" not in first and not first.startswith("tmp"):
                            return True
    return False

def _has_asyncio_mark(node: ast.AST) -> bool:
    return any("asyncio" in _unparse(d) or "anyio" in _unparse(d)
               for d in node.decorator_list)

def _param_missing_ids(node: ast.AST) -> bool:
    for d in node.decorator_list:
        src = _unparse(d)
        if "parametrize" in src and "id=" not in src and "pytest.param" not in src:
            return True
    return False

def _param_count(node: ast.AST) -> int:
    for d in node.decorator_list:
        src = _unparse(d)
        if "parametrize" in src:
            m = re.search(r'\[(.+)\]', src, re.DOTALL)
            if m:
                inner = m.group(1)
                # count top-level commas between tuples/values
                depth, count = 0, 1
                for ch in inner:
                    if ch in "([{": depth += 1
                    elif ch in ")]}": depth -= 1
                    elif ch == "," and depth == 0: count += 1
                return count
    return 0

def _param_single(node: ast.AST) -> bool:
    return any(
        "parametrize" in _unparse(d) and _param_count(node) == 1
        for d in node.decorator_list
    )

def _param_ids_with_special_chars(node: ast.AST) -> bool:
    for d in node.decorator_list:
        src = _unparse(d)
        if "parametrize" in src and "id=" in src:
            ids = re.findall(r'id=["\']([^"\']+)["\']', src)
            if any(re.search(r'[ /\[\](){}]', i) for i in ids):
                return True
    return False

def _uses_yield(node: ast.AST) -> bool:
    yields = [n for n in ast.walk(node) if isinstance(n, ast.Yield)]
    return len(yields) > 0

def _yield_count(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.Yield))

def _has_sleep(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            fn = _unparse(n.func)
            if fn in ("time.sleep", "asyncio.sleep", "sleep"):
                return True
    return False

def _has_asyncio_sleep_zero(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            fn = _unparse(n.func)
            if fn == "asyncio.sleep" and n.args:
                val = _unparse(n.args[0])
                if val == "0":
                    return True
    return False

def _has_asyncio_run(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call) and "asyncio.run" in _unparse(n.func)
        for n in ast.walk(node)
    )

def _has_print(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"
        for n in ast.walk(node)
    )

def _has_bare_except(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.ExceptHandler):
            if n.type is None:
                return True
            if _unparse(n.type) in ("Exception", "BaseException"):
                if all(isinstance(s, (ast.Pass, ast.Continue)) for s in n.body):
                    return True
    return False

def _has_assert_in_body(node: ast.AST) -> bool:
    """Direct assert in the fixture body (not inside nested function)."""
    for stmt in node.body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Assert):
                return True
    return False

def _has_assert_true_literal(node: ast.AST) -> bool:
    """assert True or assert 1 == 1 — placeholder assertions."""
    for n in ast.walk(node):
        if isinstance(n, ast.Assert):
            val = _unparse(n.test)
            if val in ("True", "1 == 1", "(1 == 1)", "1==1"):
                return True
    return False

def _has_assert_result_bare(node: ast.AST) -> bool:
    """assert result  (bare truthy check with a single name)."""
    for n in ast.walk(node):
        if isinstance(n, ast.Assert):
            if isinstance(n.test, ast.Name) and n.test.id in (
                "result", "response", "res", "output", "ret", "rv", "data"
            ):
                return True
    return False

def _has_assert_len_gt_zero(node: ast.AST) -> bool:
    """assert len(x) > 0 — use assert x instead."""
    for n in ast.walk(node):
        if isinstance(n, ast.Assert):
            t = n.test
            if (isinstance(t, ast.Compare)
                    and isinstance(t.left, ast.Call)
                    and isinstance(t.left.func, ast.Name)
                    and t.left.func.id == "len"
                    and len(t.ops) == 1
                    and isinstance(t.ops[0], ast.Gt)
                    and len(t.comparators) == 1
                    and isinstance(t.comparators[0], ast.Constant)
                    and t.comparators[0].value == 0):
                return True
    return False

def _multi_raises(node: ast.AST) -> int:
    """Count pytest.raises context managers in a test."""
    count = 0
    for n in ast.walk(node):
        if isinstance(n, ast.With):
            for item in n.items:
                if "pytest.raises" in _unparse(item.context_expr):
                    count += 1
    return count

def _uses_unittest_patch(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call) and re.search(r'unittest\.mock\.patch|mock\.patch', _unparse(n.func))
        for n in ast.walk(node)
    )

def _mock_any_overused(node: ast.AST) -> bool:
    src = _unparse(node)
    return src.count("mock.ANY") + src.count(", ANY") >= 3

def _has_assert_called(node: ast.AST) -> bool:
    src = _unparse(node)
    return any(k in src for k in (
        "assert_called", "assert_any_call", "assert_has_calls", "call_count", "call_args"
    ))

def _patches_mock(node: ast.AST) -> bool:
    src = _unparse(node)
    return ".patch(" in src or "mocker.patch" in src

def _patch_targets(node: ast.AST) -> list[str]:
    targets = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            fn = _unparse(n.func)
            if "patch" in fn and n.args:
                targets.append(_unparse(n.args[0]).strip("\"'"))
    return targets

def _float_direct_compare(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Assert) and isinstance(n.test, ast.Compare):
            if any(isinstance(op, ast.Eq) for op in n.test.ops):
                for a in [n.test.left] + n.test.comparators:
                    if isinstance(a, ast.Constant) and isinstance(a.value, float):
                        return True
    return False

def _skip_no_reason(node: ast.AST) -> bool:
    return any(
        "mark.skip" in _unparse(d) and "reason" not in _unparse(d)
        for d in node.decorator_list
    )

def _xfail_no_reason(node: ast.AST) -> bool:
    return any(
        "mark.xfail" in _unparse(d) and "reason" not in _unparse(d)
        for d in node.decorator_list
    )

def _is_unittest_class(node: ast.AST) -> bool:
    return isinstance(node, ast.ClassDef) and any(
        "TestCase" in _unparse(b) for b in node.bases
    )

def _uses_unittest_mock_import(tree: ast.AST) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            if any("unittest.mock" in a.name for a in n.names):
                return True
        if isinstance(n, ast.ImportFrom):
            if n.module and "unittest.mock" in n.module:
                return True
    return False

def _module_level_mock(tree: ast.AST) -> bool:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            src = _unparse(node)
            if re.search(r'\bMagicMock\(\)|\bMock\(\)', src):
                return True
    return False

def _modifies_environ_directly(node: ast.AST) -> bool:
    """os.environ[...] = ... or os.environ.update(...) without monkeypatch."""
    src = _unparse(node)
    return bool(re.search(r'os\.environ\s*\[.*\]\s*=|os\.environ\.(?:update|pop|setdefault)\s*\(', src))

def _hardcoded_credential(source: str, node: ast.AST) -> list[str]:
    """Look for password='literal', token='literal' etc in test body."""
    found = []
    body_src = _unparse(node)
    for m in CREDENTIAL_PATTERN.finditer(body_src):
        found.append(m.group(0)[:40])
    return found

def _source_imports(tree: ast.AST) -> list[str]:
    """All module names imported in this file."""
    modules = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            modules.extend(a.name for a in n.names)
        if isinstance(n, ast.ImportFrom) and n.module:
            modules.append(n.module)
    return modules

def _has_no_src_import(tree: ast.AST, src_root: Path | None) -> bool:
    """True if the test file imports nothing that looks like production code."""
    imports = _source_imports(tree)
    if not imports:
        return True
    stdlib_prefixes = {
        "os", "sys", "re", "json", "time", "datetime", "math",
        "random", "io", "abc", "copy", "functools", "itertools",
        "collections", "pathlib", "typing", "dataclasses",
        "contextlib", "threading", "asyncio", "logging", "warnings",
        "unittest", "pytest", "mock", "conftest",
    }
    return all(
        any(imp.startswith(p) for p in stdlib_prefixes)
        for imp in imports
    )

def _all_classes_no_class_fixtures(nodes: list, file_fixtures: dict) -> bool:
    """All tests are in classes but no class-scoped fixture exists."""
    has_class = any(isinstance(n, ast.ClassDef) and _is_test_class(n) for n in nodes)
    has_func   = any(_is_test_func(n) for n in nodes)
    if not has_class or has_func:
        return False
    return not any(
        fx.get("scope") == "class" for fx in file_fixtures.values()
    )


# ── file analyser ─────────────────────────────────────────────────────────────

def analyse_file(
    path: Path,
    registered_marks: set[str],
    all_conftest_fixtures: dict[str, str],  # name → scope from parent conftest files
    src_root: Path | None = None,
) -> FileReport:
    report = FileReport(path=str(path))
    rel = str(path)

    try:
        source = path.read_text(encoding="utf-8")
        tree   = ast.parse(source, filename=rel)
    except SyntaxError as e:
        report.issues.append(Issue("error", "F001", f"Syntax error: {e}", rel, e.lineno or 0))
        return report
    except Exception as e:
        report.issues.append(Issue("error", "F002", f"Cannot parse: {e}", rel))
        return report

    report.line_count = source.count("\n") + 1

    # ── F003 credential in source ──────────────────────────────────────────
    for m in CREDENTIAL_PATTERN.finditer(source):
        ln = source[:m.start()].count("\n") + 1
        report.issues.append(Issue("warning", "F003",
            f"Possible hardcoded credential: {m.group(0)[:50]}",
            rel, ln))

    # ── file-level checks ──────────────────────────────────────────────────
    if not (path.name.startswith("test_") or path.name.endswith("_test.py")):
        report.issues.append(Issue("warning", "N001",
            f"'{path.name}' doesn't follow naming convention (test_*.py or *_test.py)", rel))

    if report.line_count > 200:
        report.issues.append(Issue("info", "S002",
            f"File is {report.line_count} lines — consider splitting", rel))

    if _uses_unittest_mock_import(tree):
        report.issues.append(Issue("info", "MK04",
            "Direct unittest.mock import — prefer mocker fixture (pytest-mock) "
            "for automatic cleanup", rel))

    if _module_level_mock(tree):
        report.issues.append(Issue("warning", "MK05",
            "MagicMock()/Mock() created at module level — shared between all tests; "
            "move into a fixture or test function", rel))

    # ── OR10: no source imports ────────────────────────────────────────────
    if _has_no_src_import(tree, src_root):
        # only flag if there are actual tests
        if any(_is_test_func(n) for n in ast.walk(tree)):
            report.issues.append(Issue("info", "OR10",
                "No imports from production code detected — "
                "this test file may not be testing any real application logic", rel))

    # ── collect fixtures ───────────────────────────────────────────────────
    file_fixtures: dict[str, Any] = {}   # name → ast node
    fixture_meta: dict[str, dict] = {}   # name → metadata dict

    for node in ast.walk(tree):
        if _is_fixture(node):
            name       = node.name
            scope      = _fixture_scope(node)
            autouse    = _fixture_autouse(node)
            uses_yield = _uses_yield(node)
            yield_cnt  = _yield_count(node)
            body_len   = len(node.body)
            async_fix  = _is_async(node)

            file_fixtures[name] = node
            fixture_meta[name] = {
                "name":    name,
                "scope":   scope,
                "line":    node.lineno,
                "async":   async_fix,
                "yield":   uses_yield,
                "autouse": autouse,
                "bodylen": body_len,
            }
            report.fixture_count += 1
            report.fixtures.append(fixture_meta[name])

            # FX01 many stmts no yield
            if body_len > 2 and not uses_yield:
                report.issues.append(Issue("info", "FX01",
                    f"Fixture '{name}' has {body_len} statements but uses return — "
                    "consider yield for guaranteed teardown", rel, node.lineno))

            # FX02 assert inside fixture
            if _has_assert_in_body(node):
                report.issues.append(Issue("warning", "FX02",
                    f"Fixture '{name}' contains assert — "
                    "assertion failures show as ERROR not FAILED", rel, node.lineno))

            # FX03 very long
            if body_len > 30:
                report.issues.append(Issue("info", "FX03",
                    f"Fixture '{name}' is {body_len} lines — "
                    "consider splitting into smaller composed fixtures", rel, node.lineno))

            # FX04 autouse session
            if autouse and scope == "session":
                report.issues.append(Issue("warning", "FX04",
                    f"Fixture '{name}': autouse=True + session scope affects every test "
                    "in the entire run — ensure this is intentional", rel, node.lineno))

            # FX06 yields more than once
            if yield_cnt > 1:
                report.issues.append(Issue("warning", "FX06",
                    f"Fixture '{name}' yields {yield_cnt} times — "
                    "only the first yield is used; the rest are silently ignored", rel, node.lineno))

            # FX07 parameter shadows builtin
            for arg in node.args.args:
                if arg.arg in PYTHON_BUILTINS and arg.arg not in file_fixtures:
                    report.issues.append(Issue("info", "FX07",
                        f"Fixture '{name}': parameter '{arg.arg}' shadows a Python builtin",
                        rel, arg.col_offset))

            # FX08 shadowing conftest fixture
            if name in all_conftest_fixtures:
                report.issues.append(Issue("info", "FX08",
                    f"Fixture '{name}' shadows a fixture of the same name "
                    f"defined in conftest.py (scope: {all_conftest_fixtures[name]}) — "
                    "may be intentional or accidental",
                    rel, node.lineno))

    known_fixture_names = set(file_fixtures.keys()) | set(all_conftest_fixtures.keys())

    # ── scope compatibility (FX05) ─────────────────────────────────────────
    all_scopes = {**{n: fixture_meta[n]["scope"] for n in fixture_meta},
                  **all_conftest_fixtures}

    for name, node in file_fixtures.items():
        caller_scope = all_scopes.get(name, "function")
        for arg in node.args.args:
            pname = arg.arg
            if pname in all_scopes:
                callee_scope = all_scopes[pname]
                if SCOPE_ORDER.get(caller_scope, 0) > SCOPE_ORDER.get(callee_scope, 0):
                    report.issues.append(Issue("error", "FX05",
                        f"Scope mismatch: '{name}' ({caller_scope}) depends on "
                        f"'{pname}' ({callee_scope}) — outer scope must be ≥ inner scope",
                        rel, node.lineno))

    # ── OR09: all tests in classes but no class-level fixtures ────────────
    top_nodes = list(ast.iter_child_nodes(tree))
    if _all_classes_no_class_fixtures(top_nodes, fixture_meta):
        report.issues.append(Issue("info", "OR09",
            "All tests are inside classes but no class-scoped fixture exists — "
            "plain functions may be simpler than classes here", rel))

    # ── walk tests ─────────────────────────────────────────────────────────
    test_names_seen: dict[str, list[int]] = defaultdict(list)
    fixture_usage_count: Counter = Counter()

    def walk_tests(nodes: list, class_name: str | None = None) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                if _is_test_class(node):
                    report.class_count += 1
                    if _is_unittest_class(node):
                        report.issues.append(Issue("warning", "N004",
                            f"'{node.name}' inherits from TestCase — "
                            "pytest fixtures won't be injected", rel, node.lineno))
                    test_methods = [n for n in node.body if _is_test_func(n)]
                    if not test_methods:
                        report.issues.append(Issue("info", "N005",
                            f"Class '{node.name}' has no test methods", rel, node.lineno))
                    walk_tests(node.body, class_name=node.name)
                elif any(_is_test_func(n) for n in ast.walk(node)):
                    report.issues.append(Issue("warning", "N003",
                        f"Class '{node.name}' doesn't start with 'Test' — "
                        "its tests won't be collected", rel, node.lineno))
                continue

            if not _is_func(node):
                continue
            if _is_fixture(node):
                continue
            if not _is_test_func(node):
                if node.name.startswith(("check_", "verify_")):
                    report.issues.append(Issue("warning", "N002",
                        f"'{node.name}' starts with check_/verify_ — "
                        "pytest won't collect it; rename to test_", rel, node.lineno))
                continue

            report.test_count += 1
            is_async  = _is_async(node)
            n_asserts = _assert_count(node)
            marks     = _get_marks(node)
            pfx       = f"[{class_name}] " if class_name else ""
            body_src  = _unparse(node)
            fn_len    = len(node.body)

            if is_async:
                report.async_count += 1

            test_names_seen[node.name].append(node.lineno)

            # track which fixtures are used
            for arg in node.args.args:
                if arg.arg in known_fixture_names:
                    fixture_usage_count[arg.arg] += 1

            td: dict[str, Any] = {
                "name":    node.name,
                "line":    node.lineno,
                "class":   class_name,
                "asserts": n_asserts,
                "async":   is_async,
                "marks":   marks,
                "lines":   fn_len,
            }

            # ── T001 no assert ─────────────────────────────────────────────
            if n_asserts == 0:
                report.issues.append(Issue("error", "T001",
                    f"{pfx}{node.name}: no assert statements", rel, node.lineno))
                td["issue_no_assert"] = True

            # ── T002 too many asserts ──────────────────────────────────────
            elif n_asserts > 5:
                report.issues.append(Issue("warning", "T002",
                    f"{pfx}{node.name}: {n_asserts} assertions — split or use parametrize",
                    rel, node.lineno))
                td["issue_many_asserts"] = True

            # ── T003 loop+assert ───────────────────────────────────────────
            if _has_loop_with_assert(node):
                report.issues.append(Issue("warning", "T003",
                    f"{pfx}{node.name}: loop with assert — use @parametrize instead",
                    rel, node.lineno))
                td["issue_loop"] = True

            # ── T004 float == ──────────────────────────────────────────────
            if _float_direct_compare(node):
                report.issues.append(Issue("warning", "T004",
                    f"{pfx}{node.name}: float compared with == — use pytest.approx()",
                    rel, node.lineno))
                td["issue_float"] = True

            # ── T005 hardcoded /tmp ────────────────────────────────────────
            if _has_hardcoded_tmp(node):
                report.issues.append(Issue("warning", "T005",
                    f"{pfx}{node.name}: hardcoded /tmp path — use tmp_path fixture",
                    rel, node.lineno))
                td["issue_hardpath"] = True

            # ── T006 fixture called as function ────────────────────────────
            bad_calls = _calls_fixture(node, set(file_fixtures.keys()))
            if bad_calls:
                report.issues.append(Issue("error", "T006",
                    f"{pfx}{node.name}: fixture(s) called as functions: {bad_calls}",
                    rel, node.lineno))
                td["issue_fixture_call"] = bad_calls

            # ── T007 async no asyncio mark ─────────────────────────────────
            if is_async and not _has_asyncio_mark(node):
                report.issues.append(Issue("info", "T007",
                    f"{pfx}{node.name}: async test without @pytest.mark.asyncio — "
                    "add mark or set asyncio_mode='auto'",
                    rel, node.lineno))
                td["issue_async_mark"] = True

            # ── T008 parametrize no ids ────────────────────────────────────
            if _param_missing_ids(node):
                report.issues.append(Issue("info", "T008",
                    f"{pfx}{node.name}: @parametrize without id= — "
                    "use pytest.param(..., id='name') for readable output",
                    rel, node.lineno))
                td["issue_param_ids"] = True

            # ── T009 single-case parametrize ───────────────────────────────
            if _param_single(node):
                report.issues.append(Issue("info", "T009",
                    f"{pfx}{node.name}: @parametrize with 1 case — "
                    "use a regular test instead",
                    rel, node.lineno))
                td["issue_single_param"] = True

            # ── T010 >20 parametrize cases ─────────────────────────────────
            pc = _param_count(node)
            if pc > 20:
                report.issues.append(Issue("info", "T010",
                    f"{pfx}{node.name}: {pc} parametrize cases — "
                    "consider loading from CSV/JSON",
                    rel, node.lineno))
                td["issue_large_param"] = True

            # ── T011 time.sleep ────────────────────────────────────────────
            if _has_sleep(node):
                report.issues.append(Issue("warning", "T011",
                    f"{pfx}{node.name}: time.sleep() found — mock time instead",
                    rel, node.lineno))
                td["issue_sleep"] = True

            # ── T012 print left in ─────────────────────────────────────────
            if _has_print(node):
                report.issues.append(Issue("info", "T012",
                    f"{pfx}{node.name}: print() found — debugging code?",
                    rel, node.lineno))
                td["issue_print"] = True

            # ── T013 bare except ───────────────────────────────────────────
            if _has_bare_except(node):
                report.issues.append(Issue("warning", "T013",
                    f"{pfx}{node.name}: bare except / except Exception: pass — "
                    "swallows failures silently",
                    rel, node.lineno))
                td["issue_bare_except"] = True

            # ── T014 skip no reason ────────────────────────────────────────
            if _skip_no_reason(node):
                report.issues.append(Issue("warning", "T014",
                    f"{pfx}{node.name}: @skip without reason= — document why",
                    rel, node.lineno))
                td["issue_skip_no_reason"] = True

            # ── T015 xfail no reason ───────────────────────────────────────
            if _xfail_no_reason(node):
                report.issues.append(Issue("warning", "T015",
                    f"{pfx}{node.name}: @xfail without reason= — document why",
                    rel, node.lineno))
                td["issue_xfail_no_reason"] = True

            # ── T017 function longer than 30 lines ─────────────────────────
            if fn_len > 30:
                report.issues.append(Issue("info", "T017",
                    f"{pfx}{node.name}: test body is {fn_len} statements — "
                    "consider splitting into smaller focused tests",
                    rel, node.lineno))
                td["issue_long_test"] = True

            # ── T018 multiple pytest.raises ────────────────────────────────
            n_raises = _multi_raises(node)
            if n_raises > 1:
                report.issues.append(Issue("info", "T018",
                    f"{pfx}{node.name}: {n_raises} pytest.raises blocks — "
                    "each should be its own test",
                    rel, node.lineno))
                td["issue_multi_raises"] = True

            # ── T019 assert True literal ───────────────────────────────────
            if _has_assert_true_literal(node):
                report.issues.append(Issue("warning", "T019",
                    f"{pfx}{node.name}: assert True / assert 1==1 — "
                    "placeholder assertion that proves nothing",
                    rel, node.lineno))
                td["issue_assert_true"] = True

            # ── T020 bare truthy assert ────────────────────────────────────
            if _has_assert_result_bare(node):
                report.issues.append(Issue("info", "T020",
                    f"{pfx}{node.name}: 'assert result' (bare name) — "
                    "use assert result == expected_value",
                    rel, node.lineno))
                td["issue_bare_assert"] = True

            # ── T021 assert len > 0 ────────────────────────────────────────
            if _has_assert_len_gt_zero(node):
                report.issues.append(Issue("info", "T021",
                    f"{pfx}{node.name}: assert len(x) > 0 — "
                    "use assert x or assert x == [expected]",
                    rel, node.lineno))
                td["issue_len_gt_zero"] = True

            # ── T022 asyncio.sleep(0) ──────────────────────────────────────
            if _has_asyncio_sleep_zero(node):
                report.issues.append(Issue("info", "T022",
                    f"{pfx}{node.name}: asyncio.sleep(0) — "
                    "usually unnecessary in tests",
                    rel, node.lineno))
                td["issue_sleep_zero"] = True

            # ── T023 asyncio.run() inside test ─────────────────────────────
            if _has_asyncio_run(node):
                report.issues.append(Issue("warning", "T023",
                    f"{pfx}{node.name}: asyncio.run() inside test — "
                    "use async def test + asyncio_mode='auto' instead",
                    rel, node.lineno))
                td["issue_asyncio_run"] = True

            # ── SA01 write to real path ────────────────────────────────────
            if _has_write_to_real_path(node):
                report.issues.append(Issue("warning", "SA01",
                    f"{pfx}{node.name}: open(..., 'w') with non-tmp path — "
                    "use tmp_path to avoid leaving files behind",
                    rel, node.lineno))
                td["issue_write_path"] = True

            # ── SA02 os.environ direct modification ────────────────────────
            if _modifies_environ_directly(node):
                report.issues.append(Issue("warning", "SA02",
                    f"{pfx}{node.name}: os.environ modified directly — "
                    "use monkeypatch.setenv() so it's reverted after the test",
                    rel, node.lineno))
                td["issue_environ"] = True

            # ── M001 unregistered mark ─────────────────────────────────────
            for mark in marks:
                if mark not in BUILTIN_MARKS and mark not in registered_marks:
                    report.issues.append(Issue("warning", "M001",
                        f"{pfx}{node.name}: unregistered mark '@pytest.mark.{mark}' — "
                        "add to markers in pyproject.toml",
                        rel, node.lineno))
                    td.setdefault("issue_unregistered_marks", []).append(mark)

            # ── MK01 mock set up, never asserted ──────────────────────────
            if _patches_mock(node) and not _has_assert_called(node) and n_asserts > 0:
                report.issues.append(Issue("info", "MK01",
                    f"{pfx}{node.name}: mock patched but no assert_called* — "
                    "the patch may never be verified",
                    rel, node.lineno))
                td["issue_mock_unasserted"] = True

            # ── MK02 unittest.mock.patch directly ─────────────────────────
            if _uses_unittest_patch(node):
                report.issues.append(Issue("info", "MK02",
                    f"{pfx}{node.name}: uses unittest.mock.patch directly — "
                    "prefer mocker.patch",
                    rel, node.lineno))
                td["issue_unittest_patch"] = True

            # ── MK03 mock.ANY overused ─────────────────────────────────────
            if _mock_any_overused(node):
                report.issues.append(Issue("info", "MK03",
                    f"{pfx}{node.name}: mock.ANY used 3+ times — "
                    "assertions are too permissive",
                    rel, node.lineno))
                td["issue_mock_any"] = True

            # ── MK06 suspicious patch target (too short) ───────────────────
            targets = _patch_targets(node)
            for t in targets:
                if t and "." not in t:
                    report.issues.append(Issue("warning", "MK06",
                        f"{pfx}{node.name}: patch target '{t}' has no module path — "
                        "use 'myapp.module.name' not just 'name'",
                        rel, node.lineno))
                    td["issue_patch_path"] = True
                    break

            # ── MK07 same target patched twice ─────────────────────────────
            if len(targets) != len(set(targets)) and targets:
                dupes = [t for t in set(targets) if targets.count(t) > 1]
                report.issues.append(Issue("info", "MK07",
                    f"{pfx}{node.name}: same mock target patched more than once: "
                    f"{dupes} — likely copy-paste error",
                    rel, node.lineno))
                td["issue_dup_patch"] = True

            # ── parametrize id special chars ───────────────────────────────
            if _param_ids_with_special_chars(node):
                report.issues.append(Issue("info", "T024",
                    f"{pfx}{node.name}: parametrize id contains spaces or brackets — "
                    "makes -k filtering awkward; use hyphens or underscores",
                    rel, node.lineno))
                td["issue_param_id_chars"] = True

            # ── N006 vague name ────────────────────────────────────────────
            if VAGUE_NAMES.match(node.name):
                report.issues.append(Issue("warning", "N006",
                    f"{pfx}{node.name}: vague test name — "
                    "use test_login_fails_if_password_wrong style",
                    rel, node.lineno))
                td["issue_vague_name"] = True

            # ── N007 numbered name ─────────────────────────────────────────
            if NUMBERED_NAMES.match(node.name):
                report.issues.append(Issue("info", "N007",
                    f"{pfx}{node.name}: numbered test name — "
                    "use descriptive names",
                    rel, node.lineno))
                td["issue_numbered_name"] = True

            report.tests.append(td)

    walk_tests(tree.body)

    # ── T016 duplicate test names ──────────────────────────────────────────
    for name, lines in test_names_seen.items():
        if len(lines) > 1:
            report.issues.append(Issue("warning", "T016",
                f"Duplicate test name '{name}' at lines {lines} — "
                "silent collection conflict",
                rel, lines[0]))

    # ── S003 empty test file ───────────────────────────────────────────────
    if report.test_count == 0 and report.fixture_count == 0:
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            report.issues.append(Issue("info", "S003",
                f"'{path.name}' is a test file with no tests or fixtures", rel))

    # ── FX09 fixture used only once ────────────────────────────────────────
    for fname, fnode in file_fixtures.items():
        if fixture_usage_count[fname] == 1 and not fixture_meta[fname]["autouse"]:
            report.issues.append(Issue("info", "FX09",
                f"Fixture '{fname}' is used by only 1 test — "
                "consider inlining the setup directly",
                rel, fixture_meta[fname]["line"]))

    return report


# ── conftest fixture collector ────────────────────────────────────────────────

def collect_conftest_fixtures(conftest_path: Path) -> dict[str, str]:
    """Parse a conftest.py and return {fixture_name: scope}."""
    result: dict[str, str] = {}
    try:
        tree = ast.parse(conftest_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if _is_fixture(node):
                result[node.name] = _fixture_scope(node)
    except Exception:
        pass
    return result


# ── config reader ─────────────────────────────────────────────────────────────

def read_config(root: Path) -> tuple[list[str], list[str]]:
    marks: list[str] = []
    paths: list[str] = []
    for candidate in (root / "pyproject.toml", root.parent / "pyproject.toml"):
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            m = re.search(r'markers\s*=\s*\[(.*?)\]', text, re.DOTALL)
            if m:
                marks = re.findall(r'["\'](\w+)["\']', m.group(1))
            m2 = re.search(r'testpaths\s*=\s*\[(.*?)\]', text, re.DOTALL)
            if m2:
                paths = re.findall(r'["\']([^"\']+)["\']', m2.group(1))
            break
    for candidate in (root / "pytest.ini", root.parent / "pytest.ini"):
        if candidate.exists() and not marks:
            text = candidate.read_text(encoding="utf-8")
            sec = re.search(r'\[pytest\](.*?)(?:\[|$)', text, re.DOTALL)
            if sec:
                marks.extend(re.findall(r'^\s+(\w+):', sec.group(1), re.MULTILINE))
            break
    return marks, paths


# ── coverage reader ───────────────────────────────────────────────────────────

def read_coverage(root: Path) -> tuple[float | None, list[str]]:
    for p in (root / "coverage.json", root.parent / "coverage.json"):
        if p.exists():
            try:
                data = json.loads(p.read_text())
                pct  = data.get("totals", {}).get("percent_covered")
                missing = [
                    f"{fn}: lines {','.join(str(l) for l in fd.get('missing_lines', [])[:5])}"
                    for fn, fd in data.get("files", {}).items()
                    if fd.get("missing_lines")
                ][:10]
                return pct, missing
            except Exception:
                pass
    return None, []


# ── suite scanner ─────────────────────────────────────────────────────────────

def scan(root: Path) -> SuiteReport:
    import datetime
    root = root.resolve()
    config_root = root.parent if root.name == "tests" else root
    registered_marks, _ = read_config(config_root)
    mark_set = set(registered_marks)

    cov_pct, cov_missing = read_coverage(config_root)

    report = SuiteReport(
        root             = str(root),
        generated_at     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        registered_marks = registered_marks,
        coverage_pct     = cov_pct,
        coverage_missing = cov_missing,
    )

    # ── conftest.py hierarchy ──────────────────────────────────────────────
    conftest_files = sorted(root.rglob("conftest.py"))
    report.conftest_paths = [str(p) for p in conftest_files]

    # collect all fixtures defined in conftest files
    conftest_fixtures: dict[str, str] = {}
    conftest_fixture_sources: dict[str, list[str]] = defaultdict(list)
    for cf in conftest_files:
        fxs = collect_conftest_fixtures(cf)
        for name, scope in fxs.items():
            conftest_fixture_sources[name].append(str(cf))
            conftest_fixtures[name] = scope

    # ── OR08 duplicate fixture across conftest files ────────────────────────
    for fname, sources in conftest_fixture_sources.items():
        if len(sources) > 1:
            stub = FileReport(path=str(root))
            stub.issues.append(Issue("warning", "OR08",
                f"Fixture '{fname}' defined in multiple conftest.py files: "
                f"{[str(Path(s).relative_to(root)) for s in sources]} — "
                "inner definition silently shadows outer",
                str(root)))
            report.files.append(stub)

    if not (root / "conftest.py").exists():
        stub = FileReport(path=str(root / "conftest.py"))
        stub.issues.append(Issue("info", "S001",
            f"No conftest.py in {root}", str(root)))
        report.files.append(stub)

    # ── collect test files ─────────────────────────────────────────────────
    seen: set[Path] = set()
    test_files: list[Path] = []
    for pat in ("test_*.py", "*_test.py"):
        for f in sorted(root.rglob(pat)):
            if f not in seen:
                seen.add(f)
                test_files.append(f)

    src_root = config_root / "src" if (config_root / "src").exists() else None

    for tf in test_files:
        report.files.append(analyse_file(tf, mark_set, conftest_fixtures, src_root))

    # ── OR11 no __init__.py but cross-imports ──────────────────────────────
    has_init = any([(root / "__init__.py").exists(), (root / "tests/__init__.py").exists()])
    if not has_init and test_files:
        stub = FileReport(path=str(root))
        stub.issues.append(Issue("info", "OR11",
            "No __init__.py in tests directory — "
            "imports between test files may fail on some configurations; "
            "add __init__.py or use importmode=importlib",
            str(root)))
        report.files.append(stub)

    # ── S004 no marks anywhere ─────────────────────────────────────────────
    all_marks = [m for f in report.files for t in f.tests for m in t.get("marks", [])]
    if test_files and not all_marks:
        stub = FileReport(path=str(root))
        stub.issues.append(Issue("info", "S004",
            "No tests have any marks — consider tagging slow/integration/smoke tests",
            str(root)))
        report.files.append(stub)

    # ── OR12 deeply nested test directories (>3 levels) ────────────────────
    for tf in test_files:
        depth = len(tf.relative_to(root).parts)
        if depth > 4:
            stub = FileReport(path=str(tf))
            stub.issues.append(Issue("info", "OR12",
                f"'{tf.relative_to(root)}' is {depth} levels deep — "
                "deeply nested test directories are hard to navigate",
                str(tf)))
            report.files.append(stub)
            break  # one note is enough

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

    # ── test debt metric ───────────────────────────────────────────────────
    all_tests = [t for f in report.files for t in f.tests]
    skip_tests  = sum(1 for t in all_tests if "skip" in t.get("marks", [])
                      or "skipif" in t.get("marks", []))
    xfail_tests = sum(1 for t in all_tests if "xfail" in t.get("marks", []))
    report.skip_count  = skip_tests
    report.xfail_count = xfail_tests
    if report.total_tests:
        report.test_debt_pct = round((skip_tests + xfail_tests) / report.total_tests * 100, 1)

    # ── isolation score ────────────────────────────────────────────────────
    # % of test functions whose fixtures are all function-scoped
    fn_scoped_tests = 0
    for t in all_tests:
        args = []  # we'd need to track args, approximate via fixture count
        fn_scoped_tests += 1  # simplified: count fixture usage at function scope
    # simplified isolation: ratio of function-scoped to all fixtures
    all_fx = [fx for f in report.files for fx in f.fixtures]
    if all_fx:
        fn_scope = sum(1 for fx in all_fx if fx.get("scope") == "function")
        report.isolation_score = round(fn_scope / len(all_fx) * 100, 1)

    # ── per-directory breakdown ────────────────────────────────────────────
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
