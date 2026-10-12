"""Real browser workflows against the local server; only GitHub is stubbed."""
import json

import pytest
from playwright.sync_api import expect

from page_objects import AuditPage, HtmlReportPage

pytestmark = pytest.mark.browser


@pytest.fixture
def audit_page(page, app_url):
    audit = AuditPage(page)
    audit.open(app_url)
    return audit


# Shared setup runs the real app and waits for an audit; each test receives a fresh browser page.
@pytest.fixture
def page_with_audit_results(audit_page: AuditPage, browser_test_suite):
    audit_page.set_path(browser_test_suite)
    audit_page.run_audit()
    expect(audit_page.status).to_contain_text('Audit complete.')
    return audit_page


# Drive each scope through the form rather than calling the backend directly.
@pytest.mark.parametrize('mode,expected_count', [
    ('suite', '2'), ('file', '1'), ('test', '1'),
], ids=['suite', 'file', 'single-test'])
def test_run_audit_and_view_results(audit_page: AuditPage, browser_test_suite, mode, expected_count):
    expect(audit_page.audit_scope).to_have_count(0)
    target = browser_test_suite if mode == 'suite' else browser_test_suite / 'test_beta.py'
    audit_page.set_path(target)
    if mode == 'test':
        audit_page.test_function.fill('test_placeholder')
    audit_page.run_audit()
    expect(audit_page.status).to_contain_text('Audit complete.')
    expect(audit_page.test_count).to_have_text(expected_count)
    expect(audit_page.score_heading).to_be_visible()
    audit_page.show_tab('Tests')
    expect(audit_page.rows).to_have_count(int(expected_count))
    expect(audit_page.first_test_path).to_contain_text('sample_tests/')


# Assert the entire order in both directions, not just the first row.
@pytest.mark.parametrize('key,direction,expected_codes', [
    ('severity', 'asc', ['T001', 'T019', 'T012']),
    ('severity', 'desc', ['T012', 'T019', 'T001']),
    ('category', 'asc', ['T001', 'T019', 'T012']),
    ('category', 'desc', ['T012', 'T019', 'T001']),
    ('file', 'asc', ['T001', 'T019', 'T012']),
    ('file', 'desc', ['T012', 'T019', 'T001']),
], ids=['severity-first', 'severity-last', 'category-ascending', 'category-descending',
        'file-ascending', 'file-descending'])
def test_issue_sorting_orders_every_row(audit_page: AuditPage, page_with_audit_results, key, direction, expected_codes):
    audit_page.sort_by.select_option(key)
    audit_page.order.select_option(direction)
    assert audit_page.issue_codes() == expected_codes


# Changing one filter must not silently discard the other filter’s selection.
def test_search_and_severity_filters_work_together(audit_page: AuditPage, page_with_audit_results):
    audit_page.severity.select_option('warning')
    audit_page.search.fill('T019')
    expect(audit_page.rows).to_have_count(1)
    assert audit_page.issue_codes() == ['T019']
    audit_page.severity.select_option('error')
    expect(audit_page.empty_results).to_be_visible()
    audit_page.search.fill('')
    assert audit_page.issue_codes() == ['T001']


def test_finding_explanation_can_be_opened(audit_page: AuditPage, page_with_audit_results):
    audit_page.search.fill('T019')
    audit_page.open_finding_explanation()
    expect(audit_page.finding_details).to_have_attribute('open', '')
    expect(audit_page.finding_details).to_contain_text('cannot detect a regression')
    expect(audit_page.finding_details).to_contain_text('Replace the placeholder')


# Navigate from a parent folder before selecting a directory or a Python file.
@pytest.mark.parametrize('selection,expected_mode', [('folder', 'suite'), ('file', 'file')])
def test_folder_picker_navigates_and_selects_sources(audit_page: AuditPage, browser_test_suite, selection, expected_mode):
    audit_page.path.fill(str(browser_test_suite.parent))
    audit_page.browse()
    audit_page.folder_picker.open_folder('sample_tests')
    expect(audit_page.folder_picker.path).to_have_value(str(browser_test_suite))
    if selection == 'file':
        audit_page.folder_picker.select_file('test_beta.py')
    else:
        audit_page.folder_picker.select_folder()
    target = browser_test_suite / 'test_beta.py' if selection == 'file' else browser_test_suite
    expect(audit_page.folder_picker.dialog).not_to_be_visible()
    expect(audit_page.path).to_have_value(str(target))
    expect(audit_page.audit_scope).to_have_count(0)


def test_missing_local_path_explains_failure(audit_page: AuditPage, tmp_path):
    audit_page.path.fill(str(tmp_path / 'missing'))
    audit_page.run_audit()
    expect(audit_page.status).to_have_text('Enter an existing local path.')
    expect(audit_page.run_button).to_be_enabled()
    expect(audit_page.results).not_to_be_visible()


def test_empty_suite_has_no_numeric_quality_score(audit_page: AuditPage, tmp_path):
    audit_page.path.fill(str(tmp_path))
    audit_page.run_audit()
    expect(audit_page.status).to_contain_text('No tests found.')
    expect(audit_page.quality_score).to_have_text('Not assessed')
    expect(audit_page.score_breakdown).to_be_empty()


