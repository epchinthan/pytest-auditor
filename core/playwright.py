"""Conservative static recognition of Python Playwright tests; no imports executed."""
import ast

from core.models import Issue, WARNING
from core import ast_helpers as h

FIXTURE_SCOPES = {**dict.fromkeys(('page', 'context', 'new_context'), 'function'),
                  **dict.fromkeys(('playwright', 'browser', 'browser_type', 'browser_name',
                                   'browser_channel', 'is_chromium', 'is_firefox', 'is_webkit',
                                   'browser_context_args', 'browser_type_launch_args', 'connect_options'), 'session')}
MARKS = {'only_browser', 'skip_browser', 'browser_context_args'}
TYPES = {'Page', 'Browser', 'BrowserContext', 'Locator', 'Playwright', 'APIRequestContext'}
LOCATORS = {'locator', 'get_by_role', 'get_by_text', 'get_by_label', 'get_by_placeholder',
            'get_by_test_id', 'get_by_alt_text', 'get_by_title', 'frame_locator'}


def imports(tree):
    bindings = {}
    for item in ast.walk(tree) if tree is not None else []:
        if isinstance(item, ast.ImportFrom) and item.module in {'playwright.sync_api', 'playwright.async_api'}:
            for alias in item.names:
                bindings[alias.asname or alias.name] = f'{item.module}.{alias.name}'
        elif isinstance(item, ast.Import):
            for alias in item.names:
                if alias.name == 'playwright' or alias.name.startswith('playwright.'):
                    bindings[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else 'playwright'
    for item in getattr(tree, "body", []):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings.pop(item.name, None)
    return bindings


def qualified(expr, bindings):
    text = ast.unparse(expr)
    head, *tail = text.split('.')
    return '.'.join([bindings.get(head, head), *tail])


def expect_calls(node, tree):
    bindings = imports(tree)
    for arg in getattr(getattr(node, "args", None), "args", []):
        bindings.pop(arg.arg, None)
    calls = []
    for item in ast.walk(node):
        if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Attribute):
            continue
        if not item.func.attr.startswith(('to_', 'not_to_')):
            continue
        base = item.func.value
        if isinstance(base, ast.Call) and qualified(base.func, bindings) in {
            'playwright.sync_api.expect', 'playwright.async_api.expect',
            'playwright.sync_api.expect.soft', 'playwright.async_api.expect.soft',
        }:
            calls.append(item)
    return calls


def browser_names(node, tree):
    bindings = imports(tree)
    names = set()
    for arg in node.args.args + node.args.kwonlyargs:
        if arg.annotation:
            annotation = arg.annotation
            if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
                try:
                    annotation = ast.parse(annotation.value, mode='eval').body
                except SyntaxError:
                    continue
            if qualified(annotation, bindings) in {f'playwright.{api}.{kind}' for api in ('sync_api', 'async_api') for kind in TYPES}:
                names.add(arg.arg)
        if bindings and arg.arg in FIXTURE_SCOPES:
            names.add(arg.arg)
    # Common plugin-only files omit imports and type annotations. Require a
    # characteristic locator call on a standard browser fixture, not its name alone.
    for item in ast.walk(node):
        if (isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)
                and item.func.attr in LOCATORS | {"wait_for_timeout", "wait_for_load_state"} and isinstance(item.func.value, ast.Name)
                and item.func.value.id in {'page', 'context'}):
            names.add(item.func.value.id)
    # Track local locator/page aliases without treating unrelated objects as browser APIs.
    changed = True
    while changed:
        changed = False
        for item in ast.walk(node):
            if isinstance(item, (ast.Assign, ast.AnnAssign)):
                value = item.value
                if value is not None and receiver_known(value, names):
                    targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id not in names:
                            names.add(target.id)
                            changed = True
    return names


def receiver_known(expr, names):
    if isinstance(expr, ast.Name):
        return expr.id in names
    if isinstance(expr, (ast.Attribute, ast.Await)):
        return receiver_known(expr.value, names)
    if isinstance(expr, ast.Call):
        return receiver_known(expr.func, names)
    return False


def is_playwright(node, tree):
    return bool(expect_calls(node, tree) or browser_names(node, tree))


def assertion_count(node, tree):
    return h.assert_count(node, tree) + len(expect_calls(node, tree))


def check(node, path, tree):
    if not is_playwright(node, tree):
        return []
    names = browser_names(node, tree)
    issues = []
    def add(code, item, message):
        issues.append(Issue(WARNING, code, f'{node.name}: {message}', str(path), item.lineno))
    parents = {child: parent for parent in ast.walk(node) for child in ast.iter_child_nodes(parent)}
    bindings = imports(tree)
    for call in expect_calls(node, tree):
        base = call.func.value
        if qualified(base.func, bindings).startswith('playwright.async_api.') and not isinstance(parents.get(call), ast.Await):
            add('PW04', call, 'Async Playwright assertion is not awaited — await expect(...).matcher() so verification runs.')
    for item in ast.walk(node):
        if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Attribute):
            continue
        if not receiver_known(item.func.value, names):
            continue
        method = item.func.attr
        if method == 'wait_for_timeout':
            add('PW01', item, 'Fixed browser delay — use auto-waiting actions or expect() assertions.')
        if method in {'goto', 'reload', 'go_back', 'go_forward', 'set_content', 'wait_for_url', 'wait_for_load_state'}:
            values = [k.value for k in item.keywords if k.arg in {'wait_until', 'state'}]
            if method == 'wait_for_load_state':
                values += item.args[:1]
            if any(isinstance(v, ast.Constant) and v.value == 'networkidle' for v in values):
                add('PW02', item, 'networkidle is unreliable for test readiness — assert the expected UI state with expect().')
    snapshots = {'is_visible', 'is_hidden', 'is_enabled', 'is_disabled', 'is_checked',
                 'text_content', 'inner_text', 'input_value', 'count', 'get_attribute', 'title'}
    for item in ast.walk(node):
        if not isinstance(item, ast.Assert):
            continue
        if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
               and c.func.attr in snapshots and receiver_known(c.func.value, names)
               for c in ast.walk(item.test)):
            add('PW03', item, 'UI snapshot asserted without retries — prefer a matching expect() assertion (await it for async tests).')
    return issues
