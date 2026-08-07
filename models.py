"""
models.py
─────────
Shared dataclasses, constants, and type aliases used across the auditor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── issue levels ──────────────────────────────────────────────────────────────

ERROR   = "error"
WARNING = "warning"
INFO    = "info"


# ── data models ───────────────────────────────────────────────────────────────

@dataclass
class Issue:
    """A single quality issue found in a test file."""
    level:   str   # ERROR | WARNING | INFO
    code:    str   # e.g. "T001"
    message: str
    file:    str
    line:    int = 0


@dataclass
class FileReport:
    """Audit results for one test file."""
    path:          str
    test_count:    int = 0
    class_count:   int = 0
    fixture_count: int = 0
    async_count:   int = 0
    line_count:    int = 0
    issues:        list[Issue] = field(default_factory=list)
    tests:         list[dict]  = field(default_factory=list)
    fixtures:      list[dict]  = field(default_factory=list)


@dataclass
class SuiteReport:
    """Full audit results for a test suite."""
    root:              str
    generated_at:      str
    files:             list[FileReport] = field(default_factory=list)
    registered_marks:  list[str]        = field(default_factory=list)
    conftest_paths:    list[str]        = field(default_factory=list)
    coverage_pct:      float | None     = None
    coverage_missing:  list[str]        = field(default_factory=list)
    # aggregates
    total_tests:       int   = 0
    total_fixtures:    int   = 0
    total_files:       int   = 0
    total_issues:      int   = 0
    errors:            int   = 0
    warnings:          int   = 0
    infos:             int   = 0
    score:             int   = 100
    # metrics
    skip_count:        int   = 0
    xfail_count:       int   = 0
    async_count:       int   = 0
    test_debt_pct:     float = 0.0
    isolation_score:   float = 0.0
    dir_breakdown:     dict  = field(default_factory=dict)


# ── shared constants ──────────────────────────────────────────────────────────

SCOPE_ORDER = {"function": 0, "class": 1, "module": 2, "session": 3}

BUILTIN_MARKS = {
    "slow", "skip", "skipif", "xfail", "parametrize",
    "usefixtures", "filterwarnings", "asyncio", "anyio",
    "smoke", "integration", "unit", "e2e",
}

PYTHON_BUILTINS = {
    "id", "type", "list", "dict", "set", "tuple", "str", "int",
    "float", "bool", "bytes", "range", "map", "filter", "zip",
    "len", "min", "max", "sum", "sorted", "reversed", "open",
    "print", "input", "format", "vars", "dir", "hash",
}

EXCLUDE_DIRS = {
    ".venv", "venv", ".env", "env",
    ".tox", ".nox",
    "node_modules",
    ".git", ".hg", ".svn",
    "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "build", "dist",
    ".eggs", "htmlcov", "site-packages",
}

VAGUE_NAMES = re.compile(
    r"^test_(it|this|thing|run|go|do|check|a|b|c|1|2|3|temp|tmp|foo|bar|baz|x|y|z)$",
    re.IGNORECASE,
)

NUMBERED_NAMES = re.compile(r"^test_.*\d+$")

CREDENTIAL_PATTERN = re.compile(
    r"(password|passwd|token|api_key|apikey|secret|auth|credential)\s*=\s*[\"'][^\"']{4,}[\"']",
    re.IGNORECASE,
)