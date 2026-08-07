#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# pytest-auditor  —  run.sh
# Usage:
#   ./run.sh                  scan ./tests  →  pytest_audit.html
#   ./run.sh path/to/tests    scan a specific directory
#   ./run.sh tests --fail-under 80
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── colours ──────────────────────────────────────────────────────────────────
BOLD="\033[1m"
TEAL="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
DIM="\033[2m"
RESET="\033[0m"

banner() {
  echo ""
  echo -e "${BOLD}${TEAL}  pytest-auditor${RESET}"
  echo -e "${DIM}  Quality audit for your pytest test suite${RESET}"
  echo ""
}

info()    { echo -e "${TEAL}  →${RESET}  $*"; }
success() { echo -e "${GREEN}  ✔${RESET}  $*"; }
warn()    { echo -e "${YELLOW}  ⚠${RESET}  $*"; }
fail()    { echo -e "${RED}  ✖${RESET}  $*"; }
step()    { echo -e "\n${BOLD}$*${RESET}"; }

# ── find this script's directory ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── parse args ────────────────────────────────────────────────────────────────
TESTS_PATH="${1:-tests}"
shift 2>/dev/null || true   # remaining args passed through to the auditor
EXTRA_ARGS=("$@")

# ── banner ────────────────────────────────────────────────────────────────────
banner

# ── 1. Python check ───────────────────────────────────────────────────────────
step "[1/4]  Checking Python"

PYTHON=""
for candidate in python3 python python3.12 python3.11 python3.10; do
  if command -v "$candidate" &>/dev/null; then
    VER=$("$candidate" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)
    MAJOR=$("$candidate" -c 'import sys; print(sys.version_info.major)')
    MINOR=$("$candidate" -c 'import sys; print(sys.version_info.minor)')
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
      PYTHON="$candidate"
      success "Found $("$candidate" --version 2>&1)"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  fail "Python 3.10+ not found. Please install it and re-run."
  exit 1
fi

# ── 2. pip / venv ─────────────────────────────────────────────────────────────
step "[2/4]  Installing dependencies"

# Check if pip is available
if ! "$PYTHON" -m pip --version &>/dev/null; then
  fail "pip not found. Install pip and re-run."
  exit 1
fi

# Install rich (only dependency)
if "$PYTHON" -c "import rich" &>/dev/null 2>&1; then
  success "rich already installed"
else
  info "Installing rich..."
  "$PYTHON" -m pip install rich --quiet --disable-pip-version-check
  success "rich installed"
fi

# ── 3. verify auditor is present ─────────────────────────────────────────────
step "[3/4]  Locating pytest_auditor"

AUDITOR_DIR="$SCRIPT_DIR/pytest_auditor"

if [ ! -d "$AUDITOR_DIR" ]; then
  fail "pytest_auditor/ folder not found next to this script."
  echo ""
  echo -e "  Expected:  ${DIM}$AUDITOR_DIR/${RESET}"
  echo ""
  echo "  Make sure the folder structure is:"
  echo "    run.sh"
  echo "    pytest_auditor/"
  echo "      __init__.py"
  echo "      __main__.py"
  echo "      analyse.py"
  echo "      terminal.py"
  echo "      html_report.py"
  echo ""
  exit 1
fi

for required in __init__.py __main__.py analyse.py terminal.py html_report.py; do
  if [ ! -f "$AUDITOR_DIR/$required" ]; then
    fail "Missing: pytest_auditor/$required"
    exit 1
  fi
done

success "pytest_auditor/ found at $AUDITOR_DIR"

# ── 4. resolve tests path ─────────────────────────────────────────────────────
step "[4/4]  Running audit"

# Resolve relative to cwd, fallback to next to this script
if [ -d "$TESTS_PATH" ]; then
  TESTS_ABS="$(cd "$TESTS_PATH" && pwd)"
elif [ -d "$SCRIPT_DIR/$TESTS_PATH" ]; then
  TESTS_ABS="$(cd "$SCRIPT_DIR/$TESTS_PATH" && pwd)"
else
  fail "Tests directory not found: $TESTS_PATH"
  echo ""
  echo "  Usage:  ./run.sh [path/to/tests]  (default: ./tests)"
  echo ""
  exit 1
fi

info "Tests path : $TESTS_ABS"
info "HTML output: $(pwd)/pytest_audit.html"
echo ""

# ── run ───────────────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR"

"$PYTHON" -m pytest_auditor "$TESTS_ABS" \
  --html "$(pwd)/pytest_audit.html" \
  "${EXTRA_ARGS[@]}"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
  success "Done.  Open ${BOLD}pytest_audit.html${RESET} in your browser."
elif [ $EXIT_CODE -eq 1 ]; then
  warn "Done — score below threshold. Open ${BOLD}pytest_audit.html${RESET} for details."
else
  fail "Auditor exited with code $EXIT_CODE"
fi

echo ""
exit $EXIT_CODE