"""
analyse.py
──────────
Public entry point for the auditor. Import scan() from here.
All logic lives in: models.py · ast_helpers.py · checks.py · scanner.py
"""
from models import FileReport, Issue, SuiteReport
from scanner import scan

__all__ = ["FileReport", "Issue", "SuiteReport", "scan"]