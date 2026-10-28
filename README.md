# A.R.M.O.R. — Active Real-Time Machine & Operator Response System

Internal codename for **MachinoCare 2.0**: a closed-loop cyber-physical worker-safety cell.
See `docs/` for the merged build spec, roadmap, and architecture.

## Layout

```
armor/
├── docs/                       # Specs (single source of truth: "ARMOR Merged Build Spec.md")
│   ├── hardware-pinout.md      # Authoritative ESP32 pinout (also on `hardware` branch)
│   └── data-streaming.md       # MQTT/HTTP streaming spec (also on `hardware` branch)
├── armor-backend/              # FastAPI gateway + SQLite + Streamlit dashboard
│   ├── backend/                # FastAPI app, storage, vision engine, models
│   ├── dashboard/app.py        # Streamlit Operator Control Room
│   ├── scripts/                # ESP32 / breach simulators
│   ├── tests (test_*.py)       # End-to-end backend + vision tests
│   ├── .env.example            # Copy to .env and fill in
│   ├── requirements.txt        # Runtime deps
│   └── requirements-dev.txt    # Test deps (httpx)
├── start.ps1 / start.bat / start.sh # One-click stack startup
├── stop.ps1 / stop.bat / stop.sh    # One-click stack shutdown
├── test_backend.py             # Root shims (run from repo root)
└── test_vision.py
```

## Quick Start

### 1. One-Click Startup (Recommended)

Start both the FastAPI backend and Streamlit dashboard together:

**Windows (PowerShell or double-click `.bat`):**
```powershell
.\start.ps1       # Or double-click start.bat
```

To stop all services cleanly:
```powershell
.\stop.ps1        # Or double-click stop.bat
```

**Linux / macOS:**
```bash
./start.sh
./stop.sh
```

---

### 2. Manual Setup & Startup

```powershell
cd armor-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env as needed

# Terminal 1: backend gateway
python -m uvicorn backend.main:app --reload --port 8000

# Terminal 2: operator dashboard
streamlit run dashboard/app.py --server.port 8501

# Terminal 3: simulated ESP32 telemetry (optional)
python scripts/simulate_esp32.py
```

## Tests

```powershell
cd armor-backend
.\.venv\Scripts\python.exe test_backend.py
.\.venv\Scripts\python.exe test_vision.py
```

## Git Workflow

Short-lived feature branches (`feat/*`, `chore/*`, `fix/*`) branch off `main` and merge back into `main` when done and tested. `main` stays demo-ready.
Never commit `.env`, `data/`, or `.venv/`.
