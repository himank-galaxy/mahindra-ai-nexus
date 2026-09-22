#!/bin/bash
# Stops the live scoring loop started by run_scheduler.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.pids/scheduler.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "No scheduler.pid file found (already stopped?)."
  exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
  kill "$PID"
  echo "Scheduler stopped (PID $PID)."
else
  echo "Process $PID not running (already stopped?)."
fi

rm -f "$PID_FILE"
