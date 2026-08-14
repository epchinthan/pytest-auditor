"""
checks.py
─────────
Check functions that inspect AST nodes and emit Issues.
Each function receives context (node, path, marks, etc.) and returns
a list[Issue] — zero or more. No global state, no printing.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from core import ast_helpers as h
from core.models import (
    BUILTIN_MARKS,
    CREDENTIAL_PATTERN,
    ERROR,
    INFO,
    NUMBERED_NAMES,
    PYTHON_BUILTINS,
    SCOPE_ORDER,
    VAGUE_NAMES,
    WARNING,
    Issue,
)

# ── file-level checks ─────────────────────────────────────────────────────────

def check_file_naming(path: Path) -> list[Issue]:
    if not (path.name.startswith("test_") or path.name.endswith("_test.py")):
        return [Issue(WARNING, "N001",
            f"'{path.name}' doesn't follow naming convention (test_*.py or *_test.py)",
            str(path))]
    return []


def check_file_length(path: Path, line_count: int) -> list[Issue]:
    if line_count > 200:
        return [Issue(INFO, "S002",
            f"File is {line_count} lines — consider splitting into multiple modules",
            str(path))]
    return []


SAFE_TEST_VALUES = re.compile(
    r"""["'](wrong|bad|invalid|fake|dummy|test|example|placeholder|
    secret|changeme|none|empty|xxx|123|password|admin|user|guest)["']\s*$""",
)

def check_credentials(source: str, path: Path) -> list[Issue]:
    """Flag hardcoded credentials, but ignore obvious test placeholder values."""
    issues = []
    for m in CREDENTIAL_PATTERN.finditer(source):
        # skip obvious test placeholder values
        value_part = m.group(0).split("=", 1)[1].strip()
        if SAFE_TEST_VALUES.match(value_part):
            continue
        ln = source[: m.start()].count("\n") + 1
        issues.append(Issue(WARNING, "F003",
            f"Possible hardcoded credential: {m.group(0)[:50]}",
            str(path), ln))
    return issues


def check_unittest_mock_import(tree: ast.AST, path: Path) -> list[Issue]:
    if h.uses_unittest_mock_import(tree):
        return [Issue(INFO, "MK04",
            "Direct unittest.mock import — prefer mocker fixture (pytest-mock)",
            str(path))]
    return []


def check_module_level_mock(tree: ast.AST, path: Path) -> list[Issue]:
    if h.module_level_mock(tree):
        return [Issue(WARNING, "MK05",
            "MagicMock()/Mock() at module level — shared between all tests",
            str(path))]
    return []



def check_empty_file(path: Path, test_count: int, fixture_count: int) -> list[Issue]:
    if (
        test_count == 0
        and fixture_count == 0
        and (path.name.startswith("test_") or path.name.endswith("_test.py"))
    ):
        return [Issue(INFO, "S003",
            f"'{path.name}' is a test file with no tests or fixtures",
            str(path))]
    return []


# ── fixture checks ────────────────────────────────────────────────────────────

