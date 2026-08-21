"""
config.py
─────────
Reads project configuration (pyproject.toml / pytest.ini),
coverage data (coverage.json), and conftest fixture definitions.
Also owns the path exclusion filter.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from core import ast_helpers as h
from core.models import EXCLUDE_DIRS

# ── path filtering ────────────────────────────────────────────────────────────

def is_excluded(path: Path) -> bool:
    """True if the path lives inside a directory that should never be scanned."""
    return any(
        part in EXCLUDE_DIRS or part.endswith(".egg-info")
        for part in path.parts
    )


# ── config reader ─────────────────────────────────────────────────────────────

def read_config(root: Path) -> tuple[list[str], list[str]]:
    """Return (registered_marks, testpaths) from pyproject.toml or pytest.ini."""
    marks: list[str] = []
    paths: list[str] = []

    # A user may audit a nested test directory (for example tests/test_suites),
    # while pytest.ini lives at the repository root. Walk upwards just as
    # pytest does when discovering its configuration instead of checking only
    # the immediate parent.
    search_roots = (root, *root.parents)

    config_path: Path | None = None
    for directory in search_roots:
        # pytest.ini takes precedence over pyproject.toml in the same directory.
        for name in ("pytest.ini", "pyproject.toml"):
            candidate = directory / name
            if candidate.is_file():
                config_path = candidate
                break
        if config_path:
            break

    if config_path is None:
        return marks, paths

    text = config_path.read_text(encoding="utf-8")
    if config_path.name == "pytest.ini":
        sec = re.search(r"\[pytest\](.*?)(?:^\[|\Z)", text, re.DOTALL | re.MULTILINE)
        if sec:
            marks.extend(re.findall(r"^\s+([A-Za-z_][\w.-]*)\s*:", sec.group(1), re.MULTILINE))
            testpaths = re.search(
                r"^\s*testpaths\s*=\s*(.*(?:\n[ \t]+.*)*)",
                sec.group(1), re.MULTILINE,
            )
            if testpaths:
                paths = testpaths.group(1).split()
    else:
        marker_list = re.search(r"markers\s*=\s*\[(.*?)\]", text, re.DOTALL)
        if marker_list:
            marks = re.findall(
                r'["\']\s*([A-Za-z_][\w.-]*)\s*(?::[^"\']*)?["\']',
                marker_list.group(1),
            )
        configured_paths = re.search(r"testpaths\s*=\s*\[(.*?)\]", text, re.DOTALL)
        if configured_paths:
            paths = re.findall(r'["\']([^"\']+)["\']', configured_paths.group(1))

    return marks, paths


# ── coverage reader ───────────────────────────────────────────────────────────

def read_coverage(root: Path) -> tuple[float | None, list[str]]:
    """Parse coverage.json if present. Returns (pct, list of missing line notes)."""
    for candidate in (root / "coverage.json", root.parent / "coverage.json"):
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                pct = data.get("totals", {}).get("percent_covered")
                missing = [
                    f"{fn}: lines {','.join(str(ln) for ln in fd.get('missing_lines', [])[:5])}"
                    for fn, fd in data.get("files", {}).items()
                    if fd.get("missing_lines")
                ][:10]
                return pct, missing
            except (OSError, KeyError, ValueError, json.JSONDecodeError):
                pass

    return None, []


# ── conftest fixture collector ────────────────────────────────────────────────

def collect_conftest_fixtures(conftest_path: Path) -> dict[str, str]:
    """Return {fixture_name: scope} for all fixtures defined in a conftest.py."""
    result: dict[str, str] = {}
    try:
        tree = ast.parse(conftest_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if h.is_fixture(node):
                result[node.name] = h.fixture_scope(node)
    except (SyntaxError, OSError, UnicodeDecodeError):
        pass
    return result
