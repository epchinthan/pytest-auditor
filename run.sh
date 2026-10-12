#!/usr/bin/env bash
# Bootstrap an isolated runtime environment, then run the local web application.
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$PROJECT_DIR/.venv"
ENV_PYTHON="$ENV_DIR/bin/python"
CHECK_ONLY=false

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'HELP'
Usage: ./run.sh [--check] [--port PORT]

Checks Python 3.10+, creates .venv, and installs missing runtime dependencies.
Starts the web UI at http://127.0.0.1:8765 unless --port is supplied.
--check prepares the environment without starting the server.
Stop the server with Ctrl+C.
HELP
    exit 0
fi
if [[ "${1:-}" == "--check" ]]; then
    CHECK_ONLY=true
    shift
fi

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

cd "$PROJECT_DIR"
for required in web_server.py requirements.txt web/index.html web/app.js web/style.css reporting/issue_sort.js; do
    [[ -f "$required" ]] || fail "Missing project file: $required. Restore the complete checkout."
done

# Use a supported local Python first. uv can provision one when none is available.
PYTHON_BIN=""
for candidate in "$ENV_PYTHON" python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        PYTHON_BIN="$(command -v "$candidate")"
        break
    fi
done

# Keep installer caches inside the checkout; never modify system Python packages.
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_DIR/.cache/uv}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$PROJECT_DIR/.cache/pip}"
if [[ -z "$PYTHON_BIN" ]]; then
    command -v uv >/dev/null 2>&1 || fail 'Python 3.10+ is required. Install Python or uv, then rerun ./run.sh.'
    printf 'Installing Python 3.12 with uv…\n'
    uv python install 3.12 || fail 'Could not install Python. Check your network connection and rerun.'
    PYTHON_BIN="$(uv python find 3.12)"
fi
printf 'Checking runtime: %s\n' "$("$PYTHON_BIN" --version 2>&1)"

if [[ ! -e "$ENV_DIR" ]]; then
    printf 'Creating isolated environment: .venv\n'
    if command -v uv >/dev/null 2>&1; then
        uv venv --python "$PYTHON_BIN" "$ENV_DIR" || fail 'Could not create .venv.'
    else
        "$PYTHON_BIN" -m venv "$ENV_DIR" || fail 'Could not create .venv. Install the Python venv component or uv, then rerun.'
    fi
fi
[[ -x "$ENV_PYTHON" ]] || fail '.venv is incomplete. Rename it and rerun to create a fresh environment.'
"$ENV_PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' ||
    fail '.venv needs Python 3.10+. Rename it and rerun to create a supported environment.'

if ! "$ENV_PYTHON" -c 'import rich' >/dev/null 2>&1; then
    printf 'Installing missing runtime dependencies…\n'
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "$ENV_PYTHON" -r "$PROJECT_DIR/requirements.txt" ||
            fail 'Dependency installation failed. Check your connection and rerun.'
    else
        if ! "$ENV_PYTHON" -m pip --version >/dev/null 2>&1; then
            "$ENV_PYTHON" -m ensurepip --upgrade || fail 'pip is unavailable. Install the Python venv/pip components or uv.'
        fi
        "$ENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt" ||
            fail 'Dependency installation failed. Check your connection and rerun.'
    fi
fi

# Import the actual application before launch, catching missing modules early.
"$ENV_PYTHON" -c 'import rich; import web_server' || fail 'Application prerequisite check failed.'
printf 'Prerequisites ready.\n'
if "$CHECK_ONLY"; then
    exit 0
fi
printf 'Starting pytest-auditor web UI (Ctrl+C to stop)…\n'
exec "$ENV_PYTHON" "$PROJECT_DIR/web_server.py" "$@"
