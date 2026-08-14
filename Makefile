# ─────────────────────────────────────────────────────────────────────────────
# pytest-auditor — Makefile
# __main__.py lives at root. Subpackages: core/ reporting/ scanning/
# ─────────────────────────────────────────────────────────────────────────────

PYTHON  ?= python3
TESTS   ?= tests
HTML    ?= pytest_audit.html
SCORE   ?= 80

HERE := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

# Expand ~ and resolve to absolute path via Python (handles ~, ./, ../, absolute)
RESOLVE = $(PYTHON) -c "import os; print(os.path.abspath(os.path.expanduser('$(1)')))"

.PHONY: audit audit-strict install help

help:
	@echo ""
	@echo "  make audit                    scan \$$TESTS → \$$HTML"
	@echo "  make audit TESTS=src/tests    custom path"
	@echo "  make audit TESTS=~/my/tests   ~ paths work too"
	@echo "  make audit HTML=out.html      custom output path"
	@echo "  make audit-strict             fail if score < \$$SCORE"
	@echo "  make audit-strict SCORE=90    custom threshold"
	@echo ""

install:
	$(PYTHON) -m pip install rich --quiet --disable-pip-version-check 2>/dev/null || \
	$(PYTHON) -m pip install rich --quiet --break-system-packages 2>/dev/null || \
	echo "  note: could not install rich — run: pip install rich"

audit: install
	$(eval TESTS_ABS := $(shell $(call RESOLVE,$(TESTS))))
	$(eval HTML_ABS  := $(shell $(call RESOLVE,$(HTML))))
	$(PYTHON) $(HERE)/__main__.py "$(TESTS_ABS)" --html "$(HTML_ABS)"

audit-strict: install
	$(eval TESTS_ABS := $(shell $(call RESOLVE,$(TESTS))))
	$(eval HTML_ABS  := $(shell $(call RESOLVE,$(HTML))))
	$(PYTHON) $(HERE)/__main__.py "$(TESTS_ABS)" --html "$(HTML_ABS)" --fail-under $(SCORE)