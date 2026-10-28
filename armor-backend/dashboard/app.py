"""
ARMOR – Streamlit Operator Control Room
========================================
Active Real-Time Machine & Operator Response System
Implements the web command center per:
  - ARMOR_System_Architecture_and_Implementation_Plan.md (Section 4.3)
  - ARMOR_24Hour_Work_Division_and_Roadmap.md (Landmine B mitigation)

Features:
  • High-impact dark cyberpunk / industrial safety command room styling
  • Pulsing real-time safety alert banners (Normal / Breach / Lockout)
  • Embedded low-latency Edge Vision MJPEG iframe (http://127.0.0.1:8000/video/stream)
  • Real-time Plotly charts for ADXL345 vibration, INA219 current/power, DS18B20 temp
  • Incident log table with interactive snapshot photo evidence inspector
  • Manual emergency lockout & safety recovery controls
  • In-dashboard breach test simulator
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ── Config (Use 127.0.0.1 to avoid Windows IPv6 localhost delay) ──────────────
API_BASE_URL = os.getenv("ARMOR_API_URL", "http://127.0.0.1:8000")
DEFAULT_DEVICE_ID = os.getenv("ARMOR_DEVICE_ID", "machino_node_01")
SNAPSHOTS_DIR = Path(os.getenv("SNAPSHOT_DIR", "data/snapshots"))

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ARMOR // Operator Control Room",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS Design System ──────────────────────────────────────────────────
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

    /* Card Panels */
    .armor-panel {
        background: var(--armor-card-bg);
        border: 1px solid var(--armor-card-border);
        border-radius: 12px;
        padding: 18px;
        backdrop-filter: blur(16px);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        margin-bottom: 16px;
    }

    /* Metric HUD Cards */
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
    .hud-sub {
        font-size: 0.75rem;
        color: var(--armor-text-muted);
        margin-top: 4px;
    }

    /* Pulsing Alert Banners */
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

    @keyframes pulse-red {
        0% { box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }
        50% { box-shadow: 0 0 35px rgba(239, 68, 68, 0.85); }
        100% { box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }
    }

    /* Live Video Container */
    .video-frame-container {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(56, 189, 248, 0.3);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6);
        position: relative;
        background: #020617;
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
    /* ── Streamlit Native Element Overrides ─────────────────────── */

    /* Main container & block backgrounds */
    .stApp, .main .block-container {
        background-color: var(--armor-bg) !important;
        color: var(--armor-text-primary) !important;
    }

    /* All text elements */
    h1, h2, h3, h4, h5, h6, p, span, label, li, td, th, div {
        color: var(--armor-text-primary) !important;
    }

    /* Sidebar text */
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span, [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] div {
        color: var(--armor-text-primary) !important;
    }
    [data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] small {
        color: var(--armor-text-muted) !important;
    }

    /* Tabs */
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
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: var(--armor-cyan) !important;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none;
    }

    /* Buttons */
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

    /* Text inputs & select boxes */
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

    /* Slider */
    .stSlider [data-baseweb="slider"] {
        color: var(--armor-cyan) !important;
    }

    /* Dataframe / table */
    [data-testid="stDataFrame"], .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }

    /* Success / Error / Warning / Info boxes */
    .stSuccess, .stAlert, [data-testid="stNotification"] {
        border-radius: 8px !important;
    }

    /* Toast notifications */
    [data-testid="stToast"] {
        background-color: rgba(15, 23, 42, 0.95) !important;
        border: 1px solid rgba(56, 189, 248, 0.3) !important;
        backdrop-filter: blur(12px);
    }

    /* Metric cards (native st.metric) */
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-family: 'Space Grotesk', sans-serif !important;
    }
    [data-testid="stMetricLabel"] {
        color: var(--armor-text-muted) !important;
    }

    /* Plotly chart container */
    .js-plotly-plot .plotly .modebar {
        background: transparent !important;
    }

    /* Scrollbar styling */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); }
    ::-webkit-scrollbar-thumb { background: rgba(6, 182, 212, 0.3); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(6, 182, 212, 0.5); }

    </style>
    """,
    unsafe_allow_html=True,
)

# ── Resilient Fast API Helpers ────────────────────────────────────────────────
def api_get(endpoint: str, params: dict | None = None) -> Any:
    try:
        r = requests.get(f"{API_BASE_URL}{endpoint}", params=params, timeout=0.6)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def api_post(endpoint: str, json_data: dict | None = None, params: dict | None = None) -> Any:
    try:
        r = requests.post(f"{API_BASE_URL}{endpoint}", json=json_data, params=params, timeout=1.5)
        return r.status_code, r.json() if r.content else {}
    except Exception as e:
        return 500, {"error": str(e)}


