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

    for candidate in (root / "pyproject.toml", root.parent / "pyproject.toml"):
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            m = re.search(r"markers\s*=\s*\[(.*?)\]", text, re.DOTALL)
            if m:
                marks = re.findall(r'["\'](\w+)["\']', m.group(1))
            m2 = re.search(r"testpaths\s*=\s*\[(.*?)\]", text, re.DOTALL)
            if m2:
                paths = re.findall(r'["\']([^"\']+)["\']', m2.group(1))
            break

    for candidate in (root / "pytest.ini", root.parent / "pytest.ini"):
        if candidate.exists() and not marks:
            text = candidate.read_text(encoding="utf-8")
            sec = re.search(r"\[pytest\](.*?)(?:\[|$)", text, re.DOTALL)
            if sec:
                marks.extend(re.findall(r"^\s+(\w+):", sec.group(1), re.MULTILINE))
            break

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