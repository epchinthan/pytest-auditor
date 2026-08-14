"""
ast_helpers.py
──────────────
Pure AST inspection helpers. Each function takes an AST node and returns
a bool, string, or list. No side effects, no issue creation — just queries.
"""
from __future__ import annotations

import ast
import re

# ── basic node classification ─────────────────────────────────────────────────

def unparse(node: ast.AST) -> str:
    return ast.unparse(node)

def is_func(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))

def is_test_func(node: ast.AST) -> bool:
    return is_func(node) and node.name.startswith("test_")

def is_test_class(node: ast.AST) -> bool:
    return isinstance(node, ast.ClassDef) and node.name.startswith("Test")

def is_async(node: ast.AST) -> bool:
    return isinstance(node, ast.AsyncFunctionDef)

def is_unittest_class(node: ast.AST) -> bool:
    return isinstance(node, ast.ClassDef) and any(
        "TestCase" in unparse(b) for b in node.bases
    )


# ── fixture detection ─────────────────────────────────────────────────────────

def is_fixture(node: ast.AST) -> bool:
    if not is_func(node):
        return False
    return any(
        "pytest.fixture" in unparse(d) or unparse(d).strip() == "fixture"
        for d in node.decorator_list
    )

def fixture_scope(node: ast.AST) -> str:
    for d in node.decorator_list:
        src = unparse(d)
        if "pytest.fixture" in src:
            m = re.search(r'scope=["\'](\w+)["\']', src)
            return m.group(1) if m else "function"
    return "function"

def fixture_autouse(node: ast.AST) -> bool:
    return any(
        "autouse" in unparse(d) and "True" in unparse(d)
        for d in node.decorator_list
    )

def uses_yield(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Yield) for n in ast.walk(node))


def has_unreachable_teardown(node: ast.AST) -> bool:
    """
    True only when a fixture has statements after a top-level return —
    meaning there is teardown code that will never execute.

    These are both fine — early/conditional returns with no orphaned code:
        if condition: return value   ← return inside an if, nothing after
        conn = setup(); return conn  ← return is the final statement

    This is the problem:
        conn = setup()
        return conn
        conn.close()    ← unreachable teardown; should be yield + close
    """
    body = node.body
    for i, stmt in enumerate(body):
        # Top-level return that is not the last statement
        if isinstance(stmt, ast.Return) and i < len(body) - 1:
            return True
    return False

def yield_count(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.Yield))

def has_assert_in_body(node: ast.AST) -> bool:
    """Direct assert in fixture body (not inside a nested function)."""
    for stmt in node.body:
        if any(isinstance(n, ast.Assert) for n in ast.walk(stmt)):
            return True
    return False


# ── mark helpers ──────────────────────────────────────────────────────────────

def get_marks(node: ast.AST) -> list[str]:
    marks = []
    for d in node.decorator_list:
        marks.extend(re.findall(r"pytest\.mark\.(\w+)", unparse(d)))
    return marks


def get_module_marks(tree: ast.AST) -> list[str]:
    """
    Collect marks from module-level pytestmark assignments.
    Handles all common forms:

        pytestmark = pytest.mark.slow
        pytestmark = pytest.mark.slow()
        pytestmark = [pytest.mark.slow, pytest.mark.integration]
    """
    marks = []
    for node in ast.iter_child_nodes(tree):
        # simple assignment: pytestmark = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    marks.extend(re.findall(r"pytest\.mark\.(\w+)", unparse(node.value)))
        # annotated assignment: pytestmark: list = ...
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "pytestmark"
            and node.value
        ):
            marks.extend(re.findall(r"pytest\.mark\.(\w+)", unparse(node.value)))
    return marks

def has_asyncio_mark(node: ast.AST) -> bool:
    return any("asyncio" in unparse(d) or "anyio" in unparse(d)
               for d in node.decorator_list)

def skip_no_reason(node: ast.AST) -> bool:
    return any(
        "mark.skip" in unparse(d) and "reason" not in unparse(d)
        for d in node.decorator_list
    )

