"""Page objects for the audit UI and its downloadable HTML report."""
from pathlib import Path

from playwright.sync_api import Download, Page


class AuditPage:
    def __init__(self, page: Page):
        self.page = page
        self.path = page.locator('#path')
        self.status = page.locator('#status')
        self.run_button = page.get_by_role('button', name='Run audit')
        self.audit_scope = page.get_by_label('Audit scope')
        self.test_function = page.get_by_label('Test function')
        self.test_count = page.locator('#metrics .metric').nth(1).locator('.value')
        self.quality_score = page.locator('#metrics .metric').first.locator('.value')
        self.score_heading = page.get_by_role('heading', name='How this score is calculated')
        self.rows = page.locator('#table tbody tr')
        self.table = page.locator('#table')
        self.sort_by = page.get_by_label('Sort by', exact=True)
        self.order = page.get_by_label('Order', exact=True)
        self.severity = page.get_by_label('Severity', exact=True)
        self.search = page.get_by_label('Search results')
        self.empty_results = page.get_by_text('No results for this view or filter.')
        self.finding_details = self.rows.locator('details')
        self.results = page.locator('#results')
        self.score_breakdown = page.locator('#score-breakdown')
        self.source = page.get_by_label('Source', exact=True)
        self.repository = page.get_by_label('GitHub repository', exact=True)
        self.ref = page.get_by_label('Branch, tag, or commit')
        self.token = page.get_by_label('Token (optional for private repos)')
        self.result_title = page.locator('#result-title')
        self.minimum_score = page.get_by_label('Minimum score')
        self.score_note = page.locator('#score-note')
        self.path_fields = page.locator('#path-fields')
        self.upload_type = page.get_by_label('Upload type')
        self.upload_input = page.locator('#upload-source')
        self.upload_inputs = page.locator('#upload-fields input[type=file]')
        self.upload_selection = page.locator('#upload-selection')
        self.categories = self.rows.locator('td:nth-child(4)')
        self.first_test_path = self.rows.first.locator('td').first
        self.folder_picker = FolderPicker(page)

    def open(self, url: str):
        self.page.goto(url)

    def set_path(self, path: str | Path):
        self.path.fill(str(path))

    def run_audit(self):
        self.run_button.click()

    def show_tab(self, name: str):
        self.page.get_by_role('tab', name=name, exact=True).click()

    def issue_codes(self):
        return self.rows.evaluate_all('(rows) => rows.map(row => row.dataset.code)')

    def open_finding_explanation(self):
        self.rows.get_by_text('Why this matters · How to fix').click()

    def browse(self):
        self.page.get_by_role('button', name='Browse…').click()
        return self.folder_picker

    def upload(self, path: str | Path):
        self.upload_input.set_input_files(str(path))

    def download(self, format: str) -> Download:
        with self.page.expect_download() as event:
            self.page.get_by_role('button', name=f'Download {format}').click()
        return event.value


class FolderPicker:
    def __init__(self, page: Page):
        self.entries = page.locator('#browse-entries')
        self.path = page.locator('#browse-path')
        self.dialog = page.get_by_role('dialog')
        self.use_folder = page.get_by_role('button', name='Use this folder')

    def open_folder(self, name: str):
        self.entries.get_by_role('button', name=f'▸ {name}', exact=True).click()

    def select_file(self, name: str):
        self.entries.get_by_role('button', name=f'· {name}', exact=True).click()

    def select_folder(self):
        self.use_folder.click()


class HtmlReportPage:
    def __init__(self, page: Page):
        self.page = page
        self.sort_by = page.get_by_label('Sort by', exact=True)
        self.order = page.get_by_label('Order', exact=True)
        self.categories = page.locator('#iss-tbl tbody tr td:nth-child(3)')

    def open(self, path: Path):
        self.page.goto(path.as_uri())
