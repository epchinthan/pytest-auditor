"""
scanner.py
──────────
Re-exports all public scan functions. Import from here.

Scanning is split across focused modules:
  config.py        — read_config, read_coverage, is_excluded, collect_conftest_fixtures
  file_analyzer.py — analyse_file (one file → FileReport)
  suite_scanner.py — scan (full directory → SuiteReport)
  targeted.py      — scan_file, scan_test (focused audits)
"""
from reporting.config import (
    collect_conftest_fixtures,
    is_excluded,
    read_config,
    read_coverage,
)

from scanning.file_analyzer import analyse_file
from scanning.suite_scanner import scan
from scanning.targeted import scan_file, scan_test

__all__ = [
    "analyse_file",
    "collect_conftest_fixtures",
    "is_excluded",
    "read_config",
    "read_coverage",
    "scan",
    "scan_file",
    "scan_test",
]