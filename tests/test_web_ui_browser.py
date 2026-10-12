"""Real browser workflows against the local server; only GitHub is stubbed."""
import json

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


# Shared setup runs the real app and waits for an audit; each test receives a fresh browser page.
@pytest.fixture
def page_with_audit_results(page: Page, app_url, browser_test_suite):
    page.goto(app_url)
    page.locator('#path').fill(str(browser_test_suite))
    page.get_by_role('button', name='Run audit').click()
    expect(page.locator('#status')).to_contain_text('Audit complete.')
    return page


# Drive each scope through the form rather than calling the backend directly.
@pytest.mark.parametrize('mode,expected_count', [
    ('suite', '2'), ('file', '1'), ('test', '1'),
], ids=['suite', 'file', 'single-test'])
def test_run_audit_and_view_results(page: Page, app_url, browser_test_suite, mode, expected_count):
    page.goto(app_url)
    expect(page.get_by_label('Audit scope')).to_have_count(0)
    target = browser_test_suite if mode == 'suite' else browser_test_suite / 'test_beta.py'
    page.locator('#path').fill(str(target))
    if mode == 'test':
        page.get_by_label('Test function').fill('test_placeholder')
    page.get_by_role('button', name='Run audit').click()
    expect(page.locator('#status')).to_contain_text('Audit complete.')
    expect(page.locator('#metrics .metric').nth(1).locator('.value')).to_have_text(expected_count)
    expect(page.get_by_role('heading', name='How this score is calculated')).to_be_visible()
    page.get_by_role('tab', name='Tests', exact=True).click()
    expect(page.locator('#table tbody tr')).to_have_count(int(expected_count))
    expect(page.locator('#table tbody tr').first.locator('td').first).to_contain_text('sample_tests/')


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
def test_issue_sorting_orders_every_row(page: Page, page_with_audit_results, key, direction, expected_codes):
    page.get_by_label('Sort by', exact=True).select_option(key)
    page.get_by_label('Order', exact=True).select_option(direction)
    assert page.locator('#table tbody tr').evaluate_all('(rows) => rows.map(row => row.dataset.code)') == expected_codes


# Changing one filter must not silently discard the other filter’s selection.
def test_search_and_severity_filters_work_together(page: Page, page_with_audit_results):
    page.get_by_label('Severity', exact=True).select_option('warning')
    page.get_by_label('Search results').fill('T019')
    expect(page.locator('#table tbody tr')).to_have_count(1)
    assert page.locator('#table tbody tr').evaluate_all('(rows) => rows.map(row => row.dataset.code)') == ['T019']
    page.get_by_label('Severity', exact=True).select_option('error')
    expect(page.get_by_text('No results for this view or filter.')).to_be_visible()
    page.get_by_label('Search results').fill('')
    assert page.locator('#table tbody tr').evaluate_all('(rows) => rows.map(row => row.dataset.code)') == ['T001']


def test_finding_explanation_can_be_opened(page: Page, page_with_audit_results):
    page.get_by_label('Search results').fill('T019')
    row = page.locator('#table tbody tr')
    row.get_by_text('Why this matters · How to fix').click()
    expect(row.locator('details')).to_have_attribute('open', '')
    expect(row.locator('details')).to_contain_text('cannot detect a regression')
    expect(row.locator('details')).to_contain_text('Replace the placeholder')


# Navigate from a parent folder before selecting a directory or a Python file.
@pytest.mark.parametrize('selection,expected_mode', [('folder', 'suite'), ('file', 'file')])
def test_folder_picker_navigates_and_selects_sources(page: Page, app_url, browser_test_suite, selection, expected_mode):
    page.goto(app_url)
    page.locator('#path').fill(str(browser_test_suite.parent))
    page.get_by_role('button', name='Browse…').click()
    page.locator('#browse-entries').get_by_role('button', name='▸ sample_tests', exact=True).click()
    expect(page.locator('#browse-path')).to_have_value(str(browser_test_suite))
    if selection == 'file':
        page.locator('#browse-entries').get_by_role('button', name='· test_beta.py', exact=True).click()
    else:
        page.get_by_role('button', name='Use this folder').click()
    target = browser_test_suite / 'test_beta.py' if selection == 'file' else browser_test_suite
    expect(page.get_by_role('dialog')).not_to_be_visible()
    expect(page.locator('#path')).to_have_value(str(target))
    expect(page.get_by_label('Audit scope')).to_have_count(0)