def xfail_no_reason(node: ast.AST) -> bool:
    return any(
        "mark.xfail" in unparse(d) and "reason" not in unparse(d)
        for d in node.decorator_list
    )


# ── parametrize helpers ───────────────────────────────────────────────────────

def param_missing_ids(node: ast.AST) -> bool:
    for d in node.decorator_list:
        src = unparse(d)
        if "parametrize" in src and "id=" not in src and "pytest.param" not in src:
            return True
    return False

def param_count(node: ast.AST) -> int:
    for d in node.decorator_list:
        src = unparse(d)
        if "parametrize" in src:
            m = re.search(r"\[(.+)\]", src, re.DOTALL)
            if m:
                depth, count = 0, 1
                for ch in m.group(1):
                    if ch in "([{":
                        depth += 1
                    elif ch in ")]}":
                        depth -= 1
                    elif ch == "," and depth == 0:
                        count += 1
                return count
    return 0

def param_single(node: ast.AST) -> bool:
    return any(
        "parametrize" in unparse(d) and param_count(node) == 1
        for d in node.decorator_list
    )

def param_ids_with_special_chars(node: ast.AST) -> bool:
    for d in node.decorator_list:
        src = unparse(d)
        if "parametrize" in src and "id=" in src:
            ids = re.findall(r'id=["\']([^"\']+)["\']', src)
            if any(re.search(r"[ /\[\](){}]", i) for i in ids):
                return True
    return False


# ── assert quality ────────────────────────────────────────────────────────────

def assert_count(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.Assert))

def has_loop_with_assert(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if (
            isinstance(n, (ast.For, ast.While))
            and n is not node
            and any(isinstance(c, ast.Assert) for c in ast.walk(n))
        ):
            return True
    return False

def float_direct_compare(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Assert)
            and isinstance(n.test, ast.Compare)
            and any(isinstance(op, ast.Eq) for op in n.test.ops)
        ):
            for a in [n.test.left] + n.test.comparators:
                if isinstance(a, ast.Constant) and isinstance(a.value, float):
                    return True
    return False

def has_assert_true_literal(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Assert):
            val = unparse(n.test)
            if val in ("True", "1 == 1", "(1 == 1)", "1==1"):
                return True
    return False

def has_assert_result_bare(node: ast.AST) -> bool:
    BARE_NAMES = {"result", "response", "res", "output", "ret", "rv", "data"}
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Assert)
            and isinstance(n.test, ast.Name)
            and n.test.id in BARE_NAMES
        ):
            return True
    return False

def has_assert_len_gt_zero(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Assert):
            t = n.test
            if (
                isinstance(t, ast.Compare)
                and isinstance(t.left, ast.Call)
                and isinstance(t.left.func, ast.Name)
                and t.left.func.id == "len"
                and len(t.ops) == 1
                and isinstance(t.ops[0], ast.Gt)
                and len(t.comparators) == 1
                and isinstance(t.comparators[0], ast.Constant)
                and t.comparators[0].value == 0
            ):
                return True
    return False

def multi_raises(node: ast.AST) -> int:
    count = 0
    for n in ast.walk(node):
        if isinstance(n, ast.With):
            for item in n.items:
                if "pytest.raises" in unparse(item.context_expr):
                    count += 1
    return count


def has_time_sleep(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call) and unparse(n.func) == "time.sleep"
        for n in ast.walk(node)
    )


def broad_raises(node: ast.AST) -> list[tuple[int, str]]:
    """Return broad exception names used with pytest.raises()."""
    found = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Call) or unparse(n.func) != "pytest.raises" or not n.args:
            continue
        exception = unparse(n.args[0])
        if exception in {"Exception", "BaseException"}:
            found.append((n.lineno, exception))
    return found


def raises_with_multiple_statements(node: ast.AST) -> list[int]:
    lines = []
    for n in ast.walk(node):
        if not isinstance(n, ast.With):
            continue
        if any(
            isinstance(item.context_expr, ast.Call)
            and unparse(item.context_expr.func) == "pytest.raises"
            for item in n.items
        ) and len(n.body) > 1:
            lines.append(n.lineno)
    return lines


