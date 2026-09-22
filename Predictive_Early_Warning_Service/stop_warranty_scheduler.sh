#!/bin/bash
# Stops the warranty scoring loop started by run_warranty_scheduler.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.pids/warranty_scheduler.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "No warranty_scheduler.pid file found (already stopped?)."
  exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
  kill "$PID"
  echo "Warranty scheduler stopped (PID $PID)."
else
  echo "Process $PID not running (already stopped?)."
fi

rm -f "$PID_FILE"
