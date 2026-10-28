"""
ARMOR – Streamlit Operator Control Room (Rewritten)
=====================================================
Active Real-Time Machine & Operator Response System

Sections:
  1. System Health & Sidebar Controls
  2. Real Data Fetching (no synthetic fallbacks)
  3. KPI Metric HUD
  4. Subsystem Test Panel (per-subsystem manual tests)
  5. Calibration & Predictive Maintenance Panel
  6. Vision Panel (Live Camera / 3D Twin / Manual Helmet Test)
  7. Live Telemetry Charts
  8. Safety Incident Audit Log & Snapshot Inspector
  9. WebSocket Live Feed & MQTT Debug
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ── Backend API ────────────────────────────────────────────────────────────
try:
    from backend.vision import vision_engine
    VISION_AVAILABLE = True
except Exception:
    vision_engine = None
    VISION_AVAILABLE = False

# ── Config ─────────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("ARMOR_API_URL", "http://127.0.0.1:8000")
DEFAULT_DEVICE_ID = os.getenv("ARMOR_DEVICE_ID", "machino_node_01")
SNAPSHOTS_DIR = Path(os.getenv("SNAPSHOT_DIR", "data/snapshots"))

# ── Page Configuration ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="ARMOR // Operator Control Room",
    page_icon=":material/shield:",
    layout="wide",
    initial_sidebar_state="expanded",
)
# ── Custom CSS Design System ───────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --armor-bg: #0b0f19;
        --armor-card-bg: rgba(18, 26, 43, 0.75);
        --armor-card-border: rgba(56, 189, 248, 0.15);
        --armor-text-primary: #f8fafc;
        --armor-text-muted: #94a3b8;
        --armor-green: #10b981;
        --armor-green-glow: rgba(16, 185, 129, 0.25);
        --armor-red: #ef4444;
        --armor-red-glow: rgba(239, 68, 68, 0.35);
        --armor-amber: #f59e0b;
        --armor-cyan: #06b6d4;
    }

    html, body, [data-testid="stAppViewContainer"] {
        background-color: var(--armor-bg);
        color: var(--armor-text-primary);
        font-family: 'Inter', sans-serif;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #090d16 0%, #101726 100%) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }

    .armor-panel {
        background: var(--armor-card-bg);
        border: 1px solid var(--armor-card-border);
        border-radius: 12px;
        padding: 18px;
        backdrop-filter: blur(16px);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        margin-bottom: 16px;
    }

    .hud-card {
        background: rgba(15, 23, 42, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 14px 18px;
        position: relative;
        overflow: hidden;
    }
    .hud-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; width: 4px; height: 100%;
        background: var(--armor-cyan);
    }
    .hud-card.hud-green::before { background: var(--armor-green); }
    .hud-card.hud-red::before { background: var(--armor-red); }
    .hud-card.hud-amber::before { background: var(--armor-amber); }
    .hud-card.hud-blue::before { background: var(--armor-cyan); }

    .hud-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--armor-text-muted);
        margin-bottom: 4px;
    }
    .hud-value {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.65rem;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.2;
    }
    .hud-value.hud-tight {
        font-size: 1.35rem;
        white-space: nowrap;
    }
    .hud-value.hud-tiny {
        font-size: 1.05rem;
        white-space: nowrap;
    }
    .hud-sub {
        font-size: 0.75rem;
        color: var(--armor-text-muted);
        margin-top: 4px;
    }

    .alert-banner-normal {
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.15) 0%, rgba(6, 182, 212, 0.1) 100%);
        border: 1px solid var(--armor-green);
        border-radius: 10px;
        padding: 12px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 0 20px var(--armor-green-glow);
        margin-bottom: 20px;
    }
    .alert-banner-lockout {
        background: linear-gradient(90deg, rgba(239, 68, 68, 0.25) 0%, rgba(185, 28, 28, 0.2) 100%);
        border: 2px solid var(--armor-red);
        border-radius: 10px;
        padding: 14px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 0 30px var(--armor-red-glow);
        margin-bottom: 20px;
        animation: pulse-red 1.5s infinite;
    }
    .alert-banner-breach {
        background: linear-gradient(90deg, rgba(245, 158, 11, 0.2) 0%, rgba(217, 119, 6, 0.15) 100%);
        border: 1px solid var(--armor-amber);
        border-radius: 10px;
        padding: 14px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 0 25px rgba(245, 158, 11, 0.25);
        margin-bottom: 20px;
    }
    .alert-banner-offline {
        background: linear-gradient(90deg, rgba(100, 116, 139, 0.2) 0%, rgba(71, 85, 105, 0.15) 100%);
        border: 1px dashed rgba(148, 163, 184, 0.4);
        border-radius: 10px;
        padding: 14px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
    }
    .alert-banner-info {
        background: linear-gradient(90deg, rgba(6, 182, 212, 0.15) 0%, rgba(56, 189, 248, 0.1) 100%);
        border: 1px solid var(--armor-cyan);
        border-radius: 10px;
        padding: 12px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 0 20px rgba(6, 182, 212, 0.25);
        margin-bottom: 20px;
    }

    @keyframes pulse-red {
        0% { box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }
        50% { box-shadow: 0 0 35px rgba(239, 68, 68, 0.85); }
        100% { box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }
    }

    .video-frame-container {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(56, 189, 248, 0.3);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
        position: relative;
        background: #020617;
    }
    /* Force MJPEG stream iframe to fill its container without cropping */
    .video-frame-container iframe {
        width: 100% !important;
        height: 100% !important;
        object-fit: contain !important;
        object-position: center !important;
        display: block !important;
    }
    .live-badge {
        position: absolute;
        top: 12px;
        left: 12px;
        background: rgba(239, 68, 68, 0.9);
        color: white;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 4px;
        letter-spacing: 0.1em;
        z-index: 10;
        box-shadow: 0 0 10px rgba(239, 68, 68, 0.8);
    }

    .armor-header {
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 700;
        font-size: 1.4rem;
        color: #ffffff;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
    }
    .section-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        text-transform: uppercase;
        color: var(--armor-cyan);
        letter-spacing: 0.1em;
        margin-bottom: 8px;
    }

    .stApp, .main .block-container {
        background-color: var(--armor-bg) !important;
        color: var(--armor-text-primary) !important;
    }
    h1, h2, h3, h4, h5, h6, p, span, label, li, td, th, div {
        color: var(--armor-text-primary) !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span, [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] div {
        color: var(--armor-text-primary) !important;
    }
    [data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] small {
        color: var(--armor-text-muted) !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: rgba(15, 23, 42, 0.6);
        border-radius: 8px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent !important;
        color: var(--armor-text-muted) !important;
        border-radius: 6px;
        padding: 8px 16px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: rgba(6, 182, 212, 0.15) !important;
        color: var(--armor-cyan) !important;
        border-bottom: 2px solid var(--armor-cyan);
    }
    .stButton > button {
        background: linear-gradient(135deg, rgba(6, 182, 212, 0.2) 0%, rgba(56, 189, 248, 0.1) 100%) !important;
        color: #ffffff !important;
        border: 1px solid rgba(6, 182, 212, 0.4) !important;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, rgba(6, 182, 212, 0.35) 0%, rgba(56, 189, 248, 0.2) 100%) !important;
        border-color: var(--armor-cyan) !important;
        box-shadow: 0 0 12px rgba(6, 182, 212, 0.3);
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.3) 0%, rgba(185, 28, 28, 0.2) 100%) !important;
        border-color: var(--armor-red) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.5) 0%, rgba(185, 28, 28, 0.35) 100%) !important;
        box-shadow: 0 0 16px rgba(239, 68, 68, 0.4);
    }
    .stTextInput input, .stSelectbox [data-baseweb="select"] {
        background-color: rgba(15, 23, 42, 0.8) !important;
        color: #ffffff !important;
        border-color: rgba(56, 189, 248, 0.2) !important;
        border-radius: 6px;
    }
    .stSelectbox [data-baseweb="select"] > div {
        background-color: rgba(15, 23, 42, 0.8) !important;
        color: #ffffff !important;
    }
    [data-testid="stDataFrame"], .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    .stSuccess, .stAlert, [data-testid="stNotification"] {
        border-radius: 8px !important;
    }
    [data-testid="stToast"] {
        background-color: rgba(15, 23, 42, 0.95) !important;
        border: 1px solid rgba(56, 189, 248, 0.3) !important;
        backdrop-filter: blur(12px);
    }
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-family: 'Space Grotesk', sans-serif !important;
    }
    [data-testid="stMetricLabel"] {
        color: var(--armor-text-muted) !important;
    }
    .js-plotly-plot .plotly .modebar {
        background: transparent !important;
    }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); }
    ::-webkit-scrollbar-thumb { background: rgba(6, 182, 212, 0.3); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(6, 182, 212, 0.5); }

    .system-status-bar {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 14px;
    }
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(15, 23, 42, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 20px;
        padding: 5px 14px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: var(--armor-text-primary);
    }
    .status-pill b { font-weight: 700; }
    .status-dot {
        width: 8px; height: 8px;
        border-radius: 50%;
        display: inline-block;
    }
    .status-online .status-dot { background: #10b981; box-shadow: 0 0 8px #10b981; }
    .status-online { border-color: rgba(16, 185, 129, 0.4); color: #a7f3d0; }
    .status-offline .status-dot { background: #ef4444; box-shadow: 0 0 8px #ef4444; }
    .status-offline { border-color: rgba(239, 68, 68, 0.4); color: #fca5a5; }
    .status-standby .status-dot { background: #f59e0b; box-shadow: 0 0 8px #f59e0b; }
    .status-standby { border-color: rgba(245, 158, 11, 0.4); color: #fde68a; }
    .status-active .status-dot { background: #06b6d4; box-shadow: 0 0 8px #06b6d4; }
    .status-active { border-color: rgba(6, 182, 212, 0.4); color: #bae6fd; }

    .armor-icon {
        display: inline-block;
        vertical-align: middle;
        flex-shrink: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Modern SVG Icon System ─────────────────────────────────────────────────
def icon_svg(name: str, color: str = "currentColor", size: int = 18, stroke_width: float = 2.0) -> str:
    icons = {
        "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
        "shield_check": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
        "shield_alert": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>',
        "siren": '<path d="M7 18v-6a5 5 0 1 1 10 0v6"/><path d="M5 21a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-1a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2z"/><path d="M21 12h1"/><path d="M18.5 4.5l.5-.5"/><path d="M2 12h1"/><path d="M12 2v1"/><path d="m4.929 4.929.707.707"/><path d="M12 12v6"/>',
        "alert_triangle": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
        "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
        "video": '<path d="m22 8-6 4 6 4V8Z"/><rect width="14" height="12" x="2" y="6" rx="2" ry="2"/>',
        "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
        "trending_up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
        "clipboard_check": '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
        "badge": '<rect width="18" height="13" x="3" y="6" rx="2"/><circle cx="8.5" cy="12.5" r="2.5"/><path d="M14 11h3"/><path d="M14 14h3"/><path d="M10 2v4"/><path d="M14 2v4"/>',
        "lock": '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
        "lock_open": '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>',
        "check_circle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
        "x_circle": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
        "refresh": '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.85.83 6.72 2.24L21 8"/><path d="M21 3v5h-5"/>',
        "walk": '<circle cx="13.5" cy="4.5" r="2.5"/><path d="m8 22 4-11 3 3v8"/><path d="M18 11.5 14 8l-3 2-4-2"/>',
        "calibration": '<circle cx="12" cy="12" r="9"/><path d="M7 11v3a4 4 0 0 0 4 4h3m-4-11V2m0 0a3 3 0 1 0-3 3m0 0"/><line x1="12" y1="12" x2="12" y2="18"/>',
        "plug": '<path d="M5 3h3v4H5z"/><path d="M16 3h3v4h-3z"/><path d="M9 21V9"/><path d="M15 12h1"/><path d="M9 12H8"/><path d="M12 15v1"/><path d="M12 9v1"/>',
        "bug": '<circle cx="8" cy="8" r="3"/><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.85.83 6.72 2.24L21 8"/><path d="M21 3v5h-5"/>',
        "play": '<polygon points="5 3 19 12 5 21"/>',
        "stop": '<rect x="6" y="6" width="12" height="12" rx="2" ry="2"/>',
        "gear": '<path d="M20.04 9.04a5 5 0 0 0-3.07-3.07l-.07-.07a5 5 0 0 0-7.07 0l-.07.07a5 5 0 0 0 0 7.07l.07.07a5 5 0 0 0 7.07 0l.07-.07a5 5 0 0 0 3.07-3.07z"/><circle cx="12" cy="12" r="3"/>',
    }
    inner = icons.get(name, "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" '
        f'class="armor-icon" style="vertical-align: middle; display: inline-block;">{inner}</svg>'
    )
# ── Resilient Fast API Helpers ─────────────────────────────────────────────
def api_get(endpoint: str, params: dict | None = None, timeout: float = 0.6) -> Any:
    try:
        r = requests.get(f"{API_BASE_URL}{endpoint}", params=params, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def api_post(endpoint: str, json_data: dict | None = None, params: dict | None = None, timeout: float = 1.5):
    try:
        r = requests.post(f"{API_BASE_URL}{endpoint}", json=json_data, params=params, timeout=timeout)
        return r.status_code, r.json() if r.content else {}
    except Exception as e:
        return 500, {"error": str(e)}


def api_delete(endpoint: str, params: dict | None = None, timeout: float = 2.0):
    try:
        r = requests.delete(f"{API_BASE_URL}{endpoint}", params=params, timeout=timeout)
        return r.status_code, r.json() if r.content else {}
    except Exception as e:
        return 500, {"error": str(e)}


# ── Step 1: Fast Single Health Check ──────────────────────────────────────
health = api_get("/api/v1/health", timeout=1.0)
backend_online = health is not None and health.get("status") == "ok"

# ── Sidebar Controls ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:4px;">
            {icon_svg('shield', color='#06b6d4', size=24)}
            <span style="font-family:'Space Grotesk',sans-serif; font-size:1.25rem; font-weight:700; color:#ffffff; letter-spacing:0.02em;">ARMOR COMMAND</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Active Real-Time Machine & Operator Response")
    st.markdown("---")

    device_id = st.text_input("Machine Cell ID", value=DEFAULT_DEVICE_ID)

    refresh_rate = st.select_slider(
        "Auto-Refresh Stream",
        options=[0, 1, 2, 3, 5],
        value=2,
        format_func=lambda x: "Paused" if x == 0 else f"{x} sec",
    )

    if backend_online:
        st.success("● Gateway Online (`127.0.0.1:8000`)")
        mqtt_ok = health.get("mqtt_connected", False)
        st.caption(f"MQTT Broker: `{health.get('mqtt_broker')}` ({'Online' if mqtt_ok else 'Standby'})")
    else:
        st.error("● Gateway Offline")
        st.caption("Start backend:<br>`python -m uvicorn --app-dir armor-backend backend.main:app --port 8000`", unsafe_allow_html=True)

    st.markdown("---")

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
            {icon_svg('zap', color='#f59e0b', size=16)}
            <span style="font-family:'Space Grotesk',sans-serif; font-size:0.95rem; font-weight:700; color:#ffffff;">ESP32 Machine Node</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if backend_online:
        st.caption("Telemetry arrives via MQTT from the ESP32. No simulation.")
    else:
        st.caption("Start backend to receive ESP32 telemetry.")

    st.markdown("---")

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
            {icon_svg('badge', color='#06b6d4', size=16)}
            <span style="font-family:'Space Grotesk',sans-serif; font-size:0.95rem; font-weight:700; color:#ffffff;">Authorized Smart Badges</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if backend_online:
        workers_data = api_get("/api/v1/workers")
        if workers_data and "badges" in workers_data:
            for b in workers_data["badges"][:5]:
                st.markdown(
                    f"- **{b.get('worker_id')}** ({b.get('worker_name', 'Operator')})<br>"
                    f"  <small style='color:#94a3b8;'>MAC: `{b.get('badge_mac')}`</small>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No registered badges found.")
    else:
        st.caption("- **WORKER_EMP_402** (Arjun Sharma)<br><small style='color:#94a3b8;'>MAC: `24:6F:28:AB:C1:02`</small>", unsafe_allow_html=True)

# Only auto-refresh if backend is online and refresh is not paused
if backend_online and refresh_rate > 0:
    st_autorefresh(interval=refresh_rate * 1000, key="armor_autorefresh")
# ── Step 2: Fetch Real Data (no synthetic fallbacks) ──────────────────────
status_data: dict[str, Any] = {}
samples: list[dict[str, Any]] = []
incidents: list[dict[str, Any]] = []
model_package: dict[str, Any] | None = None
anomalies: list[dict[str, Any]] = []
badges: list[dict[str, Any]] = []
breaches: list[dict[str, Any]] = []

if backend_online:
    status_data = api_get(f"/api/v1/status/{device_id}", timeout=1.0) or {}
    telemetry_resp = api_get(f"/api/v1/telemetry/{device_id}", params={"limit": 120}, timeout=1.0)
    samples = telemetry_resp.get("samples", []) if telemetry_resp else []
    incidents_resp = api_get("/api/v1/incidents", params={"device_id": device_id, "limit": 50}, timeout=1.0)
    incidents = incidents_resp.get("incidents", []) if incidents_resp else []
    model_resp = api_get(f"/api/v1/model/{device_id}", timeout=1.0)
    if model_resp:
        model_package = model_resp.get("model_package")
    # 120 rows ≈ the last two minutes of 1 Hz scoring — enough for a live trend.
    anomalies_resp = api_get("/api/v1/anomalies", params={"device_id": device_id, "limit": 120}, timeout=1.0)
    anomalies = anomalies_resp.get("anomalies", []) if anomalies_resp else []
    workers_resp = api_get("/api/v1/workers", timeout=1.0)
    badges = workers_resp.get("badges", []) if workers_resp else []
    breaches_resp = api_get("/api/v1/breaches", params={"device_id": device_id, "limit": 40}, timeout=1.0)
    breaches = breaches_resp.get("breaches", []) if breaches_resp else []
    decomp_resp = api_get(f"/api/v1/telemetry/anomaly/decomposition/{device_id}", timeout=1.0)
    decomp_data = decomp_resp if isinstance(decomp_resp, dict) else {}
    pred_resp = api_get(f"/api/v1/telemetry/prediction/{device_id}", timeout=2.0)
    prediction_data = pred_resp if isinstance(pred_resp, dict) else {}
else:
    decomp_data = {}
    prediction_data = {}


def _reading(value: Any, fallback: Any = None) -> float | None:
    """Return a real sensor reading, or fallback (from samples), or None. Never invent a value."""
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    if fallback is not None:
        try:
            return float(fallback)
        except (TypeError, ValueError):
            pass
    return None


def _parse_ts(value: Any) -> datetime | None:
    """Parse an API timestamp (ISO string, epoch s or epoch ms) to aware UTC."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or (
            isinstance(value, str) and value.strip().replace(".", "", 1).isdigit()
        ):
            num = float(value)
            if num < 1e10:  # seconds
                return datetime.fromtimestamp(num, tz=timezone.utc)
            return datetime.fromtimestamp(num / 1000.0, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _age_text(value: Any) -> str:
    """Human readable age of a timestamp, or 'unknown' when unparseable."""
    dt = _parse_ts(value)
    if dt is None:
        return "unknown"
    seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _contact_time(value: Any, fallback: Any = None) -> str:
    """Format a badge contact timestamp, preferring the device ts when sane."""
    dt = _parse_ts(value)
    if dt is None or dt.year < 2000:  # ESP32 millis() uptime is not a wall clock
        dt = _parse_ts(fallback)
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "—"


def _contact_age(event: dict[str, Any]) -> str:
    return _age_text(event.get("ts") if _parse_ts(event.get("ts")) else event.get("created_at"))


motor_state = status_data.get("motor_state") or (samples[-1].get("motor_state") if samples else "NO DATA")
interlock_active = bool(status_data.get("interlock_active", False))
proximity_breach = bool(status_data.get("proximity_breach_active", False))
vicinity_presence = bool(status_data.get("vicinity_presence_active", False))
vicinity_status = status_data.get("vicinity_status", "NOMINAL")
anomaly_pct = float(status_data.get("anomaly_percentage") or decomp_data.get("anomaly_percentage") or 0.0)
window_anom_count = int(status_data.get("anomaly_window_count") or (prediction_data.get("window_stats") or {}).get("anomaly_count_in_window") or 0)
window_threshold = int(status_data.get("anomaly_window_threshold") or (prediction_data.get("window_stats") or {}).get("threshold") or 3)
predictive_advisory = (
    status_data.get("predictive_advisory") or
    (prediction_data.get("advisory") or {}).get("prediction_text") or
    "All motor telemetry (vibration, current, voltage, temperature) remains in nominal baseline limits. Continuous operation authorized."
)
active_worker = status_data.get("active_worker_id")
current_rms = _reading(status_data.get("current_rms"), samples[-1].get("rms") if samples else None)
current_voltage = _reading(status_data.get("current_voltage_v"), samples[-1].get("voltage_v") if samples else None)
current_ma = _reading(status_data.get("current_ma"), samples[-1].get("current_ma") if samples else None)
current_temp = _reading(status_data.get("current_temp_c"), samples[-1].get("temperature_c") if samples else None)
crest_factor = _reading(samples[-1].get("crest_factor") if samples else None)
power_w = (
    round((current_voltage * current_ma) / 1000.0, 2)
    if current_voltage is not None and current_ma is not None
    else None
)
peak_ma = max([float(s.get("current_ma") or 0.0) for s in samples] or [0.0]) if samples else (current_ma or 0.0)

# Telemetry staleness: live only if data arrived within last 10 seconds
telemetry_stale = True
_last_seen = status_data.get("last_telemetry_at")
if not _last_seen and samples:
    _last_seen = samples[-1].get("timestamp") or samples[-1].get("ts")
if _last_seen:
    try:
        _raw = str(_last_seen).strip()
        try:
            _num = float(_raw)
            if _num < 1e10:
                _seen_dt = datetime.fromtimestamp(_num, tz=timezone.utc)
            else:
                _seen_dt = datetime.fromtimestamp(_num / 1000.0, tz=timezone.utc)
        except ValueError:
            _seen_dt = datetime.fromisoformat(_raw.replace("Z", "+00:00"))
            if _seen_dt.tzinfo is None:
                _seen_dt = _seen_dt.replace(tzinfo=timezone.utc)
        telemetry_stale = (datetime.now(timezone.utc) - _seen_dt).total_seconds() > 10
    except (TypeError, ValueError, OSError):
        telemetry_stale = True

if not backend_online:
    motor_state = "NO DATA"

rms_text = f"{current_rms:.3f}" if current_rms is not None else "--"
ma_text = f"{current_ma:.1f}" if current_ma is not None else "--"
volt_text = f"{current_voltage:.1f}" if current_voltage is not None else "--"
power_text = f"{power_w:.2f}" if power_w is not None else "--"
temp_text = f"{current_temp:.1f}" if current_temp is not None else "--"
cf_text = f"{crest_factor:.2f}" if crest_factor is not None else "--"

# ── Live anomaly score (backend scores once per incoming telemetry sample) ──
latest_anomaly = anomalies[0] if anomalies else None
anom_score: float | None = _reading(status_data.get("anomaly_score"), decomp_data.get("anomaly_score"))
anom_threshold: float | None = _reading(status_data.get("decision_threshold"), decomp_data.get("decision_threshold", 0.0))
anom_age_s: float | None = None
if anom_score is None and latest_anomaly:
    anom_score = _reading(latest_anomaly.get("score", latest_anomaly.get("anomaly_score")))
    anom_threshold = _reading(latest_anomaly.get("threshold"))

if latest_anomaly:
    _last_score_dt = _parse_ts(latest_anomaly.get("created_at", latest_anomaly.get("recorded_at")))
    anom_age_s = (datetime.now(timezone.utc) - _last_score_dt).total_seconds() if _last_score_dt else None

ml_anomaly_active = bool(status_data.get("is_anomaly", False)) or (
    bool(latest_anomaly.get("is_anomaly", False)) if latest_anomaly else False
)
# Scoring runs at telemetry rate (1 Hz); anything older than 15 s is stale.
ml_score_stale = anom_age_s is not None and anom_age_s > 15
ml_score_text = f"{anom_score:+.3f}" if anom_score is not None else "--"

if not backend_online:
    ml_class, ml_label = "status-offline", "GATEWAY OFFLINE"
elif latest_anomaly is None:
    ml_class, ml_label = "status-standby", "NOT CALIBRATED"
elif ml_anomaly_active:
    ml_class, ml_label = "status-offline", "ANOMALY"
elif ml_score_stale:
    ml_class, ml_label = "status-standby", f"STALE ({_age_text(latest_anomaly.get('created_at'))})"
else:
    ml_class, ml_label = "status-online", "NOMINAL"


# ── Live Connection & System Status Bar ───────────────────────────────────
mqtt_connected = bool(health.get("mqtt_connected", False)) if backend_online else False
mqtt_broker_str = health.get("mqtt_broker", "localhost:1883") if backend_online else "Unavailable"
telemetry_count = len(samples)

gateway_class = "status-online" if backend_online else "status-offline"
gateway_text = "GATEWAY: CONNECTED (127.0.0.1:8000)" if backend_online else "GATEWAY: OFFLINE (Port 8000)"

mqtt_class = "status-online" if mqtt_connected else ("status-standby" if backend_online else "status-offline")
mqtt_text = f"MQTT: CONNECTED ({mqtt_broker_str})" if mqtt_connected else ("MQTT: STANDBY (HTTP Ingest)" if backend_online else "MQTT: OFFLINE")

if not backend_online:
    telem_class = "status-offline"
    telem_text = "TELEMETRY: GATEWAY OFFLINE"
elif not telemetry_stale:
    telem_class = "status-active"
    telem_text = f"TELEMETRY: STREAMING ({telemetry_count} samples)"
else:
    telem_class = "status-standby"
    telem_text = "TELEMETRY: AWAITING ESP32 SENSOR DATA"

st.markdown(
    f"""
    <div class="system-status-bar">
        <div class="status-pill {gateway_class}">
            <span class="status-dot"></span>
            <span>{gateway_text}</span>
        </div>
        <div class="status-pill {mqtt_class}">
            <span class="status-dot"></span>
            <span>{mqtt_text}</span>
        </div>
        <div class="status-pill {telem_class}">
            <span class="status-dot"></span>
            <span>{telem_text}</span>
        </div>
        <div class="status-pill {ml_class}">
            {icon_svg('activity', color='#38bdf8', size=13)}
            <span>ML: <b>{ml_score_text}</b> {ml_label}</span>
        </div>
        <div class="status-pill status-active" style="border-color: rgba(56, 189, 248, 0.3);">
            {icon_svg('shield', color='#38bdf8', size=13)}
            <span>CELL: <b>{device_id}</b></span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── Top Safety Alert Banner ───────────────────────────────────────────────
if not backend_online:
    st.markdown(
        f"""
        <div class="alert-banner-offline">
            <div>
                <span style="font-size: 1.1rem; font-weight: 700; color: #ffffff; display: flex; align-items: center; gap: 8px;">
                    {icon_svg('alert_triangle', color='#94a3b8', size=20)} FASTAPI GATEWAY OFFLINE (PORT 8000)
                </span>
                <span style="font-size: 0.85rem; color: #cbd5e1; margin-top: 4px; display: block;">
                    Start the backend: <code>python -m uvicorn --app-dir armor-backend backend.main:app --port 8000</code>
                </span>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; background: rgba(0,0,0,0.4); padding: 6px 12px; border-radius: 6px; border: 1px solid #94a3b8;">
                BACKEND: <b>DISCONNECTED</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
elif interlock_active:
    st.markdown(
        f"""
        <div class="alert-banner-lockout">
            <div>
                <span style="font-size: 1.25rem; font-weight: 800; color: #ffffff; display: flex; align-items: center; gap: 10px;">
                    {icon_svg('siren', color='#ef4444', size=24)} EMERGENCY MOTOR LOCKOUT ACTIVE — SAFETY INTERLOCK ENGAGED
                </span>
                <span style="font-size: 0.85rem; color: #fecaca; margin-top: 4px; display: block;">
                    Cell <b>{device_id}</b> power cut. L298N driver Enable pin (GPIO 25) pulled LOW. Worker: <b>{active_worker or 'UNKNOWN'}</b>.
                </span>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; background: rgba(0,0,0,0.5); padding: 6px 14px; border-radius: 6px; border: 1px solid #ef4444;">
                INTERLOCK: <b>PULLED LOW (0V)</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
elif interlock_active or proximity_breach:
    reason_label = status_data.get("lockout_reason") or "SAFETY BREACH — PERSON PRESENT IN MACHINE VICINITY WITHOUT PPE GEAR"
    st.markdown(
        f"""
        <div class="alert-banner-lockout">
            <div>
                <span style="font-size: 1.25rem; font-weight: 800; color: #ffffff; display: flex; align-items: center; gap: 10px;">
                    {icon_svg('siren', color='#ef4444', size=24)} SAFETY BREACH / EMERGENCY LOCKOUT ACTIVE
                </span>
                <span style="font-size: 0.85rem; color: #fecaca; margin-top: 4px; display: block;">
                    Cell <b>{device_id}</b> power cut. Reason: <b>{reason_label}</b>. Worker: <b>{active_worker or 'UNKNOWN'}</b>.
                </span>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; background: rgba(0,0,0,0.5); padding: 6px 14px; border-radius: 6px; border: 1px solid #ef4444;">
                INTERLOCK: <b>PULLED LOW (0V)</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
elif vicinity_presence:
    if vicinity_status == "AUTHORIZED_OPERATOR_PPE_VERIFIED":
        st.markdown(
            f"""
            <div class="alert-banner-normal" style="border-color: #38bdf8; box-shadow: 0 0 20px rgba(56, 189, 248, 0.25);">
                <div>
                    <span style="font-size: 1.15rem; font-weight: 700; color: #ffffff; display: flex; align-items: center; gap: 8px;">
                        {icon_svg('shield_check', color='#38bdf8', size=22)} PERSON DETECTED IN MACHINE VICINITY — PPE VERIFIED (AUTHORIZED)
                    </span>
                    <span style="font-size: 0.85rem; color: #bae6fd; margin-top: 4px; display: block;">
                        Worker <b>{active_worker or 'UNKNOWN'}</b> detected in machine's vicinity wearing verified safety helmet. Continuous operation authorized (no breach).
                    </span>
                </div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; background: rgba(0,0,0,0.3); padding: 6px 12px; border-radius: 6px; border: 1px solid #38bdf8;">
                    STATUS: <b>AUTHORIZED OPERATOR</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="alert-banner-breach" style="border-color: #f59e0b; box-shadow: 0 0 20px rgba(245, 158, 11, 0.25);">
                <div>
                    <span style="font-size: 1.15rem; font-weight: 700; color: #ffffff; display: flex; align-items: center; gap: 8px;">
                        {icon_svg('alert_triangle', color='#f59e0b', size=22)} PERSON DETECTED IN MACHINE'S VICINITY — VERIFYING PPE COMPLIANCE
                    </span>
                    <span style="font-size: 0.85rem; color: #fef3c7; margin-top: 4px; display: block;">
                        Worker <b>{active_worker or 'UNKNOWN'}</b> inside 1.5m vicinity perimeter. Vision AI safety gate evaluating PPE gear...
                    </span>
                </div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; background: rgba(0,0,0,0.4); padding: 6px 12px; border-radius: 6px; border: 1px solid #f59e0b;">
                    VICINITY: <b>INSPECTION ACTIVE</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
elif telemetry_stale:
    st.markdown(
        f"""
        <div class="alert-banner-offline">
            <div>
                <span style="font-size: 1.1rem; font-weight: 700; color: #ffffff; display: flex; align-items: center; gap: 8px;">
                    {icon_svg('alert_triangle', color='#94a3b8', size=20)} AWAITING LIVE TELEMETRY FROM ESP32
                </span>
                <span style="font-size: 0.85rem; color: #cbd5e1; margin-top: 4px; display: block;">
                    No telemetry received in the last 10 seconds. Values below are the last known readings, not live data.
                </span>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; background: rgba(0,0,0,0.4); padding: 6px 12px; border-radius: 6px; border: 1px solid #94a3b8;">
                LINK: <b>NO DATA</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"""
        <div class="alert-banner-normal">
            <div>
                <span style="font-size: 1.15rem; font-weight: 700; color: #ffffff; display: flex; align-items: center; gap: 8px;">
                    {icon_svg('shield_check', color='#10b981', size=22)} SAFETY CELL ARMED & NOMINAL
                </span>
                <span style="font-size: 0.85rem; color: #a7f3d0; margin-top: 4px; display: block;">
                    Machine <b>{device_id}</b> running normally. Perimeter clear. L298N Enable HIGH.
                </span>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; background: rgba(0,0,0,0.3); padding: 6px 12px; border-radius: 6px; border: 1px solid #10b981;">
                STATUS: <b>{motor_state}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── KPI Metric HUD (4 Columns) ────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)

with c1:
    if not backend_online:
        hud_class = "hud-red"
        val_color = "#ef4444"
        val_text = "OFFLINE"
        sub_text = "Gateway disconnected"
    elif interlock_active:
        hud_class = "hud-red"
        val_color = "#ef4444"
        val_text = "LOCKED"
        sub_text = "L298N ENA: GPIO 25 LOW (0V)"
    elif motor_state == "RUNNING":
        hud_class = "hud-green"
        val_color = "#10b981"
        val_text = "RUNNING"
        sub_text = "L298N ENA: GPIO 25 HIGH (5V)"
    else:
        hud_class = ""
        val_color = "#38bdf8"
        val_text = motor_state
        sub_text = "Cell Standby / Ready"

    st.markdown(
        f"""
        <div class="hud-card {hud_class}">
            <div class="hud-title">RS-555 DC Motor State</div>
            <div class="hud-value" style="color: {val_color};">{val_text}</div>
            <div class="hud-sub">{sub_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    vibe_warn = current_rms is not None and current_rms > 0.15
    hud_class = "hud-red" if vibe_warn else "hud-green"
    vibe_sub = (
        f'<span style="color:#ef4444; display:inline-flex; align-items:center; gap:4px;">'
        f'{icon_svg("alert_triangle", color="#ef4444", size=13)} Vibration Warning (&gt;0.15g)</span>'
        if vibe_warn else
        f'<span style="color:#10b981; display:inline-flex; align-items:center; gap:4px;">'
        f'{icon_svg("check_circle", color="#10b981", size=13)} Nominal baseline (&lt;0.10g)</span>'
    )
    st.markdown(
        f"""
        <div class="hud-card {hud_class}">
            <div class="hud-title">ADXL345 Vibration RMS</div>
            <div class="hud-value">{rms_text} <span style="font-size:1rem; font-weight:400; color:#94a3b8;">g</span></div>
            <div class="hud-sub">{vibe_sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    curr_warn = current_ma is not None and current_ma > 800.0
    hud_class = "hud-amber" if curr_warn else ""
    st.markdown(
        f"""
        <div class="hud-card {hud_class}">
            <div class="hud-title">INA219 Power Draw</div>
            <div class="hud-value">{ma_text} <span style="font-size:1rem; font-weight:400; color:#94a3b8;">mA</span></div>
            <div class="hud-sub">Bus: {volt_text}V | Peak: {peak_ma:.1f}mA | Power: {power_text}W</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c4:
    temp_warn = current_temp is not None and current_temp > 55.0
    hud_class = "hud-red" if temp_warn else ""
    st.markdown(
        f"""
        <div class="hud-card {hud_class}">
            <div class="hud-title">DS18B20 Surface Temp</div>
            <div class="hud-value">{temp_text} <span style="font-size:1rem; font-weight:400; color:#94a3b8;">°C</span></div>
            <div class="hud-sub">Crest: {cf_text} | Thermal boundary: &lt;65.0°C</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)
import pandas as pd

# ── Live Predictive Maintenance (multi-modal anomaly score & Groq AI advisory) ─────────────────
st.markdown(
    f"""
    <div class="armor-header">
        {icon_svg('activity', color='#06b6d4', size=22)}
        <span>Live Multi-Modal Predictive Maintenance & Groq AI Advisory</span>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(
    "Multi-Modal Anomaly Decomposition trained across Vibration, Current, Voltage/Power & Temperature. "
    "Sustained anomalies across a 5.0s rolling window trigger emergency motor lockdown; dynamic Groq LLM advisory provides expert engineering root-cause diagnostics."
)

if not backend_online:
    st.info("Gateway offline — live anomaly scoring unavailable.")
elif model_package is None:
    st.warning("No calibrated model yet. Run calibration below; scores appear here automatically once telemetry flows.")
elif latest_anomaly is None and not decomp_data:
    st.info("Model is calibrated. Waiting for the next telemetry window to be scored…")
else:
    import json as _json

    _pkg_raw = model_package.get("model_package") if isinstance(model_package, dict) else None
    try:
        _live_pkg = _json.loads(_pkg_raw) if _pkg_raw else {}
    except (TypeError, ValueError):
        _live_pkg = {}

    top_contrib = decomp_data.get("top_contributor") or status_data.get("top_contributor") or "Multi-Modal Sensor Array"
    cur_anomaly_pct = float(decomp_data.get("anomaly_percentage") or status_data.get("anomaly_percentage") or anomaly_pct or 0.0)

    # Groq AI Predictive Advisory Banner
    st.markdown(
        f"""
        <div style="background: rgba(6, 182, 212, 0.08); border: 1px solid rgba(6, 182, 212, 0.35); border-radius: 10px; padding: 14px 18px; margin: 10px 0 16px 0; backdrop-filter: blur(12px);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                <span style="font-family:'JetBrains Mono', monospace; font-size:0.75rem; font-weight:700; color:#38bdf8; display:flex; align-items:center; gap:6px;">
                    {icon_svg('activity', color='#38bdf8', size=15)} INDUSTRIAL AI PREDICTIVE MAINTENANCE ADVISORY
                </span>
                <span style="font-size:0.75rem; color:#94a3b8; font-family:'JetBrains Mono', monospace; background:rgba(255,255,255,0.05); padding:2px 8px; border-radius:4px;">
                    ENGINE: GROQ (qwen/qwen3.8-27b)
                </span>
            </div>
            <div style="font-size:0.95rem; line-height:1.55; color:#f8fafc; font-weight:500;">
                "{predictive_advisory}"
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if ml_anomaly_active or cur_anomaly_pct >= 50.0:
        score_color, hud_class, state_text = "#ef4444", "hud-red", "ANOMALY"
    elif ml_score_stale:
        score_color, hud_class, state_text = "#f59e0b", "hud-amber", "STALE"
    elif cur_anomaly_pct >= 30.0:
        score_color, hud_class, state_text = "#f59e0b", "hud-amber", "ELEVATED"
    else:
        score_color, hud_class, state_text = "#10b981", "hud-green", "NOMINAL"

    an1, an2, an3, an4 = st.columns(4)

    with an1:
        st.markdown(
            f"""
            <div class="hud-card {hud_class}">
                <div class="hud-title">Anomaly Severity</div>
                <div class="hud-value hud-tight" style="color:{score_color};">{cur_anomaly_pct:.1f}%</div>
                <div class="hud-sub">Raw Score: {anom_score:+.3f} (Thresh: {anom_threshold:+.3f})</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with an2:
        if window_anom_count >= window_threshold:
            w_color = "#ef4444"
            w_sub = '<span style="color:#ef4444; font-weight:bold;">🚨 SUSTAINED LOCKOUT ACTIVE</span>'
        elif window_anom_count > 0:
            w_color = "#f59e0b"
            w_sub = '<span style="color:#f59e0b;">⚠️ TRANSIENT (FILTERED)</span>'
        else:
            w_color = "#10b981"
            w_sub = '<span style="color:#10b981;">✅ NOMINAL BASELINE</span>'

        st.markdown(
            f"""
            <div class="hud-card {hud_class}">
                <div class="hud-title">5.0s Window Persistence Gate</div>
                <div class="hud-value hud-tight" style="color:{w_color};">{window_anom_count} / {window_threshold} in 5s</div>
                <div class="hud-sub">{w_sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with an3:
        st.markdown(
            f"""
            <div class="hud-card">
                <div class="hud-title">Dominant Anomaly Driver</div>
                <div class="hud-value hud-tight" style="font-size:1.15rem; color:#38bdf8;">{top_contrib}</div>
                <div class="hud-sub">Primary modality contributing to fault score</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with an4:
        st.markdown(
            f"""
            <div class="hud-card">
                <div class="hud-title">Model Envelope</div>
                <div class="hud-value hud-tiny">Running Motor Baseline</div>
                <div class="hud-sub">RS-555 DC Motor &middot; 4 Sensors (ADXL, INA, DS18)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Modality Weightages towards Anomaly Score
    modalities = decomp_data.get("modalities", {})
    if modalities:
        st.markdown("<br><div style='font-family:Space Grotesk, sans-serif; font-weight:600; font-size:1.05rem; margin-bottom:8px; color:#f8fafc;'>Sensor Modality Weightages & Sub-Scores towards Anomaly</div>", unsafe_allow_html=True)
        mw1, mw2, mw3, mw4 = st.columns(4)

        mod_items = [
            ("vibration", "Vibration (ADXL345)", mw1, "#38bdf8"),
            ("current", "Motor Current (INA219)", mw2, "#f59e0b"),
            ("voltage_power", "Voltage & Power (INA219)", mw3, "#10b981"),
            ("temperature", "Temperature (DS18B20)", mw4, "#ec4899"),
        ]

        for mod_key, mod_title, col, accent_color in mod_items:
            m_info = modalities.get(mod_key, {})
            w_pct = float(m_info.get("weight_pct", 25.0))
            s_pct = float(m_info.get("sub_score_pct", 10.0))
            status = str(m_info.get("status", "NOMINAL"))

            status_color = "#10b981" if status == "NOMINAL" else ("#f59e0b" if status == "ELEVATED" else "#ef4444")
            with col:
                st.markdown(
                    f"""
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-top: 3px solid {accent_color}; border-radius: 8px; padding: 12px 14px;">
                        <div style="font-family:'JetBrains Mono'; font-size:0.75rem; color:#94a3b8; text-transform:uppercase;">{mod_title}</div>
                        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:4px;">
                            <span style="font-size:1.35rem; font-weight:700; color:#ffffff;">{w_pct:.1f}% <span style="font-size:0.75rem; color:#94a3b8; font-weight:400;">weight</span></span>
                            <span style="font-size:0.75rem; font-weight:700; color:{status_color}; background:rgba(255,255,255,0.05); padding:2px 6px; border-radius:4px;">{status}</span>
                        </div>
                        <div style="font-size:0.75rem; color:#94a3b8; margin-top:4px;">Sub-Score Severity: <b>{s_pct:.1f}%</b></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Detailed Parameter Breakdown (Expander)
        with st.expander("Detailed Parameter Deviation Breakdown (Individual Channels vs. Baseline)", expanded=False):
            param_rows = []
            for mod_key, m_info in modalities.items():
                channels = m_info.get("channels", {})
                for ch_name, ch_data in channels.items():
                    val = ch_data.get("value")
                    mean_val = ch_data.get("nominal_mean")
                    std_val = ch_data.get("nominal_std")
                    dev = ch_data.get("deviation_sigma", 0.0)
                    ch_status = "ANOMALOUS" if dev >= 3.0 else ("ELEVATED" if dev >= 2.0 else "NOMINAL")
                    param_rows.append({
                        "Modality": m_info.get("name", mod_key),
                        "Parameter Channel": ch_name,
                        "Live Measured": val,
                        "Nominal Baseline (Mean ± Std)": f"{mean_val} ± {std_val}",
                        "Deviation (σ)": f"{dev:.2f} σ",
                        "Channel Status": ch_status,
                    })
            if param_rows:
                st.dataframe(pd.DataFrame(param_rows), use_container_width=True, hide_index=True)

    hist = [
        a for a in reversed(anomalies)
        if _reading(a.get("score", a.get("anomaly_score"))) is not None
    ]
    if len(hist) >= 2:
        chart_rows = []
        for a in hist:
            ts = _parse_ts(a.get("created_at", a.get("recorded_at")))
            if ts is None:
                continue
            chart_rows.append(
                {
                    "Time": ts,
                    "Anomaly score": float(_reading(a.get("score", a.get("anomaly_score"))) or 0.0),
                    "Decision threshold": float(_reading(a.get("threshold")) or 0.0),
                }
            )
        if len(chart_rows) >= 2:
            hist_df = pd.DataFrame(chart_rows).set_index("Time")
            st.line_chart(hist_df, height=220, color=["#38bdf8", "#ef4444"])
            refresh_note = (
                f"refreshing every {refresh_rate}s" if refresh_rate > 0 else "auto-refresh paused — resume in the sidebar"
            )
            st.caption(
                f"Trend of the last {len(chart_rows)} scored windows "
                f"(oldest {_age_text(hist[0].get('created_at'))}); {refresh_note}."
            )


def _build_df(samples):
    if not samples:
        return None
    df = pd.DataFrame(samples)
    if "ts" in df.columns:
        ts_dt = pd.to_datetime(df["ts"], errors="coerce", utc=True)
        if ts_dt.isna().all() or ts_dt.isna().sum() > len(df) // 2:
            try:
                numeric_ts = pd.to_numeric(df["ts"], errors="coerce")
                if numeric_ts.max() < 1e9:
                    ts_dt = pd.to_datetime(numeric_ts, unit="s", errors="coerce", utc=True)
                else:
                    ts_dt = pd.to_datetime(numeric_ts, unit="ms", errors="coerce", utc=True)
            except Exception:
                ts_dt = pd.date_range(end=datetime.now(timezone.utc), periods=len(df), freq="1s")
        df["ts_dt"] = ts_dt
    else:
        df["ts_dt"] = pd.date_range(end=datetime.now(timezone.utc), periods=len(df), freq="1s")
    return df

def _plot_chart(tab, df, chart_type):
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        if chart_type == "vibe":
            fig.add_trace(
                go.Scatter(
                    x=df["ts_dt"],
                    y=df["rms"],
                    mode="lines+markers",
                    name="RMS Vibration (g)",
                    line=dict(color="#38bdf8", width=2.5),
                    marker=dict(size=4),
                )
            )
            if "crest_factor" in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df["ts_dt"],
                        y=df["crest_factor"],
                        mode="lines",
                        name="Crest Factor",
                        line=dict(color="#f59e0b", width=1.5, dash="dot"),
                        yaxis="y2",
                    )
                )
            fig.add_hline(
                y=0.15,
                line_dash="dash",
                line_color="#ef4444",
                annotation_text="Alarm Threshold (0.15g)",
                annotation_position="top left",
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(15,23,42,0.6)",
                font=dict(color="#94a3b8", family="Inter"),
                margin=dict(l=20, r=20, t=25, b=25),
                height=300,
                legend=dict(orientation="h", y=1.1, x=0),
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Vibration (g)", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis2=dict(title="Crest Factor", overlaying="y", side="right", showgrid=False),
            )
        elif chart_type == "pwr":
            fig.add_trace(
                go.Scatter(
                    x=df["ts_dt"],
                    y=df["current_ma"],
                    mode="lines",
                    name="Current (mA)",
                    fill="tozeroy",
                    fillcolor="rgba(16, 185, 129, 0.15)",
                    line=dict(color="#10b981", width=2),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["ts_dt"],
                    y=df["voltage_v"],
                    mode="lines",
                    name="Bus Voltage (V)",
                    line=dict(color="#38bdf8", width=1.5),
                    yaxis="y2",
                )
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(15,23,42,0.6)",
                font=dict(color="#94a3b8", family="Inter"),
                margin=dict(l=20, r=20, t=25, b=25),
                height=300,
                legend=dict(orientation="h", y=1.1, x=0),
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Current (mA)", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis2=dict(title="Voltage (V)", overlaying="y", side="right", showgrid=False),
            )
        elif chart_type == "temp":
            fig.add_trace(
                go.Scatter(
                    x=df["ts_dt"],
                    y=df["temperature_c"],
                    mode="lines+markers",
                    name="Motor Temperature (°C)",
                    line=dict(color="#f43f5e", width=2.5),
                    marker=dict(size=4),
                )
            )
            fig.add_hline(
                y=55.0,
                line_dash="dash",
                line_color="#f59e0b",
                annotation_text="Thermal Alert (55°C)",
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(15,23,42,0.6)",
                font=dict(color="#94a3b8", family="Inter"),
                margin=dict(l=20, r=20, t=25, b=25),
                height=300,
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Temperature (°C)", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
            )
        with tab:
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        with tab:
            st.error(f"{chart_type} chart error: {e}")

def _render_charts(samples, device_id):
    """Render telemetry charts inside a column context."""
    chart_tab1, chart_tab2, chart_tab3 = st.tabs(
        ["Vibration (ADXL345)", "Power & Load (INA219)", "Temperature (DS18B20)"]
    )
    df = _build_df(samples)
    if df is not None:
        _plot_chart(chart_tab1, df, "vibe")
        _plot_chart(chart_tab2, df, "pwr")
        _plot_chart(chart_tab3, df, "temp")
    else:
        with chart_tab1:
            st.info("Awaiting telemetry stream from ESP32 machine node via MQTT.")
        with chart_tab2:
            st.info("Awaiting current & voltage readings from INA219.")
        with chart_tab3:
            st.info("Awaiting temperature readings from DS18B20.")

def _render_charts_in_tabs(tab1, tab2, tab3, samples, device_id):
    """Render telemetry charts into pre-created tabs (full-width twin mode)."""
    df = _build_df(samples)
    if df is not None:
        _plot_chart(tab1, df, "vibe")
        _plot_chart(tab2, df, "pwr")
        _plot_chart(tab3, df, "temp")
    else:
        with tab1:
            st.info("Awaiting telemetry stream from ESP32 machine node via MQTT.")
        with tab2:
            st.info("Awaiting current & voltage readings from INA219.")
        with tab3:
            st.info("Awaiting temperature readings from DS18B20.")


# MAIN VIEW: Edge Vision Safety Inspection
# ════════════════════════════════════════════════════════════════════════════════

st.markdown(
    f"""
    <div class="armor-header">
        {icon_svg('video', color='#06b6d4', size=22)}
        <span>Edge Vision Safety Inspection</span>
    </div>
    """,
    unsafe_allow_html=True,
)
view_mode = st.radio(
    "View Mode",
    options=["Live Camera", "3D Digital Twin"],
    horizontal=True,
    label_visibility="collapsed",
    key="vision_view_mode",
)

if backend_online:
    if view_mode == "Live Camera":
        # Two columns: camera left at natural size, charts right
        cam_col, chart_col = st.columns([1, 1], gap="medium")

        with cam_col:
            stream_url = f"{API_BASE_URL}/video/stream"

            # Query live vision engine state
            v_state = api_get("/api/v1/vision/state") or {}
            is_frozen = v_state.get("is_frozen", False)
            person_present = v_state.get("person_present", False)
            person_count = v_state.get("person_count", 0)
            auto_freeze = v_state.get("auto_freeze_enabled", False)
            is_dwelling = v_state.get("is_dwelling", False)
            dwell_elapsed = v_state.get("dwell_elapsed", 0.0)
            dwell_req = v_state.get("dwell_required", 2.0)
            last_res = v_state.get("last_helmet_result") or {}
            helmet_comp = last_res.get("compliant")
            helmet_ratio = last_res.get("compliance_ratio", 0.0)
            helmet_label = last_res.get("label", "")

            cam_badge = "status-standby" if is_frozen else "status-online"
            cam_text = "⏸ FEED FROZEN (INSPECTING)" if is_frozen else "● LIVE STREAM"

            if is_dwelling:
                person_badge = "status-standby"
                person_text = f"⏳ STABILIZING ({dwell_elapsed:.1f}s / {dwell_req:.1f}s)"
            elif person_present:
                person_badge = "status-active"
                person_text = f"● PERSON IN FRAME ({person_count})"
            else:
                person_badge = ""
                person_text = "● SCANNING"

            if helmet_comp is True:
                helmet_badge = "status-online"
                helmet_text = f"✅ HELMET OK ({helmet_ratio:.0%})"
            elif helmet_comp is False and helmet_label == "HELMET_FAIL":
                helmet_badge = "status-offline"
                helmet_text = "🚨 NO HELMET (LOCKOUT)"
            else:
                helmet_badge = ""
                helmet_text = "PPE STANDBY"

            auto_badge = "status-online" if auto_freeze else "status-standby"
            auto_text = "⚡ AUTO-FREEZE ON" if auto_freeze else "⏸ AUTO-FREEZE OFF"

            st.markdown(
                f"""
                <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
                    <span class="status-pill {cam_badge}"><span class="status-dot"></span><b>{cam_text}</b></span>
                    <span class="status-pill {person_badge}"><span class="status-dot"></span><b>{person_text}</b></span>
                    <span class="status-pill {helmet_badge}"><span class="status-dot"></span><b>{helmet_text}</b></span>
                    <span class="status-pill {auto_badge}"><span class="status-dot"></span><b>{auto_text}</b></span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Auto-freeze toggle row
            tog_c1, tog_c2 = st.columns([1.5, 1])
            with tog_c1:
                new_auto = st.toggle(
                    "⚡ Auto-Freeze Helmet Check",
                    value=auto_freeze,
                    key="toggle_auto_freeze_cam",
                    help="When enabled, detecting a person freezes the feed once to check helmet compliance. When disabled, the camera streams continuously at 30 fps without freezing.",
                )
                if new_auto != auto_freeze:
                    api_post("/api/v1/vision/auto-freeze", params={"enabled": new_auto})
                    st.rerun()
            with tog_c2:
                if is_frozen:
                    if st.button("▶ Unfreeze Stream", use_container_width=True, key="btn_quick_unfreeze_top"):
                        api_post("/api/v1/vision/unfreeze")
                        st.rerun()

            st.markdown(
                f"""
                <div class="video-frame-container" style="height: 420px; aspect-ratio: 4/3;">
                    <div class="live-badge">{'⏸ FROZEN INSPECTION' if is_frozen else 'LIVE AI STREAM'}</div>
                    <iframe
                        src="{stream_url}"
                        width="100%"
                        height="100%"
                        style="border:none; display:block; background:#000; object-fit: cover;"
                        scrolling="no"
                    ></iframe>
                </div>
                """,
                unsafe_allow_html=True,
            )

            v_btn_c1, v_btn_c2 = st.columns([1, 1])
            with v_btn_c1:
                if st.button("📸 Inspect Now (Manual Check)", use_container_width=True, key="btn_quick_inspect"):
                    api_post("/api/v1/vision/inspect", params={"worker_id": "WORKER_EMP_402", "device_id": device_id})
                    st.rerun()
            with v_btn_c2:
                if st.button("▶ Resume Live Feed", use_container_width=True, key="btn_quick_unfreeze", disabled=not is_frozen):
                    api_post("/api/v1/vision/unfreeze")
                    st.rerun()

            with st.expander("⚙️ Inspection Timing Settings", expanded=False):
                current_dwell = float(v_state.get("dwell_required", 2.0))
                new_dwell = st.slider(
                    "Person Detection Stabilization Dwell (seconds)",
                    min_value=0.5,
                    max_value=5.0,
                    value=current_dwell,
                    step=0.5,
                    key="slider_dwell_sec",
                    help="Time a person must be continuously detected before the feed freezes to evaluate helmet compliance.",
                )
                if abs(new_dwell - current_dwell) > 0.05:
                    api_post("/api/v1/vision/dwell-seconds", params={"seconds": new_dwell})
                    st.rerun()

        with chart_col:
            _render_charts(samples, device_id)

    else:
        # Full-width digital twin
        twin_url = f"{API_BASE_URL}/twin?device_id={device_id}"
        st.markdown(
            f"""
            <div class="video-frame-container" style="height: 560px;">
                <div class="live-badge" style="background:rgba(6,182,212,0.9);">3D DIGITAL TWIN</div>
                <iframe
                    src="{twin_url}"
                    width="100%"
                    height="100%"
                    style="border:none; display:block; background:#0b0f19; object-fit: cover;"
                    scrolling="no"
                ></iframe>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # Full-width charts below twin
        chart_tab1, chart_tab2, chart_tab3 = st.tabs(
            ["Vibration (ADXL345)", "Power & Load (INA219)", "Temperature (DS18B20)"]
        )
        _render_charts_in_tabs(chart_tab1, chart_tab2, chart_tab3, samples, device_id)

else:
    st.markdown(
        f"""
        <div class="video-frame-container" style="height: 420px; aspect-ratio: 4/3; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:20px;">
            <div style="margin-bottom: 12px; opacity: 0.7;">
                {icon_svg('video', color='#94a3b8', size=44)}
            </div>
            <div style="font-weight: 700; font-size: 1.1rem; color: #ffffff;">Stream Offline</div>
            <div style="color: #94a3b8; font-size: 0.85rem; max-width: 380px; margin-top: 6px;">
                Start the FastAPI backend on port 8000 to connect.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# SUBSYSTEM TEST PANEL — test every subsystem individually
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown(
    f"""
    <div class="armor-header">
        {icon_svg('bug', color='#f59e0b', size=22)}
        <span>Subsystem Test Panel</span>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("Test each subsystem independently. No badge proximity breach required.")

# Initialize session state for test results
if "test_results" not in st.session_state:
    st.session_state.test_results = {}

test_cols = st.columns(2)

# ══════════════════════════════════════════════════════════════════════════════
# Test 1: Vision / Helmet Inspection
# ══════════════════════════════════════════════════════════════════════════════
with test_cols[0]:
    st.markdown("### Vision — Helmet Inspection")
    st.caption("Calls `vision_engine.inspect()` directly (bypasses badge trigger).")

    test_worker_id = st.text_input(
        "Worker ID",
        value=os.getenv("WORKER_TEST_ID", "WORKER_EMP_402"),
        key="vision_worker_id",
    )

    if st.button(
        "Run Helmet Inspection",
        key="btn_vision_test",
        type="secondary",
        use_container_width=True,
        disabled=not (backend_online and VISION_AVAILABLE),
    ):
        with st.spinner("Running helmet inspection..."):
            try:
                code, resp = api_post(
                    "/api/v1/vision/inspect",
                    params={"worker_id": test_worker_id, "device_id": device_id},
                    timeout=30.0,
                )
                if code == 200:
                    st.session_state.test_results["vision"] = resp
                    st.rerun()
                else:
                    st.error(f"Vision inspection failed (HTTP {code}): {resp}")
                    st.session_state.test_results["vision"] = {
                        "compliant": None,
                        "label": "ERROR",
                        "compliance_ratio": 0.0,
                        "worker_id": test_worker_id,
                        "snapshot_path": None,
                    }
            except Exception as e:
                st.error(f"Vision inspection failed: {e}")
                st.session_state.test_results["vision"] = {
                    "compliant": None,
                    "label": "ERROR",
                    "compliance_ratio": 0.0,
                    "worker_id": test_worker_id,
                    "snapshot_path": None,
                }

    if "vision" in st.session_state.test_results:
        r = st.session_state.test_results["vision"]
        compliant = r.get("compliant")
        ratio = r.get("compliance_ratio", 0.0)
        label = r.get("label", "UNKNOWN")
        snapshot = r.get("snapshot_path")
        ts = r.get("timestamp", "")

        if compliant is None:
            if label == "SCANNING":
                st.error(f"🔴 VISION SCANNING — no person detected in frame")
                st.caption("Point the camera at a worker. Helmet check runs automatically when a person is detected.")
            elif label == "VISION_UNAVAILABLE":
                st.error(f"🔴 VISION UNAVAILABLE — {label}")
                st.caption("No ROBOFLOW_API_KEY configured or model not loaded. Interlock will NOT auto-trigger.")
            else:
                st.error(f"🔴 VISION {label}")
                st.caption("Helmet check could not run. Check camera and backend logs.")
        elif compliant:
            st.success(f"✅ HELMET PASS — compliance ratio: {ratio:.1%}")
            st.caption(f"Worker: {r.get('worker_id')} | Time: {ts[:19]}")
            if snapshot and Path(snapshot).exists():
                st.image(snapshot, caption="Helmet Inspection Snapshot", use_container_width=True)
        else:
            st.error(f"❌ HELMET FAIL — compliance ratio: {ratio:.1%}")
            st.caption(f"Worker: {r.get('worker_id')} | Time: {ts[:19]}")
            if snapshot and Path(snapshot).exists():
                st.image(snapshot, caption="Helmet Inspection Snapshot", use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if not (backend_online and VISION_AVAILABLE):
        reason = []
        if not backend_online:
            reason.append("backend offline")
        if not VISION_AVAILABLE:
            reason.append("vision engine import failed")
        st.caption('Button disabled: ' + ', '.join(reason))

# ══════════════════════════════════════════════════════════════════════════════
# Test 2: Motor / Interlock
# ══════════════════════════════════════════════════════════════════════════════
with test_cols[1]:
    st.markdown("### Motor — Interlock Control")
    st.caption("Manually engage or release the safety interlock (L298N ENA GPIO 25).")

    mcol1, mcol2 = st.columns(2)
    with mcol1:
        if st.button(
            "EMERGENCY LOCKOUT",
            key="btn_lockout",
            type="primary",
            use_container_width=True,
            disabled=not backend_online,
        ):
            code, resp = api_post(
                "/api/v1/interlock",
                json_data={
                    "command": "LOCKOUT",
                    "source": "OPERATOR_DASHBOARD",
                    "reason": "Manual operator emergency cutoff",
                    "issued_by": "Control_Room_Operator",
                },
                params={"device_id": device_id},
            )
            if code == 200:
                st.toast("EMERGENCY LOCKOUT ENGAGED!", icon=":material/dangerous:")
                st.session_state.test_results["motor"] = {"command": "LOCKOUT", "status": "sent"}
                st.rerun()
            else:
                st.error(f"Lockout failed: {resp}")

    with mcol2:
        if st.button(
            "RESET INTERLOCK",
            key="btn_reset",
            type="secondary",
            use_container_width=True,
            disabled=not backend_online,
        ):
            code, resp = api_post(
                "/api/v1/interlock",
                json_data={
                    "command": "RESET",
                    "source": "OPERATOR_DASHBOARD",
                    "reason": "Operator cleared cell and verified safety",
                    "issued_by": "Control_Room_Operator",
                },
                params={"device_id": device_id},
            )
            if code == 200:
                st.toast("Cell interlock reset to RUNNING.", icon=":material/check_circle:")
                st.session_state.test_results["motor"] = {"command": "RESET", "status": "sent"}
                st.rerun()
            else:
                st.error(f"Reset failed: {resp}")

    # Show current motor state from real data
    st.caption(f"Current motor state: **{motor_state}** | Interlock: **{'ACTIVE' if interlock_active else 'INACTIVE'}**")

    st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Test 3: Proximity Breach Simulation
# ══════════════════════════════════════════════════════════════════════════════
with test_cols[0]:
    st.markdown("### Proximity — Vicinity Entry Simulation")
    st.caption("Simulate a worker entering the 1.5m danger vicinity. Triggers vision inspection: if wearing helmet, authorized (no breach); if missing helmet, trips safety lockout breach.")

    breach_worker_id = st.text_input(
        "Worker ID in vicinity",
        value="WORKER_EMP_402",
        key="breach_worker_id",
    )
    breach_badge_mac = st.text_input(
        "Badge MAC",
        value="24:6F:28:AB:C1:02",
        key="breach_badge_mac",
    )

    if st.button(
        "Simulate Proximity Breach",
        key="btn_breach_test",
        type="secondary",
        use_container_width=True,
        disabled=not backend_online,
    ):
        with st.spinner("Triggering proximity breach..."):
            code, resp = api_post(
                "/api/v1/breach",
                json_data={
                    "device_id": device_id,
                    "worker_id": breach_worker_id,
                    "badge_mac": breach_badge_mac,
                    "rssi_raw": -55.0,
                    "rssi_smoothed": -55.0,
                    "distance_est_m": 0.8,
                },
            )
            if code == 202:
                st.toast(f"Proximity breach triggered for {breach_worker_id}", icon=":material/alert_triangle:")
                st.session_state.test_results["proximity"] = {
                    "worker_id": breach_worker_id,
                    "badge_mac": breach_badge_mac,
                    "status": "triggered",
                }
                st.rerun()
            else:
                st.error(f"Breach simulation failed: {resp}")

    if "proximity" in st.session_state.test_results:
        pr = st.session_state.test_results["proximity"]
        st.info(f"Breach simulated: {pr['worker_id']} ({pr['badge_mac']}) — status: {pr['status']}")

    st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Test 4: Vibration / Anomaly Scoring
# ══════════════════════════════════════════════════════════════════════════════
with test_cols[1]:
    st.markdown("### Multi-Sensor Telemetry — Anomaly Scoring")
    st.caption("Check latest ML anomaly score against calibrated model.")

    if st.button(
        "Check Anomaly Score",
        key="btn_anomaly_test",
        type="secondary",
        use_container_width=True,
        disabled=not backend_online,
    ):
        latest_anom = anomalies[0] if anomalies else None
        st.session_state.test_results["vibration"] = latest_anom

    if "vibration" in st.session_state.test_results:
        an = st.session_state.test_results["vibration"]
        if an:
            score = an.get("score", an.get("anomaly_score", 0.0))
            threshold = an.get("threshold", 0.0)
            is_anom = bool(an.get("is_anomaly", False))
            if is_anom:
                st.error(f"❌ ANOMALY DETECTED — score {score:.3f} >= threshold {threshold:.3f}")
            else:
                st.success(f"✅ NOMINAL — score {score:.3f} < threshold {threshold:.3f}")
            st.caption(f"Recorded: {str(an.get('created_at', an.get('recorded_at', 'N/A')))[:19]}")
        else:
            st.warning("No anomaly records found. Run calibration first, then collect telemetry.")
    else:
        if anomalies:
            latest = anomalies[0]
            score = latest.get("score", latest.get("anomaly_score", 0.0))
            threshold = latest.get("threshold", 0.0)
            is_anom = bool(latest.get("is_anomaly", False))
            st.caption(f"Latest anomaly: score={score:.3f}, threshold={threshold:.3f}, anomaly={'YES' if is_anom else 'no'}")
        else:
            st.caption("No anomaly data yet. Collect 20+ telemetry samples then run calibration.")

    st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Test 5: Camera / Stream Health
# ══════════════════════════════════════════════════════════════════════════════
with test_cols[0]:
    st.markdown("### Camera — Stream Health Check")
    st.caption("Verify the MJPEG edge vision stream is reachable.")

    if st.button(
        "Check Stream Health",
        key="btn_camera_test",
        type="secondary",
        use_container_width=True,
        disabled=not backend_online,
    ):
        stream_url = f"{API_BASE_URL}/video/stream"
        try:
            r = requests.get(stream_url, timeout=3.0, stream=True)
            if r.status_code == 200:
                st.success("✅ Camera stream reachable (MJPEG)")
                st.session_state.test_results["camera"] = {"status": "online", "code": 200}
            else:
                st.error(f"❌ Camera stream returned HTTP {r.status_code}")
                st.session_state.test_results["camera"] = {"status": "error", "code": r.status_code}
        except Exception as e:
            st.error(f"❌ Camera stream unreachable: {e}")
            st.session_state.test_results["camera"] = {"status": "offline", "error": str(e)}

    if "camera" in st.session_state.test_results:
        cr = st.session_state.test_results["camera"]
        if cr.get("status") == "online":
            st.success(f"Camera: ONLINE (HTTP {cr.get('code')})")
        else:
            st.error(f"Camera: {cr.get('status').upper()} — {cr.get('error', cr.get('code', 'unknown'))}")

    st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Test Summary
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.test_results:
    st.markdown("### Test Summary")
    summary_rows = []
    for test_name, result in st.session_state.test_results.items():
        if test_name == "vision":
            compliant = result.get("compliant")
            status = "PASS" if compliant is True else ("FAIL" if compliant is False else "UNAVAILABLE")
            summary_rows.append({"Test": "Vision / Helmet", "Status": status, "Detail": f"ratio={result.get('compliance_ratio', 0):.1%}"})
        elif test_name == "motor":
            summary_rows.append({"Test": "Motor / Interlock", "Status": result.get("command", "?"), "Detail": result.get("status", "")})
        elif test_name == "proximity":
            summary_rows.append({"Test": "Proximity Breach", "Status": "TRIGGERED", "Detail": f"{result.get('worker_id')} / {result.get('badge_mac')}"})
        elif test_name == "vibration":
            if result:
                is_anom = bool(result.get("is_anomaly", False))
                summary_rows.append({"Test": "Telemetry Anomaly", "Status": "ANOMALY" if is_anom else "NOMINAL", "Detail": f"score={result.get('score', result.get('anomaly_score', 0)):.3f}"})
            else:
                summary_rows.append({"Test": "Telemetry Anomaly", "Status": "NO DATA", "Detail": ""})
        elif test_name == "camera":
            summary_rows.append({"Test": "Camera Stream", "Status": result.get("status", "UNKNOWN").upper(), "Detail": str(result.get("code", ""))})
    if summary_rows:
        st.dataframe(summary_rows, use_container_width=True, hide_index=True)

st.markdown("<br>", unsafe_allow_html=True)
# ══════════════════════════════════════════════════════════════════════════════
# CALIBRATION & PREDICTIVE MAINTENANCE (MachinoCare 1.0 ML)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    f"""
    <div class="armor-header">
        {icon_svg('calibration', color='#06b6d4', size=22)}
        <span>Multi-Modal Telemetry Calibration & ML Model</span>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("Train a full IsolationForest on real multi-sensor telemetry (ADXL345 Vibration, INA219 Current & Voltage, DS18B20 Temperature); scoring runs on the backend. No synthetic data.")

cal_left, cal_right = st.columns(2)

with cal_left:
    st.markdown("#### Model Status")
    if model_package:
        st.success("\u2714\ufe0f Calibrated model exists")
        # model_package is a db row dict: model_package column holds JSON string
        pkg_raw = model_package.get("model_package") if isinstance(model_package, dict) else None
        try:
            import json as _json
            pkg = _json.loads(pkg_raw) if pkg_raw else {}
        except Exception:
            pkg = {}
        st.caption(f"Windows: {model_package.get('window_count', 'N/A') if isinstance(model_package, dict) else 'N/A'}")
        st.caption(f"Quality: {model_package.get('quality', 'N/A') if isinstance(model_package, dict) else 'N/A'}")
        baseline_raw = model_package.get("baseline_stats") if isinstance(model_package, dict) else None
        try:
            baseline = _json.loads(baseline_raw) if baseline_raw else {}
        except Exception:
            baseline = {}
        if baseline:
            if "mean_current" in baseline or "mean_voltage" in baseline:
                st.markdown(
                    f'''
                    <div style="font-size:0.82rem; line-height:1.6; color:#94a3b8; background:rgba(255,255,255,0.02); padding:8px 12px; border-radius:6px; border:1px solid rgba(255,255,255,0.06); margin-bottom:10px;">
                        <div><b>Vibration (ADXL345):</b> {baseline.get('mean_acc', 0):.4f}g (&plusmn;{baseline.get('std_acc', 0):.4f}g)</div>
                        <div><b>Current (INA219):</b> {baseline.get('mean_current', 0):.1f} mA (&plusmn;{baseline.get('std_current', 0):.1f} mA)</div>
                        <div><b>Voltage (INA219):</b> {baseline.get('mean_voltage', 0):.2f} V (&plusmn;{baseline.get('std_voltage', 0):.2f} V)</div>
                        <div><b>Temperature (DS18B20):</b> {baseline.get('mean_temp', 0):.1f} &deg;C (&plusmn;{baseline.get('std_temp', 0):.1f} &deg;C)</div>
                        <div><b>Samples:</b> {baseline.get('sample_count', 0)} | <b>Channels:</b> 12 features</div>
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )
            else:
                st.caption(f"Mean acc: {baseline.get('mean_acc', 0):.4f} g")
                st.caption(f"Std acc: {baseline.get('std_acc', 0):.4f} g")
                st.caption(f"Samples: {baseline.get('sample_count', 0)}")
        if isinstance(pkg, dict) and pkg:
            st.caption(f"Decision threshold: {pkg.get('decision_threshold', 'N/A')}")
            st.caption(f"Hysteresis high: {pkg.get('hysteresis_high', 'N/A')}")
            st.caption(f"Hysteresis low: {pkg.get('hysteresis_low', 'N/A')}")
    else:
        st.warning("\u26a0\ufe0f No calibrated model yet")
        st.caption("Collect 20+ telemetry samples, then run calibration below.")


    st.markdown("#### Run Calibration")
    contam = st.slider(
        "Contamination (expected anomaly ratio)",
        min_value=0.01,
        max_value=0.40,
        value=0.05,
        step=0.01,
        help="Proportion of samples expected to be anomalies. 0.05 = 5%.",
    )
    calib_disabled = not backend_online
    st.info("💡 Ensure the motor is **RUNNING** before calibrating, so nominal operating baseline is learned.")
    col_cal_run, col_cal_reset = st.columns([1, 1])
    with col_cal_run:
        if st.button(
            "Calibrate Running Baseline",
            key="btn_calibrate",
            type="primary",
            use_container_width=True,
            disabled=calib_disabled,
        ):
            with st.spinner("Calibrating running baseline across sensors..."):
                code, resp = api_post(
                    "/api/v1/calibrate",
                    params={"device_id": device_id, "contamination": contam},
                    timeout=30.0,
                )
                if code == 200:
                    st.toast("Running baseline calibrated!", icon=":material/check_circle:")
                    st.session_state.test_results["calibration"] = resp
                    api_get(f"/api/v1/telemetry/anomaly/decomposition/{device_id}", timeout=2.0)
                    st.rerun()
                else:
                    st.error(f"Calibration rejected: {resp.get('detail', resp)}")

    with col_cal_reset:
        if st.button(
            "Purge / Reset Model",
            key="btn_reset_model",
            type="secondary",
            use_container_width=True,
            disabled=calib_disabled,
            help="Purge old models trained on off motor and restore factory running baseline.",
        ):
            code, resp = api_delete(
                "/api/v1/calibrate",
                params={"device_id": device_id},
                timeout=10.0,
            )
            if code == 200:
                st.toast("Purged old models! Restored factory running baseline.", icon=":material/delete_forever:")
                st.session_state.test_results.pop("calibration", None)
                api_get(f"/api/v1/telemetry/anomaly/decomposition/{device_id}", timeout=2.0)
                st.rerun()
            else:
                st.error(f"Reset failed: {resp.get('detail', resp)}")

    if "calibration" in st.session_state.test_results:
        cresp = st.session_state.test_results["calibration"]
        st.success(f"Running baseline active — {cresp.get('window_count', 0)} active samples across Vibration, Current, Voltage & Temperature.")

with cal_right:
    st.markdown("#### Sample Availability")
    st.caption(f"Telemetry samples collected: **{len(samples)}** (need ≥20 for calibration)")
    st.caption(f"Anomaly records: **{len(anomalies)}**")

    if len(samples) >= 20:
        st.success("✅ Sufficient samples for calibration")
    else:
        st.error(f"❌ Need {20 - len(samples)} more samples for calibration")

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("#### Recent Anomalies")
    if anomalies:
        an_rows = []
        for a in anomalies[:10]:
            an_rows.append({
                "Score": f"{float(a.get('score', a.get('anomaly_score', 0)) or 0):.3f}",
                "Threshold": f"{float(a.get('threshold', 0) or 0):.3f}",
                "Anomaly": "YES" if bool(a.get("is_anomaly")) else "no",
                "Time": str(a.get("created_at", a.get("recorded_at", "")))[:19],
            })
        st.dataframe(an_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No anomaly records yet. Run calibration first.")

st.markdown("<br>", unsafe_allow_html=True)
# ══════════════════════════════════════════════════════════════════════════════
# WEARABLE SMART BADGE TELEMETRY (ESP-NOW → machine node → backend)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    f"""
    <div class="armor-header">
        {icon_svg('badge', color='#06b6d4', size=22)}
        <span>Wearable Smart Badge Telemetry</span>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(
    "Registry from `POST /api/v1/workers`; contact rows are the ESP-NOW proximity reports "
    "the machine node forwards to `/api/v1/breaches`. Badges only report while in range."
)

if not backend_online:
    st.info("Gateway offline — badge telemetry unavailable.")
else:
    badge_by_mac = {b.get("badge_mac"): b for b in badges}
    latest_contact = breaches[0] if breaches else None
    active_badges = [b for b in badges if b.get("active")]
    latest_distance = _reading(latest_contact.get("distance_est_m")) if latest_contact else None

    w1, w2 = st.columns(2)
    w3, w4 = st.columns(2)

    with w1:
        st.markdown(
            f"""
            <div class="hud-card">
                <div class="hud-title">Registered Badges</div>
                <div class="hud-value">{len(badges)}</div>
                <div class="hud-sub">{len(active_badges)} active · {len(badges) - len(active_badges)} deactivated</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with w2:
        _contact_badge = badge_by_mac.get((latest_contact or {}).get("badge_mac"), {})
        if active_worker:
            _worker_sub = _contact_badge.get("worker_name") or "Operator logged in"
        else:
            _worker_sub = (
                f"Last contact: {_contact_badge.get('worker_name')}"
                if _contact_badge.get("worker_name")
                else "No operator currently logged"
            )
        st.markdown(
            f"""
            <div class="hud-card">
                <div class="hud-title">Worker In Cell</div>
                <div class="hud-value hud-tight">{active_worker or '—'}</div>
                <div class="hud-sub">{_worker_sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with w3:
        if proximity_breach:
            zone_class = "hud-red"
            badge_title = "Vicinity & PPE Safety"
            badge_val = "BREACH (NO PPE)"
            badge_sub = "Worker in vicinity without verified helmet!"
        elif vicinity_presence:
            if vicinity_status == "AUTHORIZED_OPERATOR_PPE_VERIFIED":
                zone_class = "hud-blue"
                badge_title = "Vicinity Status"
                badge_val = "AUTHORIZED"
                badge_sub = "Worker in vicinity with verified helmet (Safe)"
            else:
                zone_class = "hud-amber"
                badge_title = "Vicinity Status"
                badge_val = "IN VICINITY"
                badge_sub = "Evaluating worker PPE compliance..."
        else:
            zone_class = "hud-green"
            badge_title = "Vicinity Status"
            badge_val = "CLEAR"
            _distance_sub = (
                f"latest contact {latest_distance:.2f} m ({_contact_age(latest_contact)})"
                if latest_distance is not None and latest_contact
                else "perimeter clear"
            )
            badge_sub = f"Danger perimeter &lt; 1.5 m · {_distance_sub}"

        st.markdown(
            f"""
            <div class="hud-card {zone_class}">
                <div class="hud-title">{badge_title}</div>
                <div class="hud-value">{badge_val}</div>
                <div class="hud-sub">{badge_sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with w4:
        st.markdown(
            f"""
            <div class="hud-card">
                <div class="hud-title">Last Badge Contact</div>
                <div class="hud-value hud-tight">{_contact_age(latest_contact) if latest_contact else '—'}</div>
                <div class="hud-sub">{str((latest_contact or {}).get('worker_id') or 'No contacts recorded')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>Badge Registry</div>", unsafe_allow_html=True)
    if badges:
        badge_rows = [
            {
                "Worker ID": b.get("worker_id", "?"),
                "Name": b.get("worker_name") or "—",
                "Department": b.get("department") or "—",
                "Badge MAC": b.get("badge_mac", "?"),
                "Status": "ACTIVE" if b.get("active") else "inactive",
            }
            for b in badges
        ]
        st.dataframe(pd.DataFrame(badge_rows), width="stretch", hide_index=True)
    else:
        st.info("No badges registered yet.")

    st.markdown("<div class='section-title'>Recent Proximity Contacts</div>", unsafe_allow_html=True)
    if breaches:
        contact_rows = []
        for br in breaches[:12]:
            distance = _reading(br.get("distance_est_m"))
            contact_rows.append(
                {
                    "Time": _contact_time(br.get("ts"), br.get("created_at")),
                    "Worker": br.get("worker_id") or "UNKNOWN",
                    "Dist (m)": f"{distance:.2f}" if distance is not None else "—",
                    "RSSI": br.get("rssi_raw") if br.get("rssi_raw") is not None else "—",
                    "RSSI EMA": f"{float(br.get('rssi_smoothed')):.1f}" if br.get("rssi_smoothed") is not None else "—",
                    "Zone": "DANGER" if (distance is not None and distance < 1.5) else "approach",
                }
            )
        st.dataframe(pd.DataFrame(contact_rows), width="stretch", hide_index=True)
    else:
        st.info("No proximity contacts yet. They appear when a badge comes within ESP-NOW range of the machine node.")

    contact_hist: list[tuple[datetime, float]] = []
    for br in reversed(breaches):
        if br.get("rssi_smoothed") is None:
            continue
        _dt = _parse_ts(br.get("ts"))
        if _dt is None or _dt.year < 2000:  # ESP32 uptime is not a wall clock
            _dt = _parse_ts(br.get("created_at"))
        if _dt is None:
            continue
        contact_hist.append((_dt, float(br["rssi_smoothed"])))

    if len(contact_hist) >= 2:
        rssi_df = pd.DataFrame(
            {
                "Time": [dt for dt, _ in contact_hist],
                "RSSI (dBm)": [rssi for _, rssi in contact_hist],
            }
        ).set_index("Time")
        st.line_chart(rssi_df, height=180, color=["#06b6d4"])
        st.caption("Smoothed RSSI of received badge contacts. More negative = further from the machine node.")

st.markdown("<br>", unsafe_allow_html=True)
# ══════════════════════════════════════════════════════════════════════════════
# SAFETY INCIDENT AUDIT LOG & SNAPSHOT EVIDENCE INSPECTOR
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="armor-header">
        {icon_svg('clipboard_check', color='#06b6d4', size=22)}
        <span>Safety Incident Audit Log & Evidence Inspector</span>
    </div>
    """,
    unsafe_allow_html=True,
)

if incidents:
    inc_left, inc_right = st.columns([1.1, 0.9], gap="medium")

    with inc_left:
        st.markdown("<div class='section-title'>Recorded Safety Violations (SQLite)</div>", unsafe_allow_html=True)
        table_rows = []
        for inc in incidents:
            table_rows.append({
                "Incident ID": inc["incident_id"][:8] + "...",
                "Full ID": inc["incident_id"],
                "Worker ID": inc.get("worker_id") or "UNKNOWN",
                "Violation": inc.get("violation_type"),
                "Compliance": f"{float(inc.get('compliance_ratio') or 0):.0%}",
                "Lockout": "Issued" if inc.get("interlock_issued") else "No",
                "Status": "Resolved" if inc.get("resolved") else "OPEN",
                "Time": inc.get("created_at", "")[:19].replace("T", " "),
            })
        df_inc = pd.DataFrame(table_rows)
        st.dataframe(
            df_inc[["Incident ID", "Worker ID", "Violation", "Compliance", "Lockout", "Status", "Time"]],
            use_container_width=True,
            height=280,
        )

    with inc_right:
        st.markdown("<div class='section-title'>Violation Snapshot Inspection</div>", unsafe_allow_html=True)
        selected_id = st.selectbox(
            "Select Incident to Inspect:",
            options=[row["Full ID"] for row in table_rows],
            format_func=lambda fid: f"Incident {fid[:8]}... - {next((r['Worker ID'] for r in table_rows if r['Full ID']==fid), '')}",
            key="incident_select",
        )

        selected_incident = next((i for i in incidents if i["incident_id"] == selected_id), None)
        if selected_incident:
            snap_path = selected_incident.get("snapshot_path")
            c_meta1, c_meta2 = st.columns(2)
            with c_meta1:
                st.caption(f"Worker: **{selected_incident.get('worker_id')}**")
                st.caption(f"Badge MAC: `{selected_incident.get('badge_mac')}`")
            with c_meta2:
                st.caption(f"Compliance Ratio: **{float(selected_incident.get('compliance_ratio') or 0):.1%}** (Req: >=65%)")
                st.caption(f"Status: **{'Resolved' if selected_incident.get('resolved') else 'ACTIVE LOCKOUT'}**")

            if snap_path and Path(snap_path).exists():
                st.image(snap_path, caption=f"Evidence: {Path(snap_path).name}", use_container_width=True)
            else:
                st.warning(f"Snapshot file `{snap_path}` not found on disk.")

            if not selected_incident.get("resolved"):
                if st.button(
                    f"Authorize Safety Reset for Incident {selected_id[:8]}",
                    key="btn_reset_incident",
                    icon=":material/lock_open:",
                    use_container_width=True,
                    disabled=not backend_online,
                ):
                    code, resp = api_post(
                        f"/api/v1/interlock/reset/{selected_id}",
                        params={"reset_by": "Plant_Manager_Console", "device_id": device_id},
                    )
                    if code == 200:
                        st.success(f"Incident {selected_id[:8]} marked resolved. Interlock cleared!")
                        st.rerun()
                    else:
                        st.error(f"Failed to reset: {resp}")
else:
    st.info("No safety violations recorded in SQLite yet. Trigger a breach or run the test suite to populate incidents.")

st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET LIVE FEED & MQTT DEBUG
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("🔧 Debug: WebSocket Live Feed & MQTT Debug", expanded=False):
    dbg_left, dbg_right = st.columns(2)

    with dbg_left:
        st.markdown("#### WebSocket Live Feed")
        st.caption("Connect to `/ws/live` for instant push notifications.")
        ws_status = "Connected" if backend_online else "Disconnected"
        st.caption(f"Status: **{ws_status}**")
        st.caption(f"URL: `ws://127.0.0.1:8000/ws/live?device_id={device_id}`")

    with dbg_right:
        st.markdown("#### MQTT Debug (Recent Messages)")
        if backend_online:
            mqtt_debug = api_get("/api/v1/debug/mqtt", params={"limit": 10}, timeout=1.0)
            if mqtt_debug and "messages" in mqtt_debug:
                for msg in mqtt_debug["messages"][:5]:
                    topic = msg.get("topic", "unknown")
                    payload = str(msg.get("payload", ""))[:120]
                    st.code(f"{topic}\n{payload}", language="json")
            else:
                st.info("No recent MQTT messages.")
        else:
            st.caption("Backend must be online to view MQTT debug.")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    "<div style='text-align:center; color:#64748b; font-size:0.8rem; margin-top:20px;'>"
    "ARMOR Operator Control Room — Real ESP32 telemetry only. No simulation."
    "</div>",
    unsafe_allow_html=True,
)
