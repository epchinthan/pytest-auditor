"""Real HTTP routes: assets, authentication, malformed bodies, and API responses."""
import pytest


# Public assets do not require a session token, but must retain safe content headers.
@pytest.mark.parametrize('path,content_type', [
    ('/', 'text/html'), ('/app.js', 'text/javascript'),
    ('/issue-sort.js', 'text/javascript'), ('/style.css', 'text/css'),
])
def test_http_serves_assets(http_client, path, content_type):
    status, body, headers = http_client('GET', path, authenticated=False)
    assert status == 200
    assert body
    assert headers['Content-Type'].startswith(content_type)
    assert headers['X-Content-Type-Options'] == 'nosniff'


# Filesystem-reading POST routes require the token returned by the session endpoint.
@pytest.mark.parametrize('path', ['/api/audit', '/api/browse'])
def test_http_actions_require_session_token(http_client, path, example_test_file):
    status, body, _ = http_client('POST', path, {'path': str(example_test_file)}, authenticated=False)
    assert status == 403
    assert 'Invalid session' in body['error']


# Send raw bodies so validation is exercised before any scanner code runs.
@pytest.mark.parametrize('raw,message', [
    ('not-json', 'Expecting value'),
    ('[]', 'Expected an audit request'),
    ('', 'too large or empty'),
    ('x' * 16385, 'too large or empty'),
], ids=['malformed-json', 'wrong-shape', 'empty-body', 'oversized-body'])
def test_http_rejects_malformed_requests(http_client, raw, message):
    status, body, _ = http_client('POST', '/api/audit', raw=raw)
    assert status == 400
    assert message in body['error']


# The HTTP response must contain actual scanner findings, not a mocked success payload.
def test_http_audit_uses_real_scanner(http_client, example_test_file):
    status, result, _ = http_client('POST', '/api/audit', {'path': str(example_test_file), 'mode': 'file'})
    assert status == 200
    assert result['report']['total_tests'] == 2
    assert any(issue['code'] == 'T019' for file in result['report']['files'] for issue in file['issues'])


# The folder picker and audit endpoint share authentication but return different data.
def test_http_folder_picker_lists_local_files(http_client, example_test_file):
    status, body, _ = http_client('POST', '/api/browse', {'path': str(example_test_file.parent)})
    assert status == 200
    assert body['entries'] == [{'name': example_test_file.name, 'path': str(example_test_file), 'directory': False}]


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_http_unknown_routes_return_not_found(http_client, method):
    status, body, _ = http_client(method, '/missing')
    assert status == 404
    assert body['error'] == 'Not found'
