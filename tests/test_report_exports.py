"""Readable findings, paths, and exported reports across all audit modes."""
import pytest

from web_server import audit


# Check exported data in every scan mode, including fixture/debt aggregation.
@pytest.mark.parametrize('mode', ['suite', 'file', 'test'])
def test_finding_guidance_and_debt_metrics_are_exported(write_test_file, mode):
    path = write_test_file('''
        import pytest

        @pytest.mark.skip(reason="pending")
        def test_checkout():
            assert True
    ''')
    result = audit({'path': str(path.parent if mode == 'suite' else path),
                    'mode': mode, 'test': 'test_checkout'})
    report = result['report']
    issue = next(issue for file in report['files'] for issue in file['issues'] if issue['code'] == 'T019')
    assert report['test_debt_pct'] == 100
    assert report['score_breakdown']['deductions']['Test debt'] == 5
    assert 'regression' in issue['explanation']
    assert 'placeholder' in issue['suggestion']


# Standalone HTML must retain the explanations shown in the live web UI.
def test_html_contains_guidance_and_score_breakdown(example_test_file):
    html = audit({'path': str(example_test_file), 'mode': 'file'})['html']
    assert 'How this score is calculated' in html
    assert 'Why this matters' in html
    assert 'Suggested fix:' in html
    assert 'Replace the placeholder' in html


# Suite scans anchor paths at the selected folder; focused scans use the file’s parent.
@pytest.mark.parametrize('mode,expected', [
    ('suite', 'tests/orders/test_checkout.py'),
    ('file', 'orders/test_checkout.py'),
    ('test', 'orders/test_checkout.py'),
])
def test_file_columns_begin_with_selected_folder(write_test_file, mode, expected):
    path = write_test_file('def test_checkout():\n    assert True', name='tests/orders/test_checkout.py')
    selected = path.parent.parent if mode == 'suite' else path
    result = audit({'path': str(selected), 'mode': mode, 'test': 'test_checkout'})
    assert result['path_labels'][str(path)] == expected
    assert f'>{expected}:1</code>' in result['html']
    assert f'>{path}</code>' not in result['html']


# Verify the user-facing empty state as well as the underlying scoring status.
def test_empty_report_is_unassessed_and_cannot_pass_a_zero_threshold(tmp_path):
    result = audit({'path': str(tmp_path), 'fail_under': 0})
    assert result['report']['score'] is None
    assert result['report']['score_breakdown']['deductions'] == {}
    assert not result['passed']
    assert '<div class="score-num">—</div>' in result['html']
    assert 'Not assessed' in result['html']


def test_categories_are_exported_with_original_rule_codes(example_test_file):
    result = audit({'path': str(example_test_file), 'mode': 'file'})
    issue = next(i for f in result['report']['files'] for i in f['issues'] if i['code'] == 'T019')
    assert issue['category'] == 'Assertions & verification'
    assert 'Assertions &amp; verification' in result['html']
    assert '<th>Rule code</th>' not in result['html']
    assert 'data-category="Assertions &amp; verification"' in result['html']
