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

# Detect a python that actually has the backend dependencies installed.
PYTHON_EXE=""
for cand in "$BACKEND_DIR/.venv/bin/python" "$ROOT/.venv/bin/python" "python3" "python"; do
  if [[ "$cand" != "python3" && "$cand" != "python" && ! -f "$cand" ]]; then
    continue
  fi
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import uvicorn, fastapi, streamlit" >/dev/null 2>&1; then
    PYTHON_EXE="$cand"
    break
  fi
done
if [[ -z "$PYTHON_EXE" ]]; then
  echo "No Python interpreter with ARMOR dependencies found." >&2
  echo "Install them with: python -m pip install -r armor-backend/requirements.txt" >&2
  exit 1
fi
echo "Using Python: $PYTHON_EXE"

BACKEND_PORT="${BACKEND_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8501}"

cd "$BACKEND_DIR"
"$PYTHON_EXE" -m uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
  > "$ROOT/.run/backend.log" 2>&1 &
BACKEND_PID=$!

READY=0
for _ in $(seq 1 20); do
  sleep 0.75
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then break; fi
  if "$PYTHON_EXE" - "$BACKEND_PORT" <<'PY' >/dev/null 2>&1
import sys, urllib.request
urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/api/v1/health", timeout=2)
PY
  then
    READY=1
    break
  fi
done

if [[ "$READY" -ne 1 ]]; then
  echo "Backend failed to start on port $BACKEND_PORT." >&2
  echo "--- .run/backend.log ---" >&2
  tail -n 20 "$ROOT/.run/backend.log" >&2 || true
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi

ARMOR_API_URL="http://127.0.0.1:$BACKEND_PORT" "$PYTHON_EXE" -m streamlit run dashboard/app.py --server.port "$DASHBOARD_PORT" --server.headless true \
  > "$ROOT/.run/dashboard.log" 2>&1 &
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