def warns_without_match(node: ast.AST) -> list[int]:
    lines = []
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Call)
            and unparse(n.func) == "pytest.warns"
            and not any(k.arg == "match" for k in n.keywords)
        ):
            lines.append(n.lineno)
    return lines


def duplicate_parametrize_cases(node: ast.AST) -> list[int]:
    """Return duplicate case indexes for literal @parametrize sequences."""
    duplicates = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call) or "parametrize" not in unparse(decorator.func):
            continue
        if len(decorator.args) < 2 or not isinstance(decorator.args[1], (ast.List, ast.Tuple)):
            continue
        seen: dict[str, int] = {}
        for index, case in enumerate(decorator.args[1].elts):
            key = ast.dump(case, include_attributes=False)
            if key in seen:
                duplicates.append(index)
            else:
                seen[key] = index
    return duplicates


def has_assert_false_literal(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Assert)
        and isinstance(n.test, ast.Constant)
        and n.test.value in (False, 0, None)
        for n in ast.walk(node)
    )


def pytest_fail_without_message(node: ast.AST) -> list[int]:
    return [
        n.lineno for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and unparse(n.func) == "pytest.fail"
        and not n.args
        and not any(k.arg in {"reason", "msg"} for k in n.keywords)
    ]


def has_assert_in_except(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.ExceptHandler)
        and any(isinstance(child, ast.Assert) for stmt in n.body for child in ast.walk(stmt))
        for n in ast.walk(node)
    )


def debugger_calls(node: ast.AST) -> list[tuple[int, str]]:
    names = {"breakpoint", "pdb.set_trace", "ipdb.set_trace"}
    return [
        (n.lineno, unparse(n.func)) for n in ast.walk(node)
        if isinstance(n, ast.Call) and unparse(n.func) in names
    ]


def fixture_default_args(node: ast.AST) -> list[str]:
    positional = [arg.arg for arg in (*node.args.posonlyargs, *node.args.args)]
    default_names = positional[len(positional) - len(node.args.defaults):]
    default_names.extend(
        arg.arg for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
        if default is not None
    )
    return default_names


def has_non_assert_verification(node: ast.AST) -> bool:
    """Recognize common pytest/mock verification calls used without assert statements."""
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        name = unparse(n.func)
        if name in {"pytest.fail", "pytest.skip"} or "assert_called" in name:
            return True
    return False


# ── fixture call detection ────────────────────────────────────────────────────

def calls_fixture(node: ast.AST, known: set[str]) -> list[str]:
    return [
        n.func.id
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in known
    ]


# ── path / environment safety ─────────────────────────────────────────────────

def has_hardcoded_tmp(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and re.search(r"^/tmp/", n.value)
        for n in ast.walk(node)
    )

def has_write_to_real_path(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            fn = unparse(n.func)
            if fn == "open" and n.args:
                first = unparse(n.args[0])
                mode_arg = (
                    unparse(n.args[1]) if len(n.args) > 1
                    else next(
                        (unparse(k.value) for k in n.keywords if k.arg == "mode"),
                        "",
                    )
                )
                if (
                    any(m in mode_arg for m in ('"w"', "'w'", '"a"', "'a'", '"x"', "'x'"))
                    and "tmp_path" not in first
                    and not first.startswith("tmp")
                ):
                    return True
    return False

def modifies_environ_directly(node: ast.AST) -> bool:
    src = unparse(node)
    return bool(
        re.search(
            r"os\.environ\s*\[.*\]\s*=|os\.environ\.(?:update|pop|setdefault)\s*\(",
            src,
        )
    )


# ── async ─────────────────────────────────────────────────────────────────────


def has_asyncio_sleep_zero(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Call)
            and unparse(n.func) == "asyncio.sleep"
            and n.args
            and unparse(n.args[0]) == "0"
        ):
            return True
    return False

def has_asyncio_run(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call) and "asyncio.run" in unparse(n.func)
        for n in ast.walk(node)
    )


# ── mocking ───────────────────────────────────────────────────────────────────

def has_print(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "print"
        for n in ast.walk(node)
    )

