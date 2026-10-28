#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/armor-backend"
mkdir -p "$ROOT/.run"
PIDFILE="$ROOT/.run/pids.json"

if [[ -f "$PIDFILE" ]]; then
  BACKEND_PID=$(python3 -c "import json; print(json.load(open('$PIDFILE')).get('backend',''))" 2>/dev/null || echo "")
  DASHBOARD_PID=$(python3 -c "import json; print(json.load(open('$PIDFILE')).get('dashboard',''))" 2>/dev/null || echo "")
  STALE=1
  for pid in "$BACKEND_PID" "$DASHBOARD_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      STALE=0
      break
    fi
  done
  if [[ "$STALE" -eq 0 ]]; then
    echo "Stack appears to be running. Run ./stop.sh first." >&2
    exit 1
  else
    echo "Cleaning up stale pid file..."
    rm -f "$PIDFILE"
  fi
fi

# Detect python executable (prefers virtualenv if available)
PYTHON_EXE="python3"
if [[ -f "$BACKEND_DIR/.venv/bin/python" ]]; then
  PYTHON_EXE="$BACKEND_DIR/.venv/bin/python"
elif [[ -f "$ROOT/.venv/bin/python" ]]; then
  PYTHON_EXE="$ROOT/.venv/bin/python"
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"

cd "$BACKEND_DIR"
"$PYTHON_EXE" -m uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!
ARMOR_API_URL="http://127.0.0.1:$BACKEND_PORT" "$PYTHON_EXE" -m streamlit run dashboard/app.py --server.port "$DASHBOARD_PORT" --server.headless true &
DASHBOARD_PID=$!

printf '{"backend":%s,"dashboard":%s,"backend_port":"%s","dashboard_port":"%s"}\n' \
  "$BACKEND_PID" "$DASHBOARD_PID" "$BACKEND_PORT" "$DASHBOARD_PORT" > "$PIDFILE"

echo "========================================"
echo "  A.R.M.O.R. System Online"
echo "========================================"
echo "  Backend Gateway:    http://127.0.0.1:$BACKEND_PORT"
echo "  API Docs (Swagger): http://127.0.0.1:$BACKEND_PORT/docs"
echo "  Operator Dashboard: http://127.0.0.1:$DASHBOARD_PORT"
echo "  Run ./stop.sh to shut down cleanly."
