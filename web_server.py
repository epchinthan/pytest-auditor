"""Loopback web interface for the existing static auditor (stdlib only)."""
from __future__ import annotations

import argparse
import json
import secrets
import tempfile
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from web_sources import browse, download_repository, extract_repository, repository_name

from reporting.html_report import generate_html
from reporting.paths import display_path
from scanning.scanner import scan, scan_file, scan_test

ASSETS = Path(__file__).parent / 'web'


def audit(payload):
    source = payload.get("source", "local")
    if source == "github":
        repository = repository_name(payload.get("repository", ""))
        ref = payload.get("ref", "").strip()
        data = download_repository(repository, ref, payload.get("github_token", "").strip())
        with tempfile.TemporaryDirectory(prefix="pytest-auditor-github-") as directory:
            root = extract_repository(data, Path(directory))
            relative = payload.get("path", "").strip() or "."
            target = (root / relative).resolve()
            if not target.is_relative_to(root):
                raise ValueError("Audit path must stay inside the repository.")
            local = dict(payload, source="local", path=str(target),
                         _folder_name=repository.split("/")[1] if target == root else None)
            result = audit(local)
            prefix = str(root)
            label = f"github:{repository}@{ref or 'default'}"
            def normalize(value):
                if isinstance(value, str):
                    return value.replace(prefix, label)
                if isinstance(value, list):
                    return [normalize(item) for item in value]
                if isinstance(value, dict):
                    return {normalize(key): normalize(item) for key, item in value.items()}
                return value
            return normalize(result)
    if source != "local":
        raise ValueError("Choose local or GitHub source.")
    mode = payload.get('mode', 'suite')
    if mode not in {'suite', 'file', 'test'}:
        raise ValueError('Choose suite, file, or test mode.')
    path = Path(payload.get('path', '')).expanduser().resolve()
    if not payload.get('path') or not path.exists():
        raise ValueError('Enter an existing local path.')
    threshold = payload.get('fail_under', 0)
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 100:
        raise ValueError('Score threshold must be an integer from 0 to 100.')
    if mode != 'suite' and (not path.is_file() or path.suffix != '.py'):
        raise ValueError('File and test modes require a Python file.')
    if mode == 'test':
        name = payload.get('test', '').strip()
        if not name:
            raise ValueError('Enter a test function name.')
        report = scan_test(path, name)
    else:
        report = scan_file(path) if path.is_file() else scan(path)
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / 'report.html'
        generate_html(report, output, payload.get("_folder_name"))
        html = output.read_text(encoding='utf-8')
    locations = {f.path for f in report.files} | {i.file for f in report.files for i in f.issues}
    labels = {p: display_path(p, report.root, payload.get('_folder_name')) for p in locations}
    return {'report': asdict(report), 'html': html, 'path_labels': labels, 'threshold': threshold,
            'passed': report.total_tests > 0 and report.score >= threshold}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, kind='application/json'):
        data = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/session':
            return self.respond(200, json.dumps({'token': self.server.token}))
        assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                  '/style.css': ('style.css', 'text/css'),
                  '/issue-sort.js': ('../reporting/issue_sort.js', 'text/javascript')}
        if path not in assets:
            return self.respond(404, json.dumps({'error': 'Not found'}))
        name, kind = assets[path]
        self.respond(200, (ASSETS / name).read_text(encoding='utf-8'), kind)

    def do_POST(self):
        if self.path not in {'/api/audit', '/api/browse'}:
            return self.respond(404, json.dumps({'error': 'Not found'}))
        if self.headers.get('X-Audit-Token') != self.server.token:
            return self.respond(403, json.dumps({'error': 'Invalid session. Reload the page.'}))
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 16384:
                raise ValueError('Request is too large or empty.')
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('Expected an audit request.')
            result = browse(payload.get('path', '')) if self.path == '/api/browse' else audit(payload)
        except (ValueError, OSError, TypeError, AttributeError) as error:
            return self.respond(400, json.dumps({'error': str(error)}))
        except Exception:
            return self.respond(500, json.dumps({'error': 'Audit failed. Check the server terminal for details.'}))
        self.respond(200, json.dumps(result))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Start the local pytest-auditor web UI')
    parser.add_argument('--port', type=int, default=6767)
    parser.add_argument('--host', default='127.0.0.1', help='Bind address (default: loopback)')
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.token = secrets.token_urlsafe(32)
    print(f'pytest-auditor web UI: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
