"""
ARMOR – Groq LLM Predictive Maintenance Advisor
------------------------------------------------
Generates domain-expert predictive maintenance statements and root-cause diagnoses
using the Groq API (Qwen 3.8 / Llama 3) based on real-time multi-sensor telemetry,
anomaly decomposition, and rolling-window persistence.
"""
from __future__ import annotations

import os
import time
import threading
from typing import Any, Mapping
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# In-memory prediction cache to prevent spamming Groq on every sub-second packet
_PREDICTION_CACHE: dict[str, Any] = {
    "prediction_text": "Machine operating within nominal baselines. No immediate failure risk detected.",
    "severity": "NOMINAL",
    "timestamp": 0.0,
    "top_contributor": "none",
    "model_used": GROQ_MODEL,
}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 10.0


def generate_predictive_advisory(
    telemetry: Mapping[str, Any],
    anomaly_decomp: Mapping[str, Any],
    window_stats: Mapping[str, Any] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Generates a concise 1-2 sentence predictive maintenance advisory using Groq LLM."""
    global _PREDICTION_CACHE

    now = time.time()
    with _CACHE_LOCK:
        if not force_refresh and (now - _PREDICTION_CACHE["timestamp"] < _CACHE_TTL_SECONDS):
            return dict(_PREDICTION_CACHE)

    anomaly_pct = float(anomaly_decomp.get("anomaly_percentage", 0.0))
    score = float(anomaly_decomp.get("anomaly_score", 0.0))
    is_anomaly = bool(anomaly_decomp.get("is_anomaly", False))
    top_contributor = str(anomaly_decomp.get("top_contributor", "none"))
    modalities = anomaly_decomp.get("modalities", {})

    window_count = 0
    primary_driver = "Nominal"
    if window_stats:
        window_count = int(window_stats.get("anomaly_count_in_window", 0))
        primary_driver = str(window_stats.get("primary_driver", "Nominal"))

    # If completely nominal, return nominal statement quickly
    if anomaly_pct < 25.0 and not is_anomaly and window_count == 0:
        res = {
            "prediction_text": "All motor telemetry (vibration, current, voltage, temperature) remains in nominal baseline limits. Continuous operation authorized.",
            "severity": "NOMINAL",
            "timestamp": now,
            "top_contributor": top_contributor,
            "model_used": "rules-engine-nominal",
        }
        with _CACHE_LOCK:
            _PREDICTION_CACHE = res
        return res

    # Build prompt for Groq LLM
    v_stat = modalities.get("vibration", {})
    c_stat = modalities.get("current", {})
    p_stat = modalities.get("voltage_power", {})
    t_stat = modalities.get("temperature", {})

    prompt = (
        f"Industrial Predictive Maintenance Advisory Request:\n"
        f"- Anomaly Severity: {anomaly_pct:.1f}% (Score: {score:.3f})\n"
        f"- Sustained Window Anomalies (5s): {window_count} occurrences (Driver: {primary_driver})\n"
        f"- Vibration: status={v_stat.get('status')}, weight={v_stat.get('weight_pct')}%, sub_score={v_stat.get('sub_score_pct')}%\n"
        f"- Motor Current: status={c_stat.get('status')}, weight={c_stat.get('weight_pct')}%, sub_score={c_stat.get('sub_score_pct')}%\n"
        f"- Voltage & Power: status={p_stat.get('status')}, weight={p_stat.get('weight_pct')}%, sub_score={p_stat.get('sub_score_pct')}%\n"
        f"- Temperature: status={t_stat.get('status')}, weight={t_stat.get('weight_pct')}%, sub_score={t_stat.get('sub_score_pct')}%\n\n"
        f"Provide a direct, authoritative 1-2 sentence engineering diagnosis and action recommendation."
    )

    prediction_text = None
    model_used = GROQ_MODEL

    if GROQ_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            body = {
                "model": GROQ_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert industrial mechanical & electrical reliability engineer for CNC machinery and motor drives. "
                            "Output exactly 1 to 2 concise sentences stating the probable failure mechanism and recommended action. "
                            "Do not include conversational pleasantries, formatting, or prefixes."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 90,
                "temperature": 0.2,
            }
            r = requests.post(GROQ_API_URL, headers=headers, json=body, timeout=5.0)
            if r.status_code == 200:
                data = r.json()
                choices = data.get("choices", [])
                if choices and "message" in choices[0]:
                    prediction_text = choices[0]["message"].get("content", "").strip()
        except Exception as e:
            print(f"[Groq Advisor] API call failed: {e}")

    # Deterministic expert fallback if Groq call is skipped or fails
    if not prediction_text:
        model_used = "expert-rules-fallback"
        if "current" in top_contributor.lower():
            prediction_text = (
                f"Elevated motor current ({c_stat.get('sub_score_pct', 0):.0f}% anomaly) indicates mechanical binding or winding overload. "
                f"Recommend immediate stator insulation check and shaft torque verification."
            )
        elif "vibration" in top_contributor.lower():
            prediction_text = (
                f"High vibration anomaly ({v_stat.get('sub_score_pct', 0):.0f}%) indicates severe bearing wear or dynamic shaft unbalance. "
                f"Inspect bearing races and mechanical mountings within 24 hours."
            )
        elif "temp" in top_contributor.lower():
            prediction_text = (
                f"Excessive surface temperature ({t_stat.get('sub_score_pct', 0):.0f}%) indicates localized thermal buildup or cooling failure. "
                f"Inspect airflow ducts and bearing lubrication immediately."
            )
        elif "voltage" in top_contributor.lower():
            prediction_text = (
                f"Bus voltage sag/instability detected. Check power supply regulation and electrical terminals to prevent motor stall."
            )
        else:
            prediction_text = (
                f"Multi-sensor anomaly detected ({anomaly_pct:.0f}%). Driven by {primary_driver}; verify mechanical alignment and electrical supply."
            )

    severity = "CRITICAL" if anomaly_pct >= 75.0 or window_count >= 3 else ("ELEVATED" if anomaly_pct >= 45.0 else "NOMINAL")

    res = {
        "prediction_text": prediction_text,
        "severity": severity,
        "timestamp": now,
        "top_contributor": top_contributor,
        "model_used": model_used,
        "anomaly_percentage": anomaly_pct,
    }

    with _CACHE_LOCK:
        _PREDICTION_CACHE = res
    return res
