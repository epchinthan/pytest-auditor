"""Auditor AST-analysis tests; source snippets are data and never run a browser.

Real Playwright executions live in test_web_ui_browser.py. These tests verify
what the auditor reports when it reads sync/async browser-test source files.
"""
import pytest


def issue_codes(report):
    return {issue.code for file in report.files for issue in file.issues}


# These are static source inputs: no browsers or Playwright calls run in this module.
@pytest.mark.parametrize('mode', ['suite', 'file', 'test'])
@pytest.mark.parametrize('header,matcher', [
    ('from playwright.sync_api import expect', 'expect'),
    ('from playwright.sync_api import expect as verify', 'verify'),
    ('import playwright.sync_api as pw', 'pw.expect'),
    ('from playwright.sync_api import expect', 'expect.soft'),
], ids=['direct', 'alias', 'namespace', 'soft'])
def test_expect_matchers_count_as_verification(scan_source, mode, header, matcher):
    report = scan_source(header + f'''
def test_checkout(page):
    {matcher}(page).to_have_title("Store")
    assert 1 + 1 == 2
''', mode=mode)
    test = next(test for file in report.files for test in file.tests)
    assert test['asserts'] == 2
    assert test['framework'] == 'playwright'
    assert 'T001' not in issue_codes(report)


# An async matcher needs await; otherwise its coroutine never performs verification.
@pytest.mark.parametrize('mode', ['suite', 'file', 'test'])
@pytest.mark.parametrize('awaited', [True, False], ids=['awaited', 'missing-await'])
def test_async_matchers_require_await(scan_source, mode, awaited):
    statement = 'await expect(page).to_have_url("https://example.com")' if awaited else 'expect(page).to_have_url("https://example.com")'
    report = scan_source(f'''from playwright.async_api import expect
async def test_checkout(page):
    {statement}
''', mode=mode)
    assert ('PW04' in issue_codes(report)) == (not awaited)
    assert 'T001' not in issue_codes(report)
    assert report.async_count == 1


# The source layout is deliberate: warning line numbers must point to the bad statement.
@pytest.mark.parametrize('mode', ['suite', 'file', 'test'])
def test_browser_warnings_identify_the_actual_statement(scan_source, mode):
    report = scan_source('''
        from playwright.sync_api import Page, expect

        def test_checkout(page: Page):
            page.wait_for_timeout(1000)
            page.goto("https://example.com", wait_until="networkidle")
            button = page.get_by_role("button")
            assert button.is_visible()
            expect(button).to_be_enabled()
    ''', mode=mode)
    warnings = [(issue.code, issue.line, issue.level)
                for file in report.files for issue in file.issues if issue.code.startswith('PW')]
    assert warnings == [('PW01', 4, 'warning'), ('PW02', 5, 'warning'), ('PW03', 7, 'warning')]


# A Playwright import alone must not turn every test in the module into a browser test.
def test_unit_test_in_browser_module_keeps_generic_rules(scan_source):
    report = scan_source('''
        from playwright.sync_api import expect

        def test_checkout(client):
            client.wait_for_timeout(1000)
            client.goto("url", wait_until="networkidle")
            client.is_visible()
    ''')
    assert report.files[0].tests[0]['framework'] == 'pytest'
    assert 'T001' in issue_codes(report)
    assert not any(code.startswith('PW') for code in issue_codes(report))


@pytest.mark.parametrize('body', [
    'expect(page)', 'page.goto("url")', 'expect.set_options(timeout=1000)',
], ids=['bare-expect', 'navigation-only', 'configuration-only'])
def test_non_verifying_browser_calls_do_not_count_as_assertions(scan_source, body):
    report = scan_source(f'''from playwright.sync_api import expect, Page

def test_checkout(page: Page):
    {body}
''')
    assert report.files[0].tests[0]['asserts'] == 0
    assert 'T001' in issue_codes(report)


# Browser workflows may verify several UI states without receiving the unit-test assertion limit.
@pytest.mark.parametrize('browser_test,expected_warning', [(True, False), (False, True)],
                         ids=['browser-workflow', 'unit-test'])
def test_assertion_limit_depends_on_test_nature(scan_source, browser_test, expected_warning):
    header = 'from playwright.sync_api import expect\n' if browser_test else ''
    signature = 'page' if browser_test else ''
    assertion = 'expect(page).to_have_title("Store")' if browser_test else 'assert 1 + 1 == 2'
    source = header + f'def test_checkout({signature}):\n' + f'    {assertion}\n' * 6
    assert ('T002' in issue_codes(scan_source(source))) == expected_warning


@pytest.mark.parametrize('mark', ['only_browser', 'skip_browser', 'browser_context_args'])
def test_browser_plugin_marks_are_accepted(scan_source, mark):
    report = scan_source(f'''import pytest
from playwright.sync_api import expect
@pytest.mark.{mark}
def test_checkout(page):
    expect(page).to_have_title("Store")
''')
    assert 'M001' not in issue_codes(report)


# A session fixture cannot request the plugin’s function-scoped page fixture.
@pytest.mark.parametrize('mode', ['suite', 'file', 'test'])
def test_browser_fixture_scope_mismatch_is_reported(scan_source, mode):
    report = scan_source('''
        import pytest
        from playwright.sync_api import Page, expect

        @pytest.fixture(scope="session")
        def login(page: Page):
            return page

        def test_checkout(login):
            expect(login).to_have_title("Store")
    ''', mode=mode)
    assert 'FX05' in issue_codes(report)


def test_plugin_only_browser_calls_are_detected_without_imports(scan_source):
    report = scan_source('''
        def test_checkout(page):
            page.get_by_role("button").click()
            page.wait_for_timeout(1000)
    ''')
    assert {'PW01', 'T001'} <= issue_codes(report)
    assert report.files[0].tests[0]['framework'] == 'playwright'


# A helper may own verification; that should produce a note rather than a missing-assert error.
def test_delegated_browser_verification_is_an_information_note(scan_source):
    report = scan_source('''
        from playwright.sync_api import expect

        def check_title(page):
            expect(page).to_have_title("Store")

        def test_checkout(page):
            check_title(page)
    ''')
    findings = [issue for file in report.files for issue in file.issues if issue.code == 'T001']
    assert [issue.level for issue in findings] == ['info']
    assert report.score_breakdown['deductions']['Suggestions'] == 0


def test_unrelated_expect_function_does_not_count_as_verification(scan_source):
    report = scan_source('''
        def expect(value):
            return value

        def test_checkout(page):
            expect(page).to_be_visible()
    ''')
    assert 'T001' in issue_codes(report)
