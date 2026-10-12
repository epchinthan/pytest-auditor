"""Direct audit requests: scan modes, validation, thresholds, and checkout lifecycle."""
import pytest

import web_server
from web_server import audit


# Exercise the audit callable directly; HTTP protocol behavior lives in test_http_endpoints.py.
@pytest.mark.parametrize('mode', ['suite', 'file', 'test'])
def test_audit_modes_return_counts_and_threshold_outcome(mode, example_test_file):
    result = audit({'mode': mode, 'path': str(example_test_file.parent if mode == 'suite' else example_test_file),
                    'test': 'test_placeholder', 'fail_under': 100})
    assert result['report']['total_tests'] == (1 if mode == 'test' else 2)
    assert not result['passed']


# Each invalid request should identify its specific cause, not merely raise any error.
@pytest.mark.parametrize('case,message', [
    ('missing-path', 'existing local path'),
    ('directory-as-file', 'Python file'),
    ('missing-test', 'not found'),
    ('missing-test-name', 'test function name'),
    ('bad-threshold', 'integer from 0 to 100'),
    ('unknown-mode', 'Choose suite'),
    ('unknown-source', 'Choose local'),
])
def test_invalid_audit_requests_explain_the_cause(case, message, example_test_file, tmp_path):
    overrides = {
        'missing-path': {'path': str(tmp_path / 'missing')},
        'directory-as-file': {'path': str(tmp_path)},
        'missing-test': {'mode': 'test', 'test': 'test_missing'},
        'missing-test-name': {'mode': 'test'},
        'bad-threshold': {'fail_under': 101},
        'unknown-mode': {'mode': 'unknown'},
        'unknown-source': {'source': 'unknown'},
    }
    with pytest.raises(ValueError, match=message):
        audit({'path': str(example_test_file), 'mode': 'file', **overrides[case]})


# A score exactly equal to the minimum passes; one point above it fails.
@pytest.mark.parametrize('offset,passed', [(-1, True), (0, True), (1, False)],
                         ids=['below-score', 'equal-score', 'above-score'])
def test_threshold_boundary(offset, passed, example_test_file):
    payload = {'path': str(example_test_file), 'mode': 'file'}
    score = audit(payload)['report']['score']
    assert audit({**payload, 'fail_under': score + offset})['passed'] == passed


# Stub only the download, then inspect the real extraction directory after the audit finishes.
@pytest.mark.parametrize('mode', ['suite', 'file', 'test'])
def test_github_audit_removes_temporary_checkout(mode, zip_archive, example_test_file, monkeypatch):
    data = zip_archive({'repo-sha/tests/test_example.py': example_test_file.read_text()})
    downloads, directories = [], []
    extract = web_server.extract_repository

    def download(repository, ref, token):
        downloads.append((repository, ref, token))
        return data

    def record_extraction(data, destination):
        directories.append(destination)
        return extract(data, destination)

    monkeypatch.setattr(web_server, 'download_repository', download)
    monkeypatch.setattr(web_server, 'extract_repository', record_extraction)
    result = audit({'source': 'github', 'repository': 'https://github.com/example/repo.git',
                    'ref': 'feature/tests', 'mode': mode, 'test': 'test_placeholder',
                    'path': 'tests' if mode == 'suite' else 'tests/test_example.py'})
    assert result['report']['total_tests'] == (1 if mode == 'test' else 2)
    assert downloads == [('example/repo', 'feature/tests', '')]
    assert len(directories) == 1
    assert not directories[0].exists()


# Cleanup must also run when repository-relative path validation raises an error.
def test_rejected_github_path_also_removes_checkout(zip_archive, monkeypatch):
    data = zip_archive({'repo-sha/test_example.py': 'def test_example():\n    assert True\n'})
    destinations = []
    extract = web_server.extract_repository

    def record_extraction(data, destination):
        destinations.append(destination)
        return extract(data, destination)

    monkeypatch.setattr(web_server, 'download_repository', lambda *args: data)
    monkeypatch.setattr(web_server, 'extract_repository', record_extraction)
    with pytest.raises(ValueError, match='inside'):
        audit({'source': 'github', 'repository': 'example/repo', 'path': '../escape'})
    assert len(destinations) == 1
    assert not destinations[0].exists()


def test_github_report_uses_repository_paths(zip_archive, example_test_file, monkeypatch):
    data = zip_archive({'repo-sha/tests/test_example.py': example_test_file.read_text()})
    monkeypatch.setattr(web_server, 'download_repository', lambda *args: data)
    result = audit({'source': 'github', 'repository': 'example/repo', 'ref': 'feature/tests'})
    assert result['report']['root'].startswith('github:example/repo@feature/tests')
    assert 'pytest-auditor-github-' not in result['html']