# Only GitHub network traffic is replaced; the HTTP server, scanner, and UI remain real.
def test_github_form_runs_audit_and_clears_token(audit_page: AuditPage, monkeypatch, zip_archive):
    data = zip_archive({'repo-sha/tests/test_browser.py': 'def test_browser():\n    assert True\n'})
    downloads = []

    def download(repository, ref, token):
        downloads.append((repository, ref, token))
        return data

    monkeypatch.setattr('web_server.download_repository', download)
    audit_page.source.select_option('github')
    audit_page.repository.fill('example/repo')
    audit_page.ref.fill('main')
    audit_page.path.fill('tests')
    audit_page.token.fill('dummy')
    audit_page.run_audit()
    expect(audit_page.result_title).to_have_text('github:example/repo@main/tests')
    expect(audit_page.test_count).to_have_text('1')
    expect(audit_page.token).to_have_value('')
    assert downloads == [('example/repo', 'main', 'dummy')]


# Failure recovery must clear the token and make the Run audit button usable again.
def test_github_failure_also_clears_token(audit_page: AuditPage, monkeypatch):
    def fail_download(*args):
        raise ValueError('GitHub request failed (404). Check the repository.')

    monkeypatch.setattr('web_server.download_repository', fail_download)
    audit_page.source.select_option('github')
    audit_page.repository.fill('example/missing')
    audit_page.token.fill('dummy')
    audit_page.run_audit()
    expect(audit_page.status).to_contain_text('GitHub request failed (404)')
    expect(audit_page.token).to_have_value('')
    expect(audit_page.run_button).to_be_enabled()


# Read the actual browser download to confirm filename and report contents.
def test_json_download_contains_current_audit(audit_page: AuditPage, page_with_audit_results, tmp_path):
    download = audit_page.download('JSON')
    output = tmp_path / 'download.json'
    download.save_as(output)
    report = json.loads(output.read_text())
    assert download.suggested_filename == 'pytest_audit.json'
    assert report['total_tests'] == 2
    assert report['score_breakdown']['status'] == 'assessed'


# Reopen the downloaded file without the server and exercise its embedded sorting code.
def test_html_download_is_interactive_offline(audit_page: AuditPage, page_with_audit_results, tmp_path):
    download = audit_page.download('HTML')
    output = tmp_path / 'download.html'
    download.save_as(output)
    report_page = HtmlReportPage(audit_page.page)
    report_page.open(output)
    report_page.sort_by.select_option('category')
    expect(report_page.categories).to_have_text(['Assertions & verification', 'Assertions & verification', 'Debugging & maintainability'])
    report_page.order.select_option('desc')
    expect(report_page.categories).to_have_text(['Debugging & maintainability', 'Assertions & verification', 'Assertions & verification'])


# Users can run an audit without choosing a threshold; errors explain the score cap.
def test_minimum_score_is_not_requested_and_error_cap_is_explained(audit_page: AuditPage, browser_test_suite):
    # Add clean tests so the ordinary density score exceeds 70 and the cap is exercised.
    (browser_test_suite / 'test_clean.py').write_text(''.join(
        f'def test_verified_{index}_result():\n    assert 1 + 1 == 2\n' for index in range(10)
    ))
    expect(audit_page.minimum_score).to_have_count(0)
    audit_page.set_path(browser_test_suite)
    audit_page.run_audit()
    expect(audit_page.status).to_contain_text('Audit complete.')
    expect(audit_page.quality_score).to_have_text('70/100')
    expect(audit_page.score_note).to_contain_text('cannot exceed 70/100')
    audit_page.show_tab('Configuration')
    expect(audit_page.table).not_to_contain_text('Score threshold')


@pytest.mark.parametrize('folder', [False, True])
def test_upload_from_laptop(audit_page: AuditPage, browser_test_suite, folder):
    audit_page.source.select_option('upload')
    expect(audit_page.path_fields).not_to_be_visible()
    expect(audit_page.audit_scope).to_have_count(0)
    if folder:
        audit_page.upload_type.select_option('folder')
        audit_page.upload(browser_test_suite)
    else:
        audit_page.upload(browser_test_suite / 'test_beta.py')
    audit_page.run_audit()
    expect(audit_page.status).to_contain_text('Audit complete.')
    expect(audit_page.test_count).to_have_text('2' if folder else '1')
    expect(audit_page.table).to_contain_text('test_beta.py')


def test_related_rules_group_under_readable_categories(audit_page: AuditPage, page_with_audit_results):
    expect(audit_page.sort_by).to_have_value('category')
    expect(audit_page.categories).to_have_text([
        'Assertions & verification', 'Assertions & verification', 'Debugging & maintainability'])
    assert audit_page.issue_codes() == ['T001','T019','T012']
    audit_page.search.fill('Assertions & verification')
    expect(audit_page.rows).to_have_count(2)
    audit_page.search.fill('')
    audit_page.order.select_option('desc')
    expect(audit_page.categories.first).to_have_text('Debugging & maintainability')


def test_single_picker_resets_selection_when_switching_type(audit_page: AuditPage, browser_test_suite):
    audit_page.source.select_option('upload')
    expect(audit_page.upload_inputs).to_have_count(1)
    audit_page.upload(browser_test_suite / 'test_beta.py')
    expect(audit_page.upload_selection).to_contain_text('1 source/configuration files selected')
    audit_page.upload_type.select_option('folder')
    expect(audit_page.upload_input).to_have_attribute('webkitdirectory', '')
    audit_page.upload_type.select_option('file')
    expect(audit_page.upload_input).not_to_have_attribute('webkitdirectory', '')
    expect(audit_page.upload_input).to_have_value('')
    audit_page.run_audit()
    expect(audit_page.status).to_contain_text('Choose a Python file or a folder')