def check_fixture(node: ast.AST, path: Path) -> list[Issue]:
    """All checks that apply to a single fixture node."""
    issues = []
    rel      = str(path)
    name     = node.name
    scope    = h.fixture_scope(node)
    autouse  = h.fixture_autouse(node)
    body_len = len(node.body)

    if h.has_unreachable_teardown(node):
        issues.append(Issue(WARNING, "FX01",
            f"Fixture '{name}' has statements after a top-level return — "
            "those lines are unreachable; use yield instead so teardown runs",
            rel, node.lineno))

    # Only flag assert in fixture when it also yields — meaning it's a setup
    # fixture, not a standalone validation helper. A plain fixture that just
    # asserts a precondition and returns is a legitimate pattern.
    if h.has_assert_in_body(node) and h.uses_yield(node):
        issues.append(Issue(WARNING, "FX02",
            f"Fixture '{name}' contains assert before yield — "
            "assertion failures show as ERROR not FAILED; "
            "raise explicitly instead",
            rel, node.lineno))

    if body_len > 30:
        issues.append(Issue(INFO, "FX03",
            f"Fixture '{name}' is {body_len} lines — consider splitting",
            rel, node.lineno))

    if autouse and scope == "session":
        issues.append(Issue(WARNING, "FX04",
            f"Fixture '{name}': autouse=True + session scope affects every test in the run",
            rel, node.lineno))

    if h.yield_count(node) > 1:
        issues.append(Issue(WARNING, "FX06",
            f"Fixture '{name}' yields {h.yield_count(node)} times — only first yield is used",
            rel, node.lineno))

    defaults = h.fixture_default_args(node)
    if defaults:
        issues.append(Issue(WARNING, "FX09",
            f"Fixture '{name}' has default value(s) for {defaults} — "
            "pytest resolves fixture parameters by name, not by defaults",
            rel, node.lineno))

    if h.yield_without_teardown(node):
        issues.append(Issue(INFO, "FX10",
            f"Fixture '{name}' ends with yield but has no teardown — return the value instead",
            rel, node.lineno))

    if h.fixture_depends_on_itself(node):
        issues.append(Issue(INFO, "FX12",
            f"Fixture '{name}' requests a fixture with the same name — "
            "verify this is an intentional parent-fixture override",
            rel, node.lineno))

    PYTEST_FIXTURE_PARAMS = {'request', 'tmp_path', 'capsys', 'capfd', 'monkeypatch', 'caplog', 'pytestconfig'}
    for arg in node.args.args:
        if arg.arg in PYTHON_BUILTINS and arg.arg not in PYTEST_FIXTURE_PARAMS:
            issues.append(Issue(INFO, "FX07",
                f"Fixture '{name}': parameter '{arg.arg}' shadows a Python builtin",
                rel, node.lineno))

    return issues


def check_fixture_scope_compat(
    caller_name: str,
    caller_scope: str,
    callee_name: str,
    callee_scope: str,
    path: Path,
    lineno: int,
) -> list[Issue]:
    if SCOPE_ORDER.get(caller_scope, 0) > SCOPE_ORDER.get(callee_scope, 0):
        return [Issue(ERROR, "FX05",
            f"Scope mismatch: '{caller_name}' ({caller_scope}) depends on "
            f"'{callee_name}' ({callee_scope}) — outer scope must be ≥ inner",
            str(path), lineno)]
    return []


def check_fixture_shadow(name: str, conftest_fixtures: dict, path: Path, lineno: int) -> list[Issue]:
    if name in conftest_fixtures:
        return [Issue(INFO, "FX08",
            f"Fixture '{name}' shadows a fixture of the same name in conftest.py "
            f"(scope: {conftest_fixtures[name]}) — may be intentional or accidental",
            str(path), lineno)]
    return []




# ── test-level checks ─────────────────────────────────────────────────────────

