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
	@echo "  make audit TESTS=~/my/tests   ~ paths work too"
	@echo "  make audit HTML=out.html      custom output path"
	@echo "  make audit-strict             fail if score < \$$SCORE"
	@echo "  make audit-strict SCORE=90    custom threshold"
	@echo ""

install:
	@$(PYTHON) -c "import rich" 2>/dev/null \
	|| $(PYTHON) -m pip install rich --quiet --disable-pip-version-check 2>/dev/null \
	|| $(PYTHON) -m pip install rich --quiet --break-system-packages 2>/dev/null \
	|| $(PYTHON) -m pip install rich --quiet --user 2>/dev/null \
	|| echo "  warning: could not install rich. Run: pip install rich"

audit: install
	@echo "  Python   : $(PYTHON)"
	@echo "  HERE     : $(HERE)"
	@echo "  TESTS    : $(TESTS)"
	@echo "  HTML     : $(HTML)"
	@TESTS_ABS=$$($(PYTHON) -c "import os; print(os.path.abspath(os.path.expanduser('$(TESTS)')))") && \
	 HTML_ABS=$$($(PYTHON) -c "import os; print(os.path.abspath(os.path.expanduser('$(HTML)')))") && \
	 echo "  TESTS_ABS: $$TESTS_ABS" && \
	 echo "  HTML_ABS : $$HTML_ABS" && \
	 echo "" && \
	 $(PYTHON) "$(HERE)/__main__.py" "$$TESTS_ABS" --html "$$HTML_ABS"

audit-strict: install
	@TESTS_ABS=$$($(PYTHON) -c "import os; print(os.path.abspath(os.path.expanduser('$(TESTS)')))") && \
	 HTML_ABS=$$($(PYTHON) -c "import os; print(os.path.abspath(os.path.expanduser('$(HTML)')))") && \
	 $(PYTHON) "$(HERE)/__main__.py" "$$TESTS_ABS" --html "$$HTML_ABS" --fail-under $(SCORE)