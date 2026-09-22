#!/bin/bash
# Stops the Predictive Early-Warning Service's API and UI started by
# run_service.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

stop_pid_file() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"

  if [ ! -f "$pid_file" ]; then
    echo "$name: no PID file found (already stopped?)"
    return
  fi

  local pid
  pid=$(cat "$pid_file")

  if ps -p "$pid" > /dev/null 2>&1; then
    kill "$pid"
    echo "$name: stopped (PID $pid)"
  else
    echo "$name: process $pid not running (already stopped?)"
  fi

  rm -f "$pid_file"
}

stop_pid_file "api"
stop_pid_file "ui"