def has_bare_except(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.ExceptHandler):
            if n.type is None:
                return True
            if (
                unparse(n.type) in ("Exception", "BaseException")
                and all(isinstance(s, (ast.Pass, ast.Continue)) for s in n.body)
            ):
                return True
    return False

def patches_mock(node: ast.AST) -> bool:
    src = unparse(node)
    return ".patch(" in src or "mocker.patch" in src

def has_assert_called(node: ast.AST) -> bool:
    src = unparse(node)
    return any(
        k in src
        for k in ("assert_called", "assert_any_call", "assert_has_calls", "call_count", "call_args")
    )

def uses_unittest_patch(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Call)
        and re.search(r"unittest\.mock\.patch|mock\.patch", unparse(n.func))
        for n in ast.walk(node)
    )

def mock_any_overused(node: ast.AST) -> bool:
    src = unparse(node)
    return src.count("mock.ANY") + src.count(", ANY") >= 3

def patch_targets(node: ast.AST) -> list[str]:
    targets = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and "patch" in unparse(n.func) and n.args:
            targets.append(unparse(n.args[0]).strip("\"'"))
    return targets

def uses_unittest_mock_import(tree: ast.AST) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any("unittest.mock" in a.name for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and n.module and "unittest.mock" in n.module:
            return True
    return False

def module_level_mock(tree: ast.AST) -> bool:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            src = unparse(node)
            if re.search(r"\bMagicMock\(\)|\bMock\(\)", src):
                return True
    return False



def all_classes_no_class_fixtures(nodes: list, fixture_meta: dict) -> bool:
    """All tests are inside classes but no class-scoped fixture exists."""
    has_class    = any(isinstance(n, ast.ClassDef) and is_test_class(n) for n in nodes)
    has_top_func = any(is_test_func(n) for n in nodes)
    if not has_class or has_top_func:
        return False
    return not any(fx.get("scope") == "class" for fx in fixture_meta.values())


def is_called_in_tree(func_name: str, tree: ast.AST) -> bool:
    """
    True if func_name is referenced anywhere in the tree outside its own
    definition. Covers all usage patterns:

        check_user(x)                       bare call
        self.check_user(x)                  method call on self
        self.check_user                     attribute reference
        run(check_user)                     passed as positional arg
        mock.side_effect = check_user       assigned as value
        validators = [check_user]           in a list/dict
    """
    for node in ast.walk(tree):
        # bare Name reference anywhere in the tree
        # (the function's own name inside its def body is also a Name node
        # but it appears as part of the FunctionDef, not a standalone Name)
        if isinstance(node, ast.Name) and node.id == func_name:
            return True
        # attribute access: self.check_user or obj.check_user
        if isinstance(node, ast.Attribute) and node.attr == func_name:
            return True
    return False


def has_pytest_raises(node: ast.AST) -> bool:
    """True if the test contains a pytest.raises() context manager."""
    for n in ast.walk(node):
        if isinstance(n, ast.With):
            for item in n.items:
                if "pytest.raises" in unparse(item.context_expr):
                    return True
    return False


def asyncio_mode_is_auto(tree: ast.AST) -> bool:
    """
    True if asyncio_mode='auto' is set anywhere in the file —
    a common pattern via pytestmark or module-level config comment.
    We can't read pyproject.toml here so we check for the string
    in the module source as a heuristic.
    """
    src = unparse(tree)
    return "asyncio_mode" in src and "auto" in src


def param_has_marks_only(node: ast.AST) -> bool:
    """
    True if @parametrize has only 1 case but that case uses pytest.param
    with marks — a valid pattern for xfail/skip on a specific input.
    """
    for d in node.decorator_list:
        src = unparse(d)
        if ("parametrize" in src and param_count(node) == 1
                and "pytest.param" in src and ("xfail" in src or "skip" in src)):
                return True
    return False


def is_builtin_patch_target(target: str) -> bool:
    """
    True when patching a builtin that legitimately has no module path —
    e.g. 'builtins.open', 'builtins.print', 'open', 'print'.
    """
    builtin_names = {
        "open", "print", "input", "len", "range", "sorted",
        "builtins.open", "builtins.print", "builtins.input",
    }
    return target in builtin_names or target.startswith("builtins.")