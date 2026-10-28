#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$ROOT/.run/pids.json"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No pid file found; nothing to stop." >&2
  exit 0
fi

BACKEND_PID=$(python3 -c "import json,sys; print(json.load(open('$PIDFILE'))['backend'])")
DASHBOARD_PID=$(python3 -c "import json,sys; print(json.load(open('$PIDFILE'))['dashboard'])")

for pid in "$BACKEND_PID" "$DASHBOARD_PID"; do
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    echo "Stopped process $pid"
  else
    echo "Process $pid not running."
  fi
done

rm -f "$PIDFILE"
echo "ARMOR stopped."