def test_missing_local_path_explains_failure(page: Page, app_url, tmp_path):
    page.goto(app_url)
    page.locator('#path').fill(str(tmp_path / 'missing'))
    page.get_by_role('button', name='Run audit').click()
    expect(page.locator('#status')).to_have_text('Enter an existing local path.')
    expect(page.get_by_role('button', name='Run audit')).to_be_enabled()
    expect(page.locator('#results')).not_to_be_visible()


def test_empty_suite_has_no_numeric_quality_score(page: Page, app_url, tmp_path):
    page.goto(app_url)
    page.locator('#path').fill(str(tmp_path))
    page.get_by_role('button', name='Run audit').click()
    expect(page.locator('#status')).to_contain_text('No tests found.')
    expect(page.locator('#metrics .metric').first.locator('.value')).to_have_text('Not assessed')
    expect(page.locator('#score-breakdown')).to_be_empty()


# Only GitHub network traffic is replaced; the HTTP server, scanner, and UI remain real.
def test_github_form_runs_audit_and_clears_token(page: Page, app_url, monkeypatch, zip_archive):
    data = zip_archive({'repo-sha/tests/test_browser.py': 'def test_browser():\n    assert True\n'})
    downloads = []

    def download(repository, ref, token):
        downloads.append((repository, ref, token))
        return data

    monkeypatch.setattr('web_server.download_repository', download)
    page.goto(app_url)
    page.get_by_label('Source', exact=True).select_option('github')
    page.get_by_label('GitHub repository', exact=True).fill('example/repo')
    page.get_by_label('Branch, tag, or commit').fill('main')
    page.locator('#path').fill('tests')
    page.get_by_label('Token (optional for private repos)').fill('dummy')
    page.get_by_role('button', name='Run audit').click()
    expect(page.locator('#result-title')).to_have_text('github:example/repo@main/tests')
    expect(page.locator('#metrics .metric').nth(1).locator('.value')).to_have_text('1')
    expect(page.get_by_label('Token (optional for private repos)')).to_have_value('')
    assert downloads == [('example/repo', 'main', 'dummy')]


# Failure recovery must clear the token and make the Run audit button usable again.
def test_github_failure_also_clears_token(page: Page, app_url, monkeypatch):
    def fail_download(*args):
        raise ValueError('GitHub request failed (404). Check the repository.')

    monkeypatch.setattr('web_server.download_repository', fail_download)
    page.goto(app_url)
    page.get_by_label('Source', exact=True).select_option('github')
    page.get_by_label('GitHub repository', exact=True).fill('example/missing')
    page.get_by_label('Token (optional for private repos)').fill('dummy')
    page.get_by_role('button', name='Run audit').click()
    expect(page.locator('#status')).to_contain_text('GitHub request failed (404)')
    expect(page.get_by_label('Token (optional for private repos)')).to_have_value('')
    expect(page.get_by_role('button', name='Run audit')).to_be_enabled()


# Read the actual browser download to confirm filename and report contents.
def test_json_download_contains_current_audit(page: Page, page_with_audit_results, tmp_path):
    with page.expect_download() as event:
        page.get_by_role('button', name='Download JSON').click()
    output = tmp_path / 'download.json'
    event.value.save_as(output)
    report = json.loads(output.read_text())
    assert event.value.suggested_filename == 'pytest_audit.json'
    assert report['total_tests'] == 2
    assert report['score_breakdown']['status'] == 'assessed'


# Reopen the downloaded file without the server and exercise its embedded sorting code.
def test_html_download_is_interactive_offline(page: Page, page_with_audit_results, tmp_path):
    with page.expect_download() as event:
        page.get_by_role('button', name='Download HTML').click()
    output = tmp_path / 'download.html'
    event.value.save_as(output)
    page.goto(output.as_uri())
    page.get_by_label('Sort by', exact=True).select_option('category')
    expect(page.locator('#iss-tbl tbody tr td:nth-child(3)')).to_have_text(['Assertions & verification', 'Assertions & verification', 'Debugging & maintainability'])
    page.get_by_label('Order', exact=True).select_option('desc')
    expect(page.locator('#iss-tbl tbody tr td:nth-child(3)')).to_have_text(['Debugging & maintainability', 'Assertions & verification', 'Assertions & verification'])


