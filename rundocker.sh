#!/usr/bin/env bash
# Start or stop this app's Docker Compose project from any working directory.
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-start}"
if [[ "$ACTION" == '--help' || "$ACTION" == '-h' ]]; then
    cat <<'HELP'
Usage: ./rundocker.sh [start|stop]

No argument (or start): build the image and start the app in the background.
stop: stop and remove this app's containers and network.

Open http://127.0.0.1:6767 after startup. Optional environment variables:
  AUDITOR_PORT=9000              Choose a different host port.
  AUDIT_SOURCE_DIR=/path/project Mount another project read-only at /workspace.
The folder picker browses container paths; use /workspace/tests for mounted tests.
Requires Docker with the Compose plugin and a running, accessible Docker daemon.
HELP
    exit 0
fi
if [[ "$ACTION" != start && "$ACTION" != stop || $# -gt 1 ]]; then
    printf 'Usage: ./rundocker.sh [start|stop]\n' >&2
    exit 2
fi
command -v docker >/dev/null 2>&1 || { printf 'Docker is required. Install Docker and its Compose plugin, then rerun.\n' >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { printf 'The Docker Compose plugin is required.\n' >&2; exit 1; }
docker info >/dev/null 2>&1 || { printf 'Cannot reach Docker. Start the daemon and check your Docker socket permissions.\n' >&2; exit 1; }

export AUDITOR_PORT="${AUDITOR_PORT:-6767}"
export AUDITOR_UID="${AUDITOR_UID:-$(id -u)}"
export AUDITOR_GID="${AUDITOR_GID:-$(id -g)}"
export AUDIT_SOURCE_DIR="${AUDIT_SOURCE_DIR:-$PROJECT_DIR}"
COMPOSE=(docker compose --project-name pytest-auditor --project-directory "$PROJECT_DIR" --file "$PROJECT_DIR/compose.yaml")

if [[ "$ACTION" == stop ]]; then
    "${COMPOSE[@]}" down --remove-orphans
    printf 'pytest-auditor Docker services stopped.\n'
    exit 0
fi

if [[ ! "$AUDITOR_PORT" =~ ^[0-9]+$ ]] || (( 10#$AUDITOR_PORT < 1 || 10#$AUDITOR_PORT > 65535 )); then
    printf 'AUDITOR_PORT must be an integer from 1 to 65535.\n' >&2
    exit 2
fi
[[ -d "$AUDIT_SOURCE_DIR" ]] || { printf 'AUDIT_SOURCE_DIR must be an existing project directory.\n' >&2; exit 2; }
export AUDIT_SOURCE_DIR="$(cd -- "$AUDIT_SOURCE_DIR" && pwd)"
printf 'Building and starting pytest-auditor in Docker…\n'
if ! "${COMPOSE[@]}" up --build --detach --wait --wait-timeout 90; then
    printf 'Docker startup failed. Inspect logs with: docker compose -p pytest-auditor -f "%s/compose.yaml" logs\n' "$PROJECT_DIR" >&2
    printf 'Clean up with: ./rundocker.sh stop\n' >&2
    exit 1
fi
printf 'pytest-auditor web UI: http://127.0.0.1:%s\n' "$AUDITOR_PORT"
printf 'Mounted tests: /workspace (host: %s)\n' "$AUDIT_SOURCE_DIR"
printf 'Stop everything for this app with: ./rundocker.sh stop\n'
