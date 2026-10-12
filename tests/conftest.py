"""Isolated source files, archive data, and a real local HTTP server for tests."""
import io
import json
import secrets
import textwrap
import threading
import zipfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from scanning.scanner import scan, scan_file, scan_test
from web_server import Handler


@pytest.fixture
def write_test_file(tmp_path):
    """Write source data under tmp_path, with consistent indentation and line endings."""
    def write(source, name='test_example.py'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).strip() + '\n', encoding='utf-8')
        return path

    return write


@pytest.fixture
def scan_source(write_test_file):
    """Audit a source snippet through the real scanner without executing its tests."""
    def analyze(source, mode='file', test_name='test_checkout'):
        path = write_test_file(source)
        if mode == 'suite':
            return scan(path.parent)
        if mode == 'test':
            return scan_test(path, test_name)
        return scan_file(path)

    return analyze


@pytest.fixture
def example_test_file(write_test_file):
    """Provide two known tests: one intentional warning and one meaningful assertion."""
    return write_test_file('''
        def test_placeholder():
            assert True

        def test_sum():
            assert 1 + 1 == 2
    ''')


@pytest.fixture
def zip_archive():
    """Build in-memory ZIP data, including custom ZipInfo entries for safety regressions."""
    def build(files):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return data.getvalue()

    return build


@pytest.fixture(scope='session')
def app_url():
    """Share a loopback server on an OS-assigned port and stop it after the session."""
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.token = secrets.token_urlsafe(32)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def http_client(app_url):
    """Return an HTTP client that obtains a real session token unless testing unauthenticated requests."""
    address = urlsplit(app_url)
    connection = HTTPConnection(address.hostname, address.port, timeout=5)

    def request(method, path, payload=None, *, raw=None, authenticated=True):
        # raw bypasses JSON encoding for malformed-body tests.
        headers = {}
        if authenticated:
            connection.request('GET', '/api/session')
            session = json_response(connection.getresponse())[1]
            headers['X-Audit-Token'] = session['token']
        body = raw if raw is not None else json_bytes(payload)
        if body is not None:
            headers['Content-Type'] = 'application/json'
        connection.request(method, path, body, headers)
        return json_response(connection.getresponse())

    try:
        yield request
    finally:
        connection.close()


def json_bytes(payload):
    return json.dumps(payload).encode() if payload is not None else None


def json_response(response):
    # Drain each response so the same connection can issue the next request.
    content = response.read()
    body = json.loads(content) if 'application/json' in response.getheader('Content-Type', '') else content
    return response.status, body, dict(response.getheaders())


@pytest.fixture
def browser_test_suite(tmp_path):
    """Create predictable error, warning, and info findings for browser sorting assertions."""
    root = tmp_path / 'sample_tests'
    root.mkdir()
    # Avoid incidental package/mark warnings so browser tests assert just three known findings.
    (root / '__init__.py').write_text('')
    (root / 'conftest.py').write_text('')
    (root / 'test_alpha.py').write_text(
        'import pytest\n@pytest.mark.unit\ndef test_missing_verification():\n    value = 42\n'
    )
    (root / 'test_beta.py').write_text(
        'import pytest\n@pytest.mark.unit\ndef test_placeholder():\n    print("debug")\n    assert True\n'
    )
    return root
