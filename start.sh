#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/armor-backend"
mkdir -p "$ROOT/.run"
PIDFILE="$ROOT/.run/pids.json"

if [[ -f "$PIDFILE" ]]; then
  echo "Stack appears to be running (pid file exists). Run stop.sh first." >&2
  exit 1
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"

cd "$BACKEND_DIR"
python -m uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!
ARMOR_API_URL="http://127.0.0.1:$BACKEND_PORT" python -m streamlit run dashboard/app.py --server.port "$DASHBOARD_PORT" --server.headless true &
DASHBOARD_PID=$!

printf '{"backend":%s,"dashboard":%s,"backend_port":"%s","dashboard_port":"%s"}\n' \
  "$BACKEND_PID" "$DASHBOARD_PID" "$BACKEND_PORT" "$DASHBOARD_PORT" > "$PIDFILE"

echo "ARMOR started."
echo "  Backend:   http://127.0.0.1:$BACKEND_PORT"
echo "  Dashboard: http://127.0.0.1:$DASHBOARD_PORT"