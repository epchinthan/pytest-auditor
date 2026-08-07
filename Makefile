# ─────────────────────────────────────────────────────────────────────────────
# pytest-auditor — Makefile
# ─────────────────────────────────────────────────────────────────────────────

PYTHON  ?= python3
TESTS   ?= tests
HTML    ?= pytest_audit.html
SCORE   ?= 80

HERE := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

.PHONY: audit audit-strict install check help

help:
	@echo ""
	@echo "  make audit                    scan \$$TESTS → \$$HTML"
	@echo "  make audit TESTS=src/tests    custom path"
	@echo "  make audit HTML=out.html      custom output"
	@echo "  make audit-strict             fail if score < \$$SCORE"
	@echo "  make audit-strict SCORE=90    custom threshold"
	@echo "  make check                    verify setup is correct"
	@echo ""

# Print what the Makefile can see — useful for debugging
check:
	@echo "Makefile is at  : $(HERE)/Makefile"
	@echo "Looking for     : $(HERE)/pytest_auditor/__main__.py"
	@if [ -f "$(HERE)/pytest_auditor/__main__.py" ]; then \
		echo "Status          : OK — pytest_auditor/ found"; \
	else \
		echo "Status          : MISSING — pytest_auditor/ not found here"; \
		echo ""; \
		echo "Contents of $(HERE):"; \
		ls "$(HERE)"; \
	fi

install:
	@$(PYTHON) -m pip install rich --quiet --disable-pip-version-check 2>/dev/null || \
	 $(PYTHON) -m pip install rich --quiet --break-system-packages 2>/dev/null || \
	 echo "  note: could not install rich — run: pip install rich"

audit: install
	@if [ ! -f "$(HERE)/pytest_auditor/__main__.py" ]; then \
		echo ""; \
		echo "  Error: pytest_auditor/ not found in $(HERE)"; \
		echo ""; \
		echo "  Expected structure:"; \
		echo "    $(HERE)/Makefile"; \
		echo "    $(HERE)/pytest_auditor/__init__.py"; \
		echo "    $(HERE)/pytest_auditor/__main__.py"; \
		echo "    $(HERE)/pytest_auditor/analyse.py"; \
		echo "    $(HERE)/pytest_auditor/terminal.py"; \
		echo "    $(HERE)/pytest_auditor/html_report.py"; \
		echo ""; \
		echo "  Currently in $(HERE):"; \
		ls "$(HERE)"; \
		echo ""; \
		exit 1; \
	fi
	$(PYTHON) -c "\
import sys; sys.path.insert(0, '$(HERE)'); \
from pytest_auditor.__main__ import main; \
sys.exit(main(['$(abspath $(TESTS))', '--html', '$(abspath $(HTML))']))"

audit-strict: install
	@if [ ! -f "$(HERE)/pytest_auditor/__main__.py" ]; then \
		echo "Error: pytest_auditor/ not found. Run 'make check' for details."; \
		exit 1; \
	fi
	$(PYTHON) -c "\
import sys; sys.path.insert(0, '$(HERE)'); \
from pytest_auditor.__main__ import main; \
sys.exit(main(['$(abspath $(TESTS))', '--html', '$(abspath $(HTML))', '--fail-under', '$(SCORE)']))"