def check_test(
    node: ast.AST,
    path: Path,
    class_name: str | None,
    known_fixture_names: set[str],
    registered_marks: set[str],
    tree: ast.AST | None = None,
) -> list[Issue]:
    """All checks that apply to a single test function. Returns list of Issues."""
    issues  = []
    rel     = str(path)
    pfx     = f"[{class_name}] " if class_name else ""
    name    = node.name
    n_ass   = h.assert_count(node)
    marks   = h.get_marks(node)
    fn_len  = len(node.body)
    is_async = h.is_async(node)

    # ── assertions ─────────────────────────────────────────────────────────
    if n_ass == 0 and not h.has_pytest_raises(node) and not h.has_non_assert_verification(node):
        issues.append(Issue(ERROR, "T001",
            f"{pfx}{name}: no assert statements — test proves nothing",
            rel, node.lineno))

    elif n_ass > 5:
        issues.append(Issue(WARNING, "T002",
            f"{pfx}{name}: {n_ass} assertions — consider splitting or parametrize",
            rel, node.lineno))

    if h.has_assert_true_literal(node) and not h.has_pytest_raises(node):
        issues.append(Issue(WARNING, "T019",
            f"{pfx}{name}: assert True / assert 1==1 — placeholder that proves nothing",
            rel, node.lineno))

    if h.has_assert_result_bare(node):
        issues.append(Issue(INFO, "T020",
            f"{pfx}{name}: 'assert result' (bare name) — use assert result == expected",
            rel, node.lineno))

    if h.has_assert_len_gt_zero(node):
        issues.append(Issue(INFO, "T021",
            f"{pfx}{name}: assert len(x) > 0 — use assert x or assert x == [expected]",
            rel, node.lineno))

    if h.float_direct_compare(node):
        issues.append(Issue(WARNING, "T004",
            f"{pfx}{name}: float compared with == — use pytest.approx()",
            rel, node.lineno))

    n_raises = h.multi_raises(node)
    if n_raises > 1:
        issues.append(Issue(INFO, "T018",
            f"{pfx}{name}: {n_raises} pytest.raises blocks — each should be its own test",
            rel, node.lineno))

    # ── structure ──────────────────────────────────────────────────────────
    if h.has_loop_with_assert(node):
        issues.append(Issue(WARNING, "T003",
            f"{pfx}{name}: loop with assert — use @parametrize instead",
            rel, node.lineno))

    if fn_len > 30:
        issues.append(Issue(INFO, "T017",
            f"{pfx}{name}: test body is {fn_len} lines — consider splitting",
            rel, node.lineno))

    # ── fixtures ───────────────────────────────────────────────────────────
    bad_calls = h.calls_fixture(node, known_fixture_names)
    if bad_calls:
        issues.append(Issue(ERROR, "T006",
            f"{pfx}{name}: fixture(s) called as functions: {bad_calls}",
            rel, node.lineno))

    # ── paths / environment ────────────────────────────────────────────────
    if h.has_hardcoded_tmp(node):
        issues.append(Issue(WARNING, "T005",
            f"{pfx}{name}: hardcoded /tmp path — use tmp_path fixture",
            rel, node.lineno))

    if h.has_write_to_real_path(node):
        issues.append(Issue(WARNING, "SA01",
            f"{pfx}{name}: open(..., 'w') with non-tmp path — use tmp_path",
            rel, node.lineno))

    if h.modifies_environ_directly(node):
        issues.append(Issue(WARNING, "SA02",
            f"{pfx}{name}: os.environ modified directly — use monkeypatch.setenv()",
            rel, node.lineno))

    for line in h.direct_chdir(node):
        issues.append(Issue(WARNING, "SA03",
            f"{pfx}{name}: os.chdir() changes process-wide cwd — use monkeypatch.chdir()",
            rel, line))

    for line in h.direct_sys_path_mutation(node):
        issues.append(Issue(WARNING, "SA04",
            f"{pfx}{name}: sys.path modified directly — use monkeypatch.syspath_prepend()",
            rel, line))

    # ── async ──────────────────────────────────────────────────────────────
    if is_async and not h.has_asyncio_mark(node) and not h.asyncio_mode_is_auto(tree):
        issues.append(Issue(INFO, "T007",
            f"{pfx}{name}: async test without @pytest.mark.asyncio — "
            "add mark or set asyncio_mode=\'auto\' in pyproject.toml",
            rel, node.lineno))

    if h.has_asyncio_sleep_zero(node):
        issues.append(Issue(INFO, "T022",
            f"{pfx}{name}: asyncio.sleep(0) — usually unnecessary in tests",
            rel, node.lineno))

    if h.has_asyncio_run(node):
        issues.append(Issue(WARNING, "T023",
            f"{pfx}{name}: asyncio.run() inside test — use async def + asyncio_mode='auto'",
            rel, node.lineno))

    for line, exception in h.broad_raises(node):
        issues.append(Issue(WARNING, "T025",
            f"{pfx}{name}: pytest.raises({exception}) is too broad — expect a specific exception",
            rel, line))

    for line in h.raises_with_multiple_statements(node):
        issues.append(Issue(WARNING, "T026",
            f"{pfx}{name}: pytest.raises block has multiple statements — "
            "only the operation expected to raise should be inside",
            rel, line))

    for line in h.warns_without_match(node):
        issues.append(Issue(INFO, "T027",
            f"{pfx}{name}: pytest.warns() has no match= — it may accept an unrelated warning",
            rel, line))

    duplicate_cases = h.duplicate_parametrize_cases(node)
    if duplicate_cases:
        issues.append(Issue(WARNING, "T028",
            f"{pfx}{name}: duplicate parametrize case(s) at zero-based indexes {duplicate_cases}",
            rel, node.lineno))

    if h.has_assert_false_literal(node):
        issues.append(Issue(WARNING, "T029",
            f"{pfx}{name}: assertion always fails — use pytest.fail('reason')",
            rel, node.lineno))

    for line in h.pytest_fail_without_message(node):
        issues.append(Issue(INFO, "T030",
            f"{pfx}{name}: pytest.fail() has no message explaining the failure",
            rel, line))

    if h.has_assert_in_except(node):
        issues.append(Issue(WARNING, "T031",
            f"{pfx}{name}: assertion inside except block — prefer pytest.raises()",
            rel, node.lineno))

    for line, call in h.debugger_calls(node):
        issues.append(Issue(WARNING, "T032",
            f"{pfx}{name}: debugger call '{call}()' left in test",
            rel, line))

    # ── print / except ────────────────────────────────────────────────

    if h.has_print(node):
        issues.append(Issue(INFO, "T012",
            f"{pfx}{name}: print() found — debugging code?",
            rel, node.lineno))

    if h.has_bare_except(node):
        issues.append(Issue(WARNING, "T013",
            f"{pfx}{name}: bare except swallows failures silently",
            rel, node.lineno))

    # ── marks ──────────────────────────────────────────────────────────────
    if h.skip_no_reason(node):
        issues.append(Issue(WARNING, "T014",
            f"{pfx}{name}: @skip without reason= — document why",
            rel, node.lineno))

    if h.xfail_no_reason(node):
        issues.append(Issue(WARNING, "T015",
            f"{pfx}{name}: @xfail without reason= — document why",
            rel, node.lineno))

    for mark in marks:
        if mark not in BUILTIN_MARKS and mark not in registered_marks:
            issues.append(Issue(WARNING, "M001",
                f"{pfx}{name}: unregistered mark '@pytest.mark.{mark}'",
                rel, node.lineno))

    # ── parametrize ────────────────────────────────────────────────────────
    if h.param_missing_ids(node):
        issues.append(Issue(INFO, "T008",
            f"{pfx}{name}: @parametrize without id= — use pytest.param(..., id='name')",
            rel, node.lineno))

    if h.param_single(node) and not h.param_has_marks_only(node):
        issues.append(Issue(INFO, "T009",
            f"{pfx}{name}: @parametrize with 1 case — use a regular test instead",
            rel, node.lineno))

    pc = h.param_count(node)
    if pc > 20:
        issues.append(Issue(INFO, "T010",
            f"{pfx}{name}: {pc} parametrize cases — consider loading from CSV/JSON",
            rel, node.lineno))

    if h.param_ids_with_special_chars(node):
        issues.append(Issue(INFO, "T024",
            f"{pfx}{name}: parametrize id with spaces/brackets — makes -k filtering awkward",
            rel, node.lineno))

    missing_params, duplicate_params, bad_rows = h.parametrize_problems(node)
    if missing_params:
        issues.append(Issue(ERROR, "T037",
            f"{pfx}{name}: parametrized name(s) absent from test signature: "
            f"{sorted(missing_params)}",
            rel, node.lineno))
    if duplicate_params:
        issues.append(Issue(ERROR, "T038",
            f"{pfx}{name}: duplicate parametrize argument name(s): {sorted(duplicate_params)}",
            rel, node.lineno))
    if bad_rows:
        issues.append(Issue(ERROR, "T039",
            f"{pfx}{name}: parametrize row(s) have the wrong number of values at "
            f"zero-based indexes {bad_rows}",
            rel, node.lineno))

    # ── naming ─────────────────────────────────────────────────────────────
    if VAGUE_NAMES.match(name):
        issues.append(Issue(WARNING, "N006",
            f"{pfx}{name}: vague test name — use test_login_fails_if_password_wrong style",
            rel, node.lineno))

    # Only flag purely numeric endings like test_thing_1, test_1
    # Don't flag names like test_retry_3_times where the number is semantic
    if NUMBERED_NAMES.match(name) and re.search(r"_\d+$", name):
        issues.append(Issue(INFO, "N007",
            f"{pfx}{name}: test name ends with a number — use descriptive names",
            rel, node.lineno))

    # ── mocking ────────────────────────────────────────────────────────────
    if h.patches_mock(node) and not h.has_assert_called(node) and n_ass > 0:
        issues.append(Issue(INFO, "MK01",
            f"{pfx}{name}: mock patched but no assert_called* — patch may never be verified",
            rel, node.lineno))

    if h.uses_unittest_patch(node):
        issues.append(Issue(INFO, "MK02",
            f"{pfx}{name}: uses unittest.mock.patch — prefer mocker.patch",
            rel, node.lineno))

    if h.mock_any_overused(node):
        issues.append(Issue(INFO, "MK03",
            f"{pfx}{name}: mock.ANY used 3+ times — assertions too permissive",
            rel, node.lineno))

    targets = h.patch_targets(node)
    bad_targets = [
        t for t in targets
        if t and "." not in t and not h.is_builtin_patch_target(t)
    ]
    if bad_targets:
        issues.append(Issue(WARNING, "MK06",
            f"{pfx}{name}: patch target {bad_targets} has no module path — "
            "use \'myapp.module.name\'",
            rel, node.lineno))

    if len(targets) != len(set(targets)) and targets:
        dupes = [t for t in set(targets) if targets.count(t) > 1]
        issues.append(Issue(INFO, "MK07",
            f"{pfx}{name}: same mock target patched more than once: {dupes}",
            rel, node.lineno))

    return issues


