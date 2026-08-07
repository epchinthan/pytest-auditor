# ─────────────────────────────────────────────────────────────────────────────
# pytest-auditor — Makefile
# ─────────────────────────────────────────────────────────────────────────────

PYTHON  ?= python3
TESTS   ?= tests
HTML    ?= pytest_audit.html
SCORE   ?= 80

HERE := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

.PHONY: audit audit-strict install help

help:
	@echo ""
	@echo "  make audit                    scan \$$TESTS → \$$HTML"
	@echo "  make audit TESTS=src/tests    custom path"
	@echo "  make audit HTML=out.html      custom output"
	@echo "  make audit-strict             fail if score < \$$SCORE"
	@echo "  make audit-strict SCORE=90    custom threshold"
	@echo ""

install:
	@$(PYTHON) -m pip install rich --quiet --disable-pip-version-check 2>/dev/null || \
	 $(PYTHON) -m pip install rich --quiet --break-system-packages 2>/dev/null || \
	 echo "  note: could not install rich — run: pip install rich"

audit: install
	$(PYTHON) -c "\
import sys; sys.path.insert(0, '$(HERE)'); \
from pytest_auditor.__main__ import main; \
sys.exit(main(['$(abspath $(TESTS))', '--html', '$(abspath $(HTML))']))"

audit-strict: install
	$(PYTHON) -c "\
import sys; sys.path.insert(0, '$(HERE)'); \
from pytest_auditor.__main__ import main; \
sys.exit(main(['$(abspath $(TESTS))', '--html', '$(abspath $(HTML))', '--fail-under', '$(SCORE)']))"