#!/bin/bash
# Starts the Predictive Early-Warning Service's API and static UI, BOTH
# bound to 127.0.0.1 only. Local-only test tool - never bound to 0.0.0.0,
# never added to docker-compose, never touching any existing port.
#
# Uses Causal_Discovery_Service/.venv (this service's requirements.txt was
# installed into that same shared environment - see IMPLEMENTATION_PLAN.md)
# so it can import Causal_Discovery_Service's modules directly.
#
# Usage:
#   ./run_service.sh                                # default ports 8792 (API) / 8793 (UI)
#   API_PORT=9003 UI_PORT=9004 ./run_service.sh      # override if busy
#
# Note: this only starts the API + UI. The live scoring loop
# (scheduler.py) and model training (train_model.py) are run separately,
# by hand, since they are not needed just to browse existing warnings.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAUSAL_VENV_PYTHON="$SCRIPT_DIR/../Causal_Discovery_Service/.venv/bin/python3"

API_PORT="${API_PORT:-8792}"
UI_PORT="${UI_PORT:-8793}"

PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

if [ ! -x "$CAUSAL_VENV_PYTHON" ]; then
  echo "Causal_Discovery_Service/.venv not found. Set it up first (see that"
  echo "service's own instructions), then: "
  echo "  \"$CAUSAL_VENV_PYTHON\" -m pip install -r \"$SCRIPT_DIR/requirements.txt\""
  exit 1
fi

echo "window.PEWS_API_BASE = \"http://127.0.0.1:$API_PORT\";" > "$SCRIPT_DIR/ui/config.js"

echo "Starting Predictive Early-Warning API on 127.0.0.1:$API_PORT ..."
cd "$SCRIPT_DIR/api"
nohup "$CAUSAL_VENV_PYTHON" -m uvicorn main:app \
  --host 127.0.0.1 --port "$API_PORT" \
  > "$SCRIPT_DIR/api_stdout.log" 2>&1 &
echo $! > "$PID_DIR/api.pid"

echo "Starting static UI server on 127.0.0.1:$UI_PORT ..."
cd "$SCRIPT_DIR/ui"
nohup "$CAUSAL_VENV_PYTHON" -m http.server "$UI_PORT" --bind 127.0.0.1 \
  > "$SCRIPT_DIR/ui_stdout.log" 2>&1 &
echo $! > "$PID_DIR/ui.pid"

sleep 1

echo ""
echo "Open: http://127.0.0.1:$UI_PORT/warnings-list.html"
echo "API health check: http://127.0.0.1:$API_PORT/api/health"
echo ""
echo "Stop with: ./stop_service.sh"