# ── Step 1: Fast Single Health Check ──────────────────────────────────────────
health = api_get("/api/v1/health")
backend_online = health is not None and health.get("status") == "ok"


# ── Sidebar Controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🛡️ ARMOR COMMAND")
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
        st.caption("Start backend in terminal:<br>`python -m uvicorn --app-dir armor-backend backend.main:app --port 8000`", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### ⚡ Quick Simulation Triggers")

    if st.button("🚶 Simulate Proximity Breach (<1.5m)", use_container_width=True, type="secondary", disabled=not backend_online):
        code, resp = api_post(
            "/api/v1/breach",
            json_data={
                "device_id": device_id,
                "worker_id": "WORKER_EMP_402",
                "badge_mac": "24:6F:28:AB:C1:02",
                "distance_est_m": 1.2,
                "rssi_smoothed": -60.5,
            },
        )
        if code in (200, 202):
            st.toast("🚨 Proximity breach event sent! Vision inspection triggered.", icon="⚠️")
        else:
            st.error(f"Failed to post breach: {resp}")

    st.markdown("---")
    st.markdown("#### 🪪 Authorized Smart Badges")
    if backend_online:
        workers_data = api_get("/api/v1/workers")
        if workers_data and "badges" in workers_data:
            for b in workers_data["badges"][:3]:
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


# ── Step 2: Fetch Data or Fallback to Safe Defaults ───────────────────────────
if backend_online:
    status_data = api_get(f"/api/v1/status/{device_id}") or {}
    motor_state = status_data.get("motor_state", "UNKNOWN")
    interlock_active = bool(status_data.get("interlock_active", False))
    proximity_breach = bool(status_data.get("proximity_breach_active", False))
    active_worker = status_data.get("active_worker_id")
    current_rms = float(status_data.get("current_rms") or 0.048)
    current_voltage = float(status_data.get("current_voltage_v") or 12.1)
    current_ma = float(status_data.get("current_ma") or 420.5)
    current_temp = float(status_data.get("current_temp_c") or 34.2)
    power_w = round((current_voltage * current_ma) / 1000.0, 2)

    telemetry_resp = api_get(f"/api/v1/telemetry/{device_id}", params={"limit": 60})
    samples = telemetry_resp.get("samples", []) if telemetry_resp else []

    incidents_resp = api_get("/api/v1/incidents", params={"device_id": device_id, "limit": 20})
    incidents = incidents_resp.get("incidents", []) if incidents_resp else []
else:
    # Standby preview state when backend is offline
    motor_state = "STANDBY"
    interlock_active = False
    proximity_breach = False
    active_worker = None
    current_rms = 0.048
    current_voltage = 12.1
    current_ma = 420.5
    current_temp = 34.2
    power_w = 5.09
    samples = []
    incidents = []


# ── Top Safety Alert Banner ───────────────────────────────────────────────────
if not backend_online:
    st.markdown(
        f"""
        <div class="alert-banner-offline">
            <div>
                <span style="font-size: 1.1rem; font-weight: 700; color: #ffffff;">
                    ⚠️ FASTAPI GATEWAY OFFLINE (PORT 8000)
                </span><br>
                <span style="font-size: 0.85rem; color: #cbd5e1;">
                    Dashboard is in preview mode. Start backend: <code>python -m uvicorn --app-dir armor-backend backend.main:app --reload --port 8000</code>
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
                <span style="font-size: 1.3rem; font-weight: 800; color: #ffffff; display: flex; align-items: center; gap: 10px;">
                    🚨 EMERGENCY MOTOR LOCKOUT ACTIVE — SAFETY INTERLOCK ENGAGED
                </span>
                <span style="font-size: 0.85rem; color: #fecaca;">
                    Cell <b>{device_id}</b> power cut. L298N driver Enable pin (GPIO 14) pulled LOW. Worker: <b>{active_worker or 'UNKNOWN'}</b>.
                </span>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; background: rgba(0,0,0,0.5); padding: 6px 14px; border-radius: 6px; border: 1px solid #ef4444;">
                INTERLOCK: <b>PULLED LOW (0V)</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
elif proximity_breach:
    st.markdown(
        f"""
        <div class="alert-banner-breach">
            <div>
                <span style="font-size: 1.2rem; font-weight: 700; color: #ffffff;">
                    ⚠️ RESTRICTED ZONE PROXIMITY BREACH DETECTED
                </span><br>
                <span style="font-size: 0.85rem; color: #fef3c7;">
                    Worker <b>{active_worker or 'UNKNOWN'}</b> inside 1.5m perimeter. Camera inspection active.
                </span>
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; background: rgba(0,0,0,0.4); padding: 6px 12px; border-radius: 6px; border: 1px solid #f59e0b;">
                DISTANCE: <b>&lt; 1.5 METERS</b>
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
                <span style="font-size: 1.15rem; font-weight: 700; color: #ffffff;">
                    🛡️ SAFETY CELL ARMED & NOMINAL
                </span><br>
                <span style="font-size: 0.85rem; color: #a7f3d0;">
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


# ── KPI Metric HUD (4 Columns) ────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)

with c1:
    hud_class = "hud-red" if interlock_active else ("hud-green" if motor_state == "RUNNING" else "")
    st.markdown(
        f"""
        <div class="hud-card {hud_class}">
            <div class="hud-title">RS-555 DC Motor State</div>
            <div class="hud-value" style="color: {'#ef4444' if interlock_active else ('#10b981' if motor_state=='RUNNING' else '#ffffff')};">
                {motor_state}
            </div>
            <div class="hud-sub">L298N ENA: {'GPIO 14 LOW (0V)' if interlock_active else 'GPIO 14 HIGH (5V)'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    vibe_warn = current_rms > 0.15
    hud_class = "hud-red" if vibe_warn else "hud-green"
    st.markdown(
        f"""
        <div class="hud-card {hud_class}">
            <div class="hud-title">ADXL345 Vibration RMS</div>
            <div class="hud-value">{current_rms:.3f} <span style="font-size:1rem; font-weight:400; color:#94a3b8;">g</span></div>
            <div class="hud-sub">{'⚠️ Vibration Warning (>0.15g)' if vibe_warn else 'Nominal baseline (<0.10g)'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    curr_warn = current_ma > 800.0
    hud_class = "hud-amber" if curr_warn else ""
    st.markdown(
        f"""
        <div class="hud-card {hud_class}">
            <div class="hud-title">INA219 Power Draw</div>
            <div class="hud-value">{current_ma:.1f} <span style="font-size:1rem; font-weight:400; color:#94a3b8;">mA</span></div>
            <div class="hud-sub">Bus: {current_voltage:.1f}V | Power: {power_w:.2f}W</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c4:
    temp_warn = current_temp > 55.0
    hud_class = "hud-red" if temp_warn else ""
    st.markdown(
        f"""
        <div class="hud-card {hud_class}">
            <div class="hud-title">DS18B20 Surface Temp</div>
            <div class="hud-value">{current_temp:.1f} <span style="font-size:1rem; font-weight:400; color:#94a3b8;">°C</span></div>
            <div class="hud-sub">Thermal boundary: &lt;65.0°C</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)


# ── Main 2-Column Split View: Edge Vision (Left) & Real-time Charts (Right) ───
left_col, right_col = st.columns([1, 1], gap="medium")

# ─────────────────────────────────────────────────────────────────────────────
# LEFT COLUMN: Embedded MJPEG Edge Vision Stream
# ─────────────────────────────────────────────────────────────────────────────
with left_col:
    st.markdown(
        """
        <div class="armor-header">
            📹 Edge Vision Safety Inspection
        </div>
        """,
        unsafe_allow_html=True,
    )

    if backend_online:
        stream_url = f"{API_BASE_URL}/video/stream"
        st.markdown(
            f"""
            <div class="video-frame-container" style="height: 380px;">
                <div class="live-badge">● LIVE AI STREAM</div>
                <iframe 
                    src="{stream_url}" 
                    width="100%" 
                    height="100%" 
                    style="border:none; display:block; background:#000;"
                    scrolling="no"
                ></iframe>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="video-frame-container" style="height: 380px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:20px;">
                <div style="font-size: 2.5rem; margin-bottom: 10px;">📹</div>
                <div style="font-weight: 700; font-size: 1.1rem; color: #ffffff;">Camera Stream Offline</div>
                <div style="color: #94a3b8; font-size: 0.85rem; max-width: 380px; margin-top: 6px;">
                    Start the FastAPI backend server on port 8000 to connect to the live 30fps webcam & helmet segmentation stream.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button("⚡ EMERGENCY LOCKOUT", use_container_width=True, type="primary", disabled=not backend_online):
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
                st.toast("🛑 EMERGENCY LOCKOUT ENGAGED!", icon="🚨")
                time.sleep(0.3)
                st.rerun()

    with btn_col2:
        if st.button("🔄 RESET INTERLOCK", use_container_width=True, disabled=not backend_online):
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
                st.toast("✅ Cell interlock reset to RUNNING.", icon="🛡️")
                time.sleep(0.3)
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN: Plotly Live Telemetry Charts
# ─────────────────────────────────────────────────────────────────────────────
with right_col:
    st.markdown(
        """
        <div class="armor-header">
            📈 Predictive Maintenance Telemetry
        </div>
        """,
        unsafe_allow_html=True,
    )

    chart_tab1, chart_tab2, chart_tab3 = st.tabs(
        ["Vibration (ADXL345)", "Power & Load (INA219)", "Temperature (DS18B20)"]
    )

    if samples:
        df = pd.DataFrame(samples)
        if "ts" in df.columns:
            df["ts_dt"] = pd.to_datetime(df["ts"], errors="coerce")
        else:
            df["ts_dt"] = pd.date_range(end=datetime.now(timezone.utc), periods=len(df), freq="1s")

        with chart_tab1:
            fig_vibe = go.Figure()
            fig_vibe.add_trace(
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
                fig_vibe.add_trace(
                    go.Scatter(
                        x=df["ts_dt"],
                        y=df["crest_factor"],
                        mode="lines",
                        name="Crest Factor",
                        line=dict(color="#f59e0b", width=1.5, dash="dot"),
                        yaxis="y2",
                    )
                )

            fig_vibe.add_hline(
                y=0.15,
                line_dash="dash",
                line_color="#ef4444",
                annotation_text="Alarm Threshold (0.15g)",
                annotation_position="top left",
            )

            fig_vibe.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(15,23,42,0.6)",
                font=dict(color="#94a3b8", family="Inter"),
                margin=dict(l=20, r=20, t=25, b=25),
                height=320,
                legend=dict(orientation="h", y=1.1, x=0),
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Vibration (g)", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis2=dict(title="Crest Factor", overlaying="y", side="right", showgrid=False),
            )
            st.plotly_chart(fig_vibe, use_container_width=True)

        with chart_tab2:
            fig_pwr = go.Figure()
            fig_pwr.add_trace(
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
            fig_pwr.add_trace(
                go.Scatter(
                    x=df["ts_dt"],
                    y=df["voltage_v"],
                    mode="lines",
                    name="Bus Voltage (V)",
                    line=dict(color="#38bdf8", width=1.5),
                    yaxis="y2",
                )
            )
            fig_pwr.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(15,23,42,0.6)",
                font=dict(color="#94a3b8", family="Inter"),
                margin=dict(l=20, r=20, t=25, b=25),
                height=320,
                legend=dict(orientation="h", y=1.1, x=0),
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Current (mA)", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis2=dict(title="Voltage (V)", overlaying="y", side="right", showgrid=False),
            )
            st.plotly_chart(fig_pwr, use_container_width=True)

        with chart_tab3:
            fig_temp = go.Figure()
            fig_temp.add_trace(
                go.Scatter(
                    x=df["ts_dt"],
                    y=df["temperature_c"],
                    mode="lines+markers",
                    name="Motor Temperature (°C)",
                    line=dict(color="#f43f5e", width=2.5),
                    marker=dict(size=4),
                )
            )
            fig_temp.add_hline(
                y=55.0,
                line_dash="dash",
                line_color="#f59e0b",
                annotation_text="Thermal Alert (55°C)",
            )
            fig_temp.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(15,23,42,0.6)",
                font=dict(color="#94a3b8", family="Inter"),
                margin=dict(l=20, r=20, t=25, b=25),
                height=320,
                xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Temperature (°C)", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
            )
            st.plotly_chart(fig_temp, use_container_width=True)

    else:
        with chart_tab1:
            st.info("Awaiting telemetry stream from ESP32 machine node. Run `python scripts/simulate_esp32.py` to stream live sensor readings.")
        with chart_tab2:
            st.info("Awaiting current & voltage readings from INA219.")
        with chart_tab3:
            st.info("Awaiting temperature readings from DS18B20.")


# ── Full-Width Section: Safety Incident Audit Log & Snapshot Evidence Inspector ───
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    """
    <div class="armor-header">
        📋 Safety Incident Audit Log & Evidence Inspector
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
                "Lockout": "⚡ Issued" if inc.get("interlock_issued") else "No",
                "Status": "✅ Resolved" if inc.get("resolved") else "🚨 OPEN",
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

            if snap_path and os.path.exists(snap_path):
                st.image(snap_path, caption=f"Evidence: {os.path.basename(snap_path)}", use_container_width=True)
            else:
                st.warning(f"Snapshot file `{snap_path}` not found on disk.")

            if not selected_incident.get("resolved"):
                if st.button(f"🔓 Authorize Safety Reset for Incident {selected_id[:8]}", use_container_width=True, disabled=not backend_online):
                    code, resp = api_post(
                        f"/api/v1/interlock/reset/{selected_id}",
                        params={"reset_by": "Plant_Manager_Console", "device_id": device_id},
                    )
                    if code == 200:
                        st.success(f"Incident {selected_id[:8]} marked resolved. Interlock cleared!")
                        time.sleep(0.4)
                        st.rerun()
                    else:
                        st.error(f"Failed to reset: {resp}")
else:
    st.info("No safety violations recorded in SQLite yet. Trigger a breach or run `python test_backend.py` to populate test incidents.")
