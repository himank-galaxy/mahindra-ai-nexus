#!/bin/bash
# Starts the live scoring loop (scheduler.py) in the background.
#
# Separate from run_service.sh (which only starts the API + UI) since the
# API/UI can browse existing warnings without this running - this is only
# needed to keep detecting NEW warnings from live telemetry.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAUSAL_VENV_PYTHON="$SCRIPT_DIR/../Causal_Discovery_Service/.venv/bin/python3"

PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

if [ -f "$PID_DIR/scheduler.pid" ] && ps -p "$(cat "$PID_DIR/scheduler.pid")" > /dev/null 2>&1; then
  echo "Scheduler already running (PID $(cat "$PID_DIR/scheduler.pid"))."
  exit 0
fi

if [ ! -x "$CAUSAL_VENV_PYTHON" ]; then
  echo "Causal_Discovery_Service/.venv not found. See run_service.sh for setup."
  exit 1
fi

cd "$SCRIPT_DIR"
setsid "$CAUSAL_VENV_PYTHON" scheduler.py > scheduler_stdout.log 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PID_DIR/scheduler.pid"

sleep 1

if ps -p "$PID" > /dev/null 2>&1; then
  echo "Scheduler started (PID $PID). Log: scheduler_stdout.log"
else
  echo "Scheduler failed to start. Check scheduler_stdout.log."
  rm -f "$PID_DIR/scheduler.pid"
  exit 1
fi
