"""Local browsing and bounded GitHub source downloads."""
import io
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from core.models import EXCLUDE_DIRS

MAX_ARCHIVE = 50 * 1024 * 1024
MAX_EXTRACTED = 150 * 1024 * 1024


def browse(path):
    root = Path(path or Path.home()).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('Choose an existing directory.')
    entries = []
    for child in root.iterdir():
        if child.name in EXCLUDE_DIRS or child.name.startswith('.'):
            continue
        try:
            if child.is_dir() or child.suffix == '.py':
                entries.append({'name': child.name, 'path': str(child), 'directory': child.is_dir()})
        except OSError:
            continue
    entries.sort(key=lambda e: (not e['directory'], e['name'].lower()))
    return {'path': str(root), 'parent': str(root.parent), 'entries': entries}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def repository_name(value):
    value = value.strip().rstrip('/')
    if value.startswith('https://github.com/'):
        value = value[len('https://github.com/'):]
    value = value.removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value):
        raise ValueError('Enter owner/repository or a https://github.com/owner/repository URL.')
    return value


def download_repository(repository, ref, token):
    url = f'https://api.github.com/repos/{repository}/zipball'
    if ref:
        url += '/' + quote(ref, safe='')
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'pytest-auditor'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        try:
            response = build_opener(NoRedirect()).open(Request(url, headers=headers), timeout=30)
        except HTTPError as error:
            if error.code != 302:
                raise
            location = error.headers.get('Location', '')
            target = urlsplit(location)
            if target.scheme != 'https' or target.hostname != 'codeload.github.com':
                raise ValueError('GitHub returned an unexpected download location.')
            # The signed redirect authorizes private archives; never forward the token.
            response = urlopen(Request(location, headers={'User-Agent': 'pytest-auditor'}), timeout=30)
        with response:
            data = response.read(MAX_ARCHIVE + 1)
        if len(data) > MAX_ARCHIVE:
            raise ValueError('Repository archive exceeds the 50 MB download limit.')
        return data
    except HTTPError as error:
        raise ValueError(f'GitHub request failed ({error.code}). Check the repository, ref, token access, or rate limit.') from None
    except (URLError, TimeoutError):
        raise ValueError('Could not download from GitHub. Check your connection and try again.') from None


def extract_repository(data, destination):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError('GitHub did not return a valid ZIP archive.') from None
    with archive:
        members = archive.infolist()
        if len(members) > 20000 or sum(m.file_size for m in members) > MAX_EXTRACTED:
            raise ValueError('Repository exceeds the extraction limit (150 MB / 20,000 entries).')
        roots = set()
        for member in members:
            path = PurePosixPath(member.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in member.filename:
                raise ValueError('Unsafe path in repository archive.')
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError('Repository archive contains unsupported symbolic links.')
            if not path.parts:
                continue
            roots.add(path.parts[0])
            target = destination.joinpath(*path.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
        if len(roots) != 1:
            raise ValueError('Expected one repository root in the archive.')
        root = destination / roots.pop()
        if not root.is_dir():
            raise ValueError('Archive has no repository directory.')
        return root
