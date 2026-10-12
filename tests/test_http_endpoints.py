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
@pytest.mark.parametrize('path', ['/api/audit', '/api/browse', '/api/upload'])
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


def upload_file(path, content):
    import base64
    return {'path': path, 'content': base64.b64encode(content.encode()).decode()}


@pytest.fixture(params=[False, True], ids=['file', 'folder'])
def uploaded_source(http_client, monkeypatch, request):
    folder = request.param
    import web_server
    original = web_server.audit
    targets = []
    def recording_audit(payload):
        targets.append(web_server.Path(payload['path']))
        return original(payload)
    monkeypatch.setattr(web_server, 'audit', recording_audit)
    path = 'suite/tests/test_uploaded.py' if folder else 'test_uploaded.py'
    files = [upload_file(path, 'def test_uploaded():\n    assert True\n')]
    if folder:
        files.append(upload_file('suite/pytest.ini', '[pytest]\n'))
    status, result, _ = http_client('POST', '/api/upload', {'files': files, 'folder': folder})
    return status, result, targets


def test_upload_runs_real_scanner(uploaded_source):
    status, result, _ = uploaded_source
    assert status == 200, result
    assert result['report']['total_tests'] == 1
    assert any(i['code'] == 'T019' for f in result['report']['files'] for i in f['issues'])
    assert 'test_uploaded.py' in result['html']


def test_upload_removes_temporary_files_and_normalizes_paths(uploaded_source):
    status, result, targets = uploaded_source
    assert status == 200, result
    assert all(not target.exists() for target in targets)
    assert 'pytest-auditor-upload-' not in str(result)


@pytest.mark.parametrize('path', ['../test_escape.py', '/test_escape.py', 'a/../../test_escape.py', 'a\\test_escape.py', 'C:/test_escape.py'])
def test_upload_rejects_unsafe_paths(http_client, path):
    status, result, _ = http_client('POST', '/api/upload', {'files': [upload_file(path, '')]})
    assert status == 400
    assert 'Unsafe upload path' in result['error']


@pytest.mark.parametrize('payload', [
    {'files': []},
    {'files': [{'path':'test_bad.py', 'content':'!invalid!'}]},
    {'files': [upload_file('secrets.txt', 'secret')]},
    {'folder': True, 'files': [upload_file('test_a.py', ''), upload_file('test_a.py', '')]},
])
def test_upload_rejects_invalid_files(http_client, payload):
    status, _, _ = http_client('POST', '/api/upload', payload)
    assert status == 400


def test_upload_applies_total_size_limit(http_client, monkeypatch):
    import web_server
    monkeypatch.setattr(web_server, 'MAX_UPLOAD', 4)
    status, result, _ = http_client('POST', '/api/upload', {'files': [upload_file('test_large.py', '12345')]})
    assert status == 400
    assert '10 MB limit' in result['error']
