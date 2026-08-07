# ─────────────────────────────────────────────────────────────────────────────
# pytest-auditor — Makefile
#
# Usage:
#   make audit                  scan ./tests → pytest_audit.html
#   make audit TESTS=src/tests  custom path
#   make audit-strict           fail if score < 80
#   make install                install dependencies only
# ─────────────────────────────────────────────────────────────────────────────

PYTHON  ?= python3
TESTS   ?= tests
HTML    ?= pytest_audit.html
SCORE   ?= 80

.PHONY: audit audit-strict install help

# Default target
help:
	@echo ""
	@echo "  pytest-auditor"
	@echo ""
	@echo "  make audit                   scan \$$TESTS → \$$HTML"
	@echo "  make audit TESTS=src/tests   custom tests path"
	@echo "  make audit HTML=out.html     custom output path"
	@echo "  make audit-strict            fail if score < \$$SCORE (default: 80)"
	@echo "  make audit-strict SCORE=90   custom threshold"
	@echo "  make install                 install dependencies only"
	@echo ""

install:
	$(PYTHON) -m pip install rich --quiet --disable-pip-version-check 2>/dev/null || \
	$(PYTHON) -m pip install rich --quiet --break-system-packages 2>/dev/null || true

audit: install
	$(PYTHON) -m pytest_auditor $(TESTS) --html $(HTML)

audit-strict: install
	$(PYTHON) -m pytest_auditor $(TESTS) --html $(HTML) --fail-under $(SCORE)