# Users can run an audit without choosing a threshold; errors explain the score cap.
def test_minimum_score_is_not_requested_and_error_cap_is_explained(page: Page, app_url, browser_test_suite):
    # Add clean tests so the ordinary density score exceeds 70 and the cap is exercised.
    (browser_test_suite / 'test_clean.py').write_text(''.join(
        f'def test_verified_{index}_result():\n    assert 1 + 1 == 2\n' for index in range(10)
    ))
    page.goto(app_url)
    expect(page.get_by_label('Minimum score')).to_have_count(0)
    page.locator('#path').fill(str(browser_test_suite))
    page.get_by_role('button', name='Run audit').click()
    expect(page.locator('#status')).to_contain_text('Audit complete.')
    expect(page.locator('#metrics .metric').first.locator('.value')).to_have_text('70/100')
    expect(page.locator('#score-note')).to_contain_text('cannot exceed 70/100')
    page.get_by_role('tab', name='Configuration', exact=True).click()
    expect(page.locator('#table')).not_to_contain_text('Score threshold')


@pytest.mark.parametrize('folder', [False, True])
def test_upload_from_laptop(page: Page, app_url, browser_test_suite, folder):
    page.goto(app_url)
    page.get_by_label('Source', exact=True).select_option('upload')
    expect(page.locator('#path-fields')).not_to_be_visible()
    expect(page.get_by_label('Audit scope')).to_have_count(0)
    if folder:
        page.get_by_label('Upload type').select_option('folder')
        page.locator('#upload-source').set_input_files(str(browser_test_suite))
    else:
        page.locator('#upload-source').set_input_files(str(browser_test_suite / 'test_beta.py'))
    page.get_by_role('button', name='Run audit').click()
    expect(page.locator('#status')).to_contain_text('Audit complete.')
    expect(page.locator('#metrics .metric').nth(1).locator('.value')).to_have_text('2' if folder else '1')
    expect(page.locator('#table')).to_contain_text('test_beta.py')


def test_related_rules_group_under_readable_categories(page: Page, page_with_audit_results):
    expect(page.get_by_label('Sort by', exact=True)).to_have_value('category')
    expect(page.locator('#table tbody tr td:nth-child(4)')).to_have_text([
        'Assertions & verification', 'Assertions & verification', 'Debugging & maintainability'])
    assert page.locator('#table tbody tr').evaluate_all('(rows) => rows.map(row => row.dataset.code)') == ['T001','T019','T012']
    page.get_by_label('Search results').fill('Assertions & verification')
    expect(page.locator('#table tbody tr')).to_have_count(2)
    page.get_by_label('Search results').fill('')
    page.get_by_label('Order', exact=True).select_option('desc')
    expect(page.locator('#table tbody tr td:nth-child(4)').first).to_have_text('Debugging & maintainability')


def test_single_picker_resets_selection_when_switching_type(page: Page, app_url, browser_test_suite):
    page.goto(app_url)
    page.get_by_label('Source', exact=True).select_option('upload')
    expect(page.locator('#upload-fields input[type=file]')).to_have_count(1)
    page.locator('#upload-source').set_input_files(str(browser_test_suite / 'test_beta.py'))
    expect(page.locator('#upload-selection')).to_contain_text('1 source/configuration files selected')
    page.get_by_label('Upload type').select_option('folder')
    expect(page.locator('#upload-source')).to_have_attribute('webkitdirectory', '')
    page.get_by_label('Upload type').select_option('file')
    expect(page.locator('#upload-source')).not_to_have_attribute('webkitdirectory', '')
    expect(page.locator('#upload-source')).to_have_value('')
    page.get_by_role('button', name='Run audit').click()
    expect(page.locator('#status')).to_contain_text('Choose a Python file or a folder')
