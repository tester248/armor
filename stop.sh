#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$ROOT/.run/pids.json"

STOPPED=0
if [[ -f "$PIDFILE" ]]; then
  BACKEND_PID=$(python3 -c "import json; print(json.load(open('$PIDFILE')).get('backend',''))" 2>/dev/null || echo "")
  DASHBOARD_PID=$(python3 -c "import json; print(json.load(open('$PIDFILE')).get('dashboard',''))" 2>/dev/null || echo "")

  for pid in "$BACKEND_PID" "$DASHBOARD_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "Stopped process $pid"
      STOPPED=$((STOPPED + 1))
    fi
  done
  rm -f "$PIDFILE"
fi

echo "ARMOR stopped ($STOPPED process(es) terminated)."
