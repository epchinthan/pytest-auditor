"""GitHub URL parsing, bounded downloads, redirects, and safe ZIP extraction."""
import io
import stat
import zipfile
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

import web_sources
from web_sources import download_repository, extract_repository, repository_name




# Accept the supported shorthand and GitHub URL forms without accepting arbitrary hosts.
@pytest.mark.parametrize('value', ['example/repo', 'https://github.com/example/repo',
                                  'https://github.com/example/repo.git/', ' example/repo '])
def test_repository_urls_normalize_to_owner_and_repo(value):
    assert repository_name(value) == 'example/repo'


@pytest.mark.parametrize('value', ['https://evil.example/a/b', 'a/b/tree/main', 'a/../b', 'repo'])
def test_invalid_repository_urls_are_rejected(value):
    with pytest.raises(ValueError, match='Enter owner/repository'):
        repository_name(value)


# A successful archive establishes the extraction behavior used by the rejection cases.
def test_extract_repository_preserves_nested_files(zip_archive, tmp_path):
    root = extract_repository(zip_archive({'repo-sha/tests/test_app.py': 'content'}), tmp_path)
    assert root == tmp_path / 'repo-sha'
    assert (root / 'tests/test_app.py').read_text() == 'content'


# Reject traversal before writing anything outside or inside the destination.
@pytest.mark.parametrize('name', ['../escape.py', '/absolute.py', 'root/../../escape.py', 'root\\escape.py'])
def test_unsafe_archive_paths_are_rejected(name, zip_archive, tmp_path):
    with pytest.raises(ValueError, match='Unsafe path'):
        extract_repository(zip_archive({name: 'bad'}), tmp_path)
    assert list(tmp_path.iterdir()) == []


# ZIP metadata can encode links; the target must never be followed during extraction.
def test_archive_symlinks_are_rejected(zip_archive, tmp_path):
    link = zipfile.ZipInfo('repo-sha/link')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match='symbolic links'):
        extract_repository(zip_archive({link: '../outside'}), tmp_path)


def test_invalid_zip_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='valid ZIP'):
        extract_repository(b'not an archive', tmp_path)


def test_extraction_limit_is_checked_before_writing(zip_archive, tmp_path, monkeypatch):
    monkeypatch.setattr(web_sources, 'MAX_EXTRACTED', 3)
    with pytest.raises(ValueError, match='extraction limit'):
        extract_repository(zip_archive({'repo-sha/large.py': '1234'}), tmp_path)
    assert list(tmp_path.iterdir()) == []


# Private archive redirects are signed: only the API request should carry the user token.
def test_github_redirect_does_not_forward_token(monkeypatch):
    requests = []
    signed_url = 'https://codeload.github.com/example/repo/zip/signed'

    def api_open(request, timeout):
        requests.append(request)
        raise HTTPError(request.full_url, 302, 'Found', {'Location': signed_url}, None)

    def archive_open(request, timeout):
        requests.append(request)
        return io.BytesIO(b'archive bytes')

    monkeypatch.setattr(web_sources, 'build_opener', lambda *args: SimpleNamespace(open=api_open))
    monkeypatch.setattr(web_sources, 'urlopen', archive_open)
    data = download_repository('example/repo', 'feature/browser', 'dummy')
    assert data == b'archive bytes'
    assert requests[0].full_url.endswith('/zipball/feature%2Fbrowser')
    assert requests[0].get_header('Authorization') == 'Bearer dummy'
    assert requests[1].full_url == signed_url
    assert requests[1].get_header('Authorization') is None


def test_github_rejects_unexpected_redirect_hosts(monkeypatch):
    def api_open(request, timeout):
        raise HTTPError(request.full_url, 302, 'Found', {'Location': 'https://example.com/archive'}, None)

    monkeypatch.setattr(web_sources, 'build_opener', lambda *args: SimpleNamespace(open=api_open))
    with pytest.raises(ValueError, match='unexpected download location'):
        download_repository('example/repo', '', '')


# Network failures are simulated at the boundary, keeping tests offline and deterministic.
@pytest.mark.parametrize('error,message', [
    (HTTPError('https://api.github.com', 404, 'Not Found', {}, None), '404'),
    (URLError('offline'), 'connection'),
    (TimeoutError(), 'connection'),
], ids=['missing-repository', 'offline', 'timeout'])
def test_github_failures_have_actionable_messages(monkeypatch, error, message):
    def fail(request, timeout):
        raise error

    monkeypatch.setattr(web_sources, 'build_opener', lambda *args: SimpleNamespace(open=fail))
    with pytest.raises(ValueError, match=message):
        download_repository('example/repo', '', '')


# Use a tiny patched limit rather than allocating a production-sized archive.
def test_download_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(web_sources, 'MAX_ARCHIVE', 4)
    monkeypatch.setattr(web_sources, 'build_opener', lambda *args:
                        SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(b'12345')))
    with pytest.raises(ValueError, match='download limit'):
        download_repository('example/repo', '', '')