def check_registered_marks(
    marks: list[str], registered_marks: set[str], path: Path, lineno: int, owner: str,
) -> list[Issue]:
    return [
        Issue(WARNING, "M002" if owner.startswith("class ") else "M003",
              f"Unregistered mark '@pytest.mark.{mark}' on {owner}", str(path), lineno)
        for mark in marks
        if mark not in BUILTIN_MARKS and mark not in registered_marks
    ]


# ── class-level checks ────────────────────────────────────────────────────────

def check_class(node: ast.ClassDef, path: Path) -> list[Issue]:
    issues = []
    rel = str(path)

    if h.is_unittest_class(node):
        issues.append(Issue(WARNING, "N004",
            f"'{node.name}' inherits from TestCase — pytest fixtures won't inject",
            rel, node.lineno))

    test_methods = [n for n in node.body if h.is_test_func(n)]
    has_setup = any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name in ("setup_method", "teardown_method", "setup_class",
                        "teardown_class", "setup", "teardown")
        for n in node.body
    )
    has_fixtures = any(h.is_fixture(n) for n in node.body)
    if not test_methods and not has_setup and not has_fixtures:
        issues.append(Issue(INFO, "N005",
            f"Class '{node.name}' has no test methods",
            rel, node.lineno))

    return issues


def check_non_test_class(node: ast.ClassDef, path: Path) -> list[Issue]:
    if any(h.is_test_func(n) for n in ast.walk(node)):
        return [Issue(WARNING, "N003",
            f"Class '{node.name}' doesn't start with Test — its tests won't be collected",
            str(path), node.lineno)]
    return []


def check_check_prefix(node: ast.AST, path: Path, tree: ast.AST) -> list[Issue]:
    """
    Flag check_/verify_ functions only when they look like forgotten tests —
    i.e. they are never called anywhere in the file.
    If the function is called by other tests or helpers it's a legitimate
    shared assertion helper and should be left alone.
    """
    if not node.name.startswith(("check_", "verify_")):
        return []
    if h.is_called_in_tree(node.name, tree):
        return []   # it's a helper — called by something, intentional
    return [Issue(WARNING, "N002",
        f"'{node.name}' starts with check_/verify_ and is never called — "
        "pytest won't collect it; rename to test_ or call it from a test",
        str(path), node.lineno)]


# ── duplicate name check ──────────────────────────────────────────────────────

def check_duplicate_names(name_lines: dict[str, list[int]], path: Path) -> list[Issue]:
    issues = []
    for name, lines in name_lines.items():
        if len(lines) > 1:
            issues.append(Issue(WARNING, "T016",
                f"Duplicate test name '{name}' at lines {lines} — silent collection conflict",
                str(path), lines[0]))
    return issues