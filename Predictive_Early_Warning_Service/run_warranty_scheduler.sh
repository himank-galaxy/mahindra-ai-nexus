#!/bin/bash
# Starts the warranty-liability batch scoring loop (warranty_scheduler.py)
# in the background - separate process from run_scheduler.sh (PEWS's own
# live telematics scheduler), since the two have very different cadences
# (telematics: ~60s reactive; warranty: ~hourly full-fleet batch).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAUSAL_VENV_PYTHON="$SCRIPT_DIR/../Causal_Discovery_Service/.venv/bin/python3"

PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

if [ -f "$PID_DIR/warranty_scheduler.pid" ] && ps -p "$(cat "$PID_DIR/warranty_scheduler.pid")" > /dev/null 2>&1; then
  echo "Warranty scheduler already running (PID $(cat "$PID_DIR/warranty_scheduler.pid"))."
  exit 0
fi

if [ ! -x "$CAUSAL_VENV_PYTHON" ]; then
  echo "Causal_Discovery_Service/.venv not found. See run_service.sh for setup."
  exit 1
fi

cd "$SCRIPT_DIR"
setsid "$CAUSAL_VENV_PYTHON" warranty_scheduler.py > warranty_scheduler_stdout.log 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PID_DIR/warranty_scheduler.pid"

sleep 1

if ps -p "$PID" > /dev/null 2>&1; then
  echo "Warranty scheduler started (PID $PID). Log: warranty_scheduler_stdout.log"
else
  echo "Warranty scheduler failed to start. Check warranty_scheduler_stdout.log."
  rm -f "$PID_DIR/warranty_scheduler.pid"
  exit 1
fi
