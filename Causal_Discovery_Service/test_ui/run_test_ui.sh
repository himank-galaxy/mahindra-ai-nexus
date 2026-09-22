#!/bin/bash
# Starts the Causal Discovery Service test UI: a small API (uvicorn) and a
# static frontend server, BOTH bound to 127.0.0.1 only.
#
# This is a local-only testing tool. It is never bound to 0.0.0.0, never
# added to docker-compose, and never touches the existing frontend/backend
# or any existing port. Safe to run temporarily on any machine that has a
# copy of this repository and can reach the Postgres database (read-only).
#
# Usage:
#   ./run_test_ui.sh              # uses default ports 8790 (API) / 8791 (frontend)
#   API_PORT=9001 UI_PORT=9002 ./run_test_ui.sh   # override ports if 8790/8791 are busy
#
# Stop with ./stop_test_ui.sh, or Ctrl+C if running in the foreground.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$SERVICE_ROOT/.venv/bin/python3"

API_PORT="${API_PORT:-8790}"
UI_PORT="${UI_PORT:-8791}"

PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

if [ ! -x "$VENV_PYTHON" ]; then
  echo "This service's virtual environment was not found at $SERVICE_ROOT/.venv"
  echo "Set it up first: python3 -m venv \"$SERVICE_ROOT/.venv\" && \"$VENV_PYTHON\" -m pip install -r \"$SERVICE_ROOT/requirements.txt\" -r \"$SCRIPT_DIR/requirements.txt\""
  exit 1
fi

# Write the API port into a small config file the frontend loads, so
# nobody has to hand-edit app.js when overriding API_PORT/UI_PORT.
echo "window.CAUSAL_TEST_API_BASE = \"http://127.0.0.1:$API_PORT\";" \
  > "$SCRIPT_DIR/frontend/config.js"

echo "Starting Causal Discovery Test UI API on 127.0.0.1:$API_PORT ..."
cd "$SCRIPT_DIR/api"
nohup "$VENV_PYTHON" -m uvicorn main:app \
  --host 127.0.0.1 --port "$API_PORT" \
  > "$SCRIPT_DIR/api_stdout.log" 2>&1 &
echo $! > "$PID_DIR/api.pid"

echo "Starting static frontend server on 127.0.0.1:$UI_PORT ..."
cd "$SCRIPT_DIR/frontend"
nohup "$VENV_PYTHON" -m http.server "$UI_PORT" --bind 127.0.0.1 \
  > "$SCRIPT_DIR/frontend_stdout.log" 2>&1 &
echo $! > "$PID_DIR/frontend.pid"

sleep 1

echo ""
echo "Open: http://127.0.0.1:$UI_PORT"
echo "API health check: http://127.0.0.1:$API_PORT/api/health"
echo ""
echo "Stop with: ./stop_test_ui.sh"
