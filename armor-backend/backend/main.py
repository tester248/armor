"""
ARMOR – FastAPI Gateway
------------------------
Implements SW Member 2 scope from ARMOR_System_Architecture_and_Implementation_Plan.md:

  • Eclipse Mosquitto MQTT client (subscribes to armor/# topics)
  • WebSocket /ws/live  – live telemetry + status push to Streamlit / React Native
  • GET  /video/stream  – MJPEG stream from VisionEngine (Streamlit <iframe>)

  REST endpoints
  ──────────────
  POST /api/v1/telemetry            ← ESP32 / MQTT HTTP fallback
  POST /api/v1/breach               ← proximity breach event (ESP-NOW → machine node → here)
  POST /api/v1/interlock            ← issue LOCKOUT or RESET command
  POST /api/v1/interlock/reset/{id} ← manager resets a specific incident
  GET  /api/v1/status/{device_id}   ← live machine status
  GET  /api/v1/incidents            ← paginated incident log
  GET  /api/v1/incidents/{id}       ← single incident + snapshot
  POST /api/v1/workers              ← register ESP32 smart badge
  GET  /api/v1/workers              ← list registered badges
  DELETE /api/v1/workers/{mac}      ← deactivate badge
  GET  /api/v1/health               ← health check

MQTT Topics (Eclipse Mosquitto)
────────────────────────────────
  Subscribe  machinocare/v1/devices/+/telemetry      ← ADXL345 / INA219 / DS18B20 readings
  Subscribe  machinocare/v1/events/proximity   ← ESP-NOW proximity breach events
  Publish    machinocare/v1/devices/{device}/interlock ← LOCKOUT / RESET commands to machine node
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# ── Load env ──────────────────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

# ── Local imports ─────────────────────────────────────────────────────────────
from backend.storage import ArmorStore
from backend.vision import vision_engine, SNAPSHOT_DIR
from backend.models import (
    TelemetryIngestRequest,
    ProximityBreachEvent,
    InterlockCommand,
    WorkerBadge,
)
from backend.ml_engine import (
    build_feature_matrix,
    train_isolation_forest,
    score_feature_vector,
    score_with_forest,
    latest_feature_vector,
    compute_multimodal_baseline_stats,
    decompose_anomaly,
    FEATURE_ORDER,
)
from backend.groq_advisor import generate_predictive_advisory

# ── Config ────────────────────────────────────────────────────────────────────
MQTT_BROKER   = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT     = int(os.getenv("MQTT_PORT", "1883"))
_ARMOR_DB_RAW = os.getenv("ARMOR_DB", "data/armor.db")
ARMOR_DB = str((Path(__file__).resolve().parent.parent / _ARMOR_DB_RAW).resolve()) if not os.path.isabs(_ARMOR_DB_RAW) else _ARMOR_DB_RAW
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
LIVE_PUSH_INTERVAL = 0.75   # seconds between WebSocket snapshots

# ── Singletons ────────────────────────────────────────────────────────────────
store = ArmorStore(db_path=ARMOR_DB)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# Telegram Bot
# ══════════════════════════════════════════════════════════════════════════════
def _telegram_send(text: str, photo_path: str | None = None) -> None:
    """Send alert to Telegram channel — fire and forget (runs in thread)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    def _send() -> None:
        try:
            if photo_path and os.path.exists(photo_path):
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                with open(photo_path, "rb") as f:
                    requests.post(
                        url,
                        data={"chat_id": TELEGRAM_CHAT_ID, "caption": text},
                        files={"photo": f},
                        timeout=8,
                    )
            else:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                requests.post(
                    url,
                    json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
                    timeout=8,
                )
        except Exception as e:
            print(f"[Telegram] Failed to send alert: {e}")

    threading.Thread(target=_send, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# MQTT Client (Eclipse Mosquitto)
# ══════════════════════════════════════════════════════════════════════════════
_mqtt_client = None

# Ring buffer of recent raw MQTT messages (for debug utility)
_mqtt_ring: list[dict[str, Any]] = []
_MQTT_RING_MAX = 200


def _load_model_package(device_id: str) -> dict[str, Any] | None:
    """Return the trained package dict for a device.

    calibrations.model_package is stored as JSON text, so the raw row is not
    usable by score_feature_vector(); it needs the parsed dict.
    """
    record = store.get_model_package("machino_node_01", device_id)
    if not record:
        return None
    package = record.get("model_package")
    if isinstance(package, str):
        try:
            package = json.loads(package)
        except (ValueError, TypeError):
            return None
    if isinstance(package, dict):
        if "baseline_stats" not in package and record.get("baseline_stats"):
            b_stats = record.get("baseline_stats")
            if isinstance(b_stats, str):
                try:
                    b_stats = json.loads(b_stats)
                except Exception:
                    pass
            package["baseline_stats"] = b_stats
        return package
    return None


def _score_package(feature_vector: Any, package: dict[str, Any]) -> float | None:
    """Score one feature vector with whichever model the package describes."""
    model_path = package.get("model_path")
    if model_path:
        score = score_with_forest(feature_vector, model_path)
        if score is not None:
            return score
        print(f"[ML] Forest unavailable at {model_path}; recalibrate.")
        return None
    if "weights" in package and "bias" in package:
        # Legacy distilled package.
        return score_feature_vector(feature_vector, package)
    return None


class RollingAnomalyMonitor:
    """Tracks anomalies across a 5-second sliding window and triggers motor lockdown
    only when anomalies are sustained above nominal baseline (prevents nuisance trips)."""
    def __init__(self, window_seconds: float = 5.0, count_threshold: int = 3):
        self.window_seconds = window_seconds
        self.threshold = count_threshold
        self.history: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def record_sample(
        self,
        device_id: str,
        is_anomaly: bool,
        anomaly_pct: float,
        contributors: dict[str, Any],
        now: float | None = None,
    ) -> dict[str, Any]:
        t = now or time.time()
        with self._lock:
            dev_hist = self.history.setdefault(device_id, [])
            cutoff = t - self.window_seconds
            dev_hist = [e for e in dev_hist if e["time"] >= cutoff]

            entry = {
                "time": t,
                "is_anomaly": is_anomaly,
                "anomaly_pct": anomaly_pct,
                "contributors": contributors,
            }
            dev_hist.append(entry)
            self.history[device_id] = dev_hist

            # Count occurrences in the 5-second window
            anomaly_count = sum(1 for e in dev_hist if e["is_anomaly"])
            total_samples = len(dev_hist)

            vib_anom = sum(1 for e in dev_hist if e["is_anomaly"] and e["contributors"].get("vibration", {}).get("status") == "ANOMALOUS")
            curr_anom = sum(1 for e in dev_hist if e["is_anomaly"] and e["contributors"].get("current", {}).get("status") == "ANOMALOUS")
            pwr_anom = sum(1 for e in dev_hist if e["is_anomaly"] and e["contributors"].get("voltage_power", {}).get("status") == "ANOMALOUS")
            temp_anom = sum(1 for e in dev_hist if e["is_anomaly"] and e["contributors"].get("temperature", {}).get("status") == "ANOMALOUS")

            should_lockout = (
                anomaly_count >= self.threshold or
                curr_anom >= self.threshold or
                vib_anom >= self.threshold or
                temp_anom >= self.threshold
            )

            primary_driver = "Multi-Modal Sensor Anomaly"
            if curr_anom >= self.threshold:
                primary_driver = "Sustained Motor Over-Current Fault"
            elif vib_anom >= self.threshold:
                primary_driver = "Sustained Mechanical Vibration Surge"
            elif temp_anom >= self.threshold:
                primary_driver = "Sustained Thermal Runaway / Overheating"
            elif pwr_anom >= self.threshold:
                primary_driver = "Sustained Electrical Voltage Sag"

            return {
                "window_seconds": self.window_seconds,
                "anomaly_count_in_window": anomaly_count,
                "total_samples_in_window": total_samples,
                "threshold": self.threshold,
                "vib_anomalies": vib_anom,
                "curr_anomalies": curr_anom,
                "temp_anomalies": temp_anom,
                "pwr_anomalies": pwr_anom,
                "should_lockout": should_lockout,
                "primary_driver": primary_driver,
            }

    def get_stats(self, device_id: str) -> dict[str, Any]:
        with self._lock:
            dev_hist = self.history.get(device_id, [])
            cutoff = time.time() - self.window_seconds
            dev_hist = [e for e in dev_hist if e["time"] >= cutoff]
            anomaly_count = sum(1 for e in dev_hist if e["is_anomaly"])
            return {
                "window_seconds": self.window_seconds,
                "anomaly_count_in_window": anomaly_count,
                "total_samples_in_window": len(dev_hist),
                "threshold": self.threshold,
            }


rolling_anomaly_monitor = RollingAnomalyMonitor(
    window_seconds=float(os.getenv("ANOMALY_WINDOW_SECONDS", "5.0")),
    count_threshold=int(os.getenv("ANOMALY_LOCKDOWN_THRESHOLD", "3")),
)
_latest_decomp: dict[str, Any] = {}


def _score_anomaly(device_id: str) -> dict[str, Any] | None:
    """Score telemetry, decompose into % and weights, check 5s window, and trigger predictive lockout."""
    global _latest_decomp
    try:
        package = _load_model_package(device_id)
        recent = store.get_recent_samples_for_ml(device_id, limit=50)
        if not recent:
            return None

        # Auto-initialize calibration package if missing or feature dimension mismatched
        if package is None or len(package.get("feature_means", [])) != len(FEATURE_ORDER):
            if len(recent) >= 20:
                print(f"[ML] Auto-calibrating 12-feature baseline for {device_id}...")
                f_mat = build_feature_matrix(recent, window_size=10)
                model_path = Path(ARMOR_DB).parent / "models" / f"{device_id}.joblib"
                package = train_isolation_forest(f_mat, contamination=0.05, model_path=model_path)
                baseline = compute_multimodal_baseline_stats(recent)
                store.save_model_package("machino_node_01", device_id, package, baseline, None, package.get("window_count"))

        fv = latest_feature_vector(recent, window_size=10)
        if fv is None:
            fv = extract_feature_vector([recent[-1]])

        raw_score = None
        if package:
            raw_score = _score_package(fv, package)

        # 1. Full multi-modal decomposition with instantaneous single-parameter spike detection
        latest_sample = recent[-1] if recent else None
        decomp = decompose_anomaly(fv, package or {}, latest_sample=latest_sample, raw_score=raw_score)
        _latest_decomp[device_id] = decomp

        # 2. 5-Second Sliding Window Persistence Tracker
        window_res = rolling_anomaly_monitor.record_sample(
            device_id=device_id,
            is_anomaly=decomp["is_anomaly"],
            anomaly_pct=decomp["anomaly_percentage"],
            contributors=decomp["modalities"],
        )

        # 3. Sustained Anomaly Lockdown Trigger
        if window_res["should_lockout"]:
            try:
                curr_state = store.get_machine_state(device_id)
                if not curr_state.get("interlock_active"):
                    print(
                        f"[Predictive Maintenance] LOCKDOWN TRIGGERED! {window_res['anomaly_count_in_window']} "
                        f"anomalies in 5s window. Driver: {window_res['primary_driver']}."
                    )
                    lockout_cmd = {
                        "command": "LOCKOUT",
                        "source": "PREDICTIVE_MAINTENANCE_ANOMALY_GATE",
                        "reason": f"SUSTAINED_ANOMALY_LOCKOUT: {window_res['primary_driver']}",
                        "anomaly_score": decomp["anomaly_score"],
                        "anomaly_percentage": decomp["anomaly_percentage"],
                        "window_count": window_res["anomaly_count_in_window"],
                        "timestamp": _utc_now(),
                    }
                    store.log_interlock({**lockout_cmd, "device_id": device_id})
                    store.set_machine_state(device_id, {
                        "motor_state": "LOCKED",
                        "interlock_active": True,
                        "lockout_reason": lockout_cmd["reason"],
                    })
                    _mqtt_publish(
                        topic=f"machinocare/v1/devices/{device_id}/interlock",
                        payload=lockout_cmd,
                    )
                    _telegram_send(
                        f"🚨 PREDICTIVE SAFETY MOTOR LOCKDOWN\n"
                        f"Device  : {device_id}\n"
                        f"Reason  : {window_res['primary_driver']}\n"
                        f"Severity: {decomp['anomaly_percentage']}%\n"
                        f"Window  : {window_res['anomaly_count_in_window']} anomalies in {window_res['window_seconds']}s\n"
                        f"Action  : Motor emergency power disconnected."
                    )
            except Exception as lock_err:
                print(f"[ML] Predictive lockout error: {lock_err}")

        # 4. Generate Groq LLM predictive advisory
        advisory = generate_predictive_advisory(latest_sample or {}, decomp, window_res)

        # 5. Record anomaly in store
        store.record_anomaly("machino_node_01", device_id, decomp["anomaly_score"], decomp["decision_threshold"], decomp["is_anomaly"])
        store.set_machine_state(device_id, {
            "is_anomaly": decomp["is_anomaly"],
            "anomaly_score": decomp["anomaly_score"],
            "anomaly_percentage": decomp["anomaly_percentage"],
            "top_contributor": decomp["top_contributor"],
            "anomaly_window_count": window_res["anomaly_count_in_window"],
            "anomaly_window_threshold": window_res["threshold"],
            "predictive_advisory": advisory.get("prediction_text"),
        })
        return decomp
    except Exception as e:
        print(f"[ML] Anomaly scoring failed: {e}")
        return None


def _telemetry_timestamp(value: Any) -> str:
    """Normalise an incoming timestamp. ESP32 millis() is not a wall-clock time."""
    if isinstance(value, (int, float)):
        # Accept epoch milliseconds only; smaller numbers are uptime counters.
        if value > 1_000_000_000_000:
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).isoformat()
        return _utc_now()
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            return _utc_now()
    return _utc_now()


def _handle_telemetry_message(payload: dict[str, Any]) -> None:
    """Process incoming telemetry from machinocare/v1/devices/+/telemetry topic.
    Normalizes both nested and flat schemas, handles nulls/NaNs, and cleans timestamps."""
    if not isinstance(payload, dict):
        return

    device_id = payload.get("device_id", "machino_node_01")
    vib = payload.get("vibration") if isinstance(payload.get("vibration"), dict) else {}
    pwr = payload.get("power") if isinstance(payload.get("power"), dict) else {}

    def _safe_float(v: Any) -> float | None:
        if v is None:
            return None
        try:
            val = float(v)
            return None if (math.isnan(val) or math.isinf(val)) else val
        except (ValueError, TypeError):
            return None

    rms = _safe_float(vib.get("rms") if "rms" in vib else payload.get("rms"))
    crest = _safe_float(vib.get("crest_factor") if "crest_factor" in vib else payload.get("crest_factor"))
    accel_x = _safe_float(vib.get("accel_x") if "accel_x" in vib else payload.get("accel_x"))
    accel_y = _safe_float(vib.get("accel_y") if "accel_y" in vib else payload.get("accel_y"))
    accel_z = _safe_float(vib.get("accel_z") if "accel_z" in vib else payload.get("accel_z"))

    voltage_v = _safe_float(pwr.get("voltage_v") if "voltage_v" in pwr else payload.get("voltage_v", payload.get("voltage")))
    current_ma = _safe_float(pwr.get("current_ma") if "current_ma" in pwr else payload.get("current_ma", payload.get("current")))
    power_mw = _safe_float(pwr.get("power_mw") if "power_mw" in pwr else payload.get("power_mw", payload.get("power")))

    if power_mw is None and voltage_v is not None and current_ma is not None:
        power_mw = round(voltage_v * current_ma, 2)

    temp_c = _safe_float(payload.get("temperature_c", payload.get("temp_c", payload.get("temperature"))))

    # Normalize motor state (avoid reporting normal idle as interlock lock)
    motor_state = str(payload.get("motor_state") or "IDLE").upper()
    try:
        current_state = store.get_machine_state(device_id)
        if not current_state.get("interlock_active") and motor_state == "LOCKED":
            motor_state = "IDLE"
    except Exception:
        pass

    record = {
        "device_id":    device_id,
        "timestamp":    _telemetry_timestamp(payload.get("timestamp")),
        "motor_state":  motor_state,
        "accel_x":      accel_x,
        "accel_y":      accel_y,
        "accel_z":      accel_z,
        "rms":          rms,
        "crest_factor": crest,
        "voltage_v":    voltage_v,
        "current_ma":   current_ma,
        "power_mw":     power_mw,
        "temperature_c": temp_c,
    }
    store.insert_telemetry(record)
    _score_anomaly(device_id)


def _handle_breach_message(payload: dict[str, Any]) -> None:
    """Process vicinity presence event from machinocare/v1/events/proximity topic.

    Safety Architecture:
      1. When a person is detected in vicinity -> Log vicinity presence event.
      2. Set vicinity presence active (informational, NOT a breach yet).
      3. Trigger Vision AI inspection with person dwell countdown.
      4. IF COMPLIANT (wearing helmet):
           - Operator is authorized with verified PPE!
           - Machine stays RUNNING. NO breach or lockout occurs.
           - Status = AUTHORIZED_OPERATOR_PPE_VERIFIED.
      5. IF NON-COMPLIANT (missing helmet):
           - A true SAFETY BREACH occurs (worker in vicinity without PPE gear).
           - Issue emergency LOCKOUT to machine node.
           - Record incident as VICINITY_BREACH_MISSING_PPE.
           - Dispatch urgent Telegram alert with snapshot.
    """
    device_id = payload.get("device_id", "machino_node_01")
    worker_id = payload.get("worker_id", "UNKNOWN")
    badge_mac  = payload.get("badge_mac", "")

    # 1. Log vicinity entry
    store.insert_breach_event(payload)

    # 2. Mark vicinity presence active (NOT a breach yet!)
    store.set_machine_state(device_id, {
        "vicinity_presence_active": True,
        "vicinity_status":          "PRESENCE_DETECTED",
        "proximity_breach_active":  False,  # Not a breach yet! Only a breach if missing PPE!
        "active_worker_id":         worker_id,
    })

    print(f"[Safety Gate] Person detected in machine vicinity ({worker_id} / {badge_mac}). Evaluating PPE...")

    # 3. Vision AI inspection
    result = vision_engine.inspect(worker_id=worker_id, device_id=device_id)
    compliant = result["compliant"]
    snapshot  = result.get("snapshot_path")

    if compliant is None:
        print(
            f"[Vision] Inspection unavailable for {worker_id} "
            f"({result.get('label')}); operator verified in vicinity, interlock skipped."
        )
        store.set_machine_state(device_id, {
            "vicinity_presence_active": True,
            "vicinity_status":          "VICINITY_OCCUPIED_UNCHECKED",
            "proximity_breach_active":  False,
            "active_worker_id":         worker_id,
        })
        return

    if not compliant:
        # 4a. Worker is in vicinity WITHOUT helmet -> SAFETY BREACH OCCURS!
        incident_id = store.create_incident({
            "device_id":        device_id,
            "worker_id":        worker_id,
            "badge_mac":        badge_mac,
            "violation_type":   "VICINITY_BREACH_MISSING_PPE",
            "compliance_ratio": result["compliance_ratio"],
            "snapshot_path":    snapshot,
            "interlock_issued": True,
        })

        lockout_cmd = {
            "command":   "LOCKOUT",
            "source":    "VISION_AI_SAFETY_GATE",
            "reason":    "SAFETY_BREACH_UNPROTECTED_WORKER_IN_VICINITY",
            "worker_id": worker_id,
            "timestamp": _utc_now(),
        }
        store.log_interlock({**lockout_cmd, "device_id": device_id})
        store.set_machine_state(device_id, {
            "motor_state":             "LOCKED",
            "interlock_active":         True,
            "vicinity_presence_active": True,
            "vicinity_status":          "SAFETY_BREACH_MISSING_PPE",
            "proximity_breach_active":  True,  # Now marked as active breach
            "active_worker_id":         worker_id,
        })

        # Publish LOCKOUT to machine node via MQTT
        _mqtt_publish(
            topic=f"machinocare/v1/devices/{device_id}/interlock",
            payload=lockout_cmd,
        )

        # Telegram alert with snapshot
        alert_text = (
            f"🚨 ARMOR SAFETY BREACH / VIOLATION\n"
            f"Device : {device_id}\n"
            f"Worker : {worker_id}  |  Badge: {badge_mac}\n"
            f"Status : PERSON IN MACHINE VICINITY WITHOUT PPE!\n"
            f"Verdict: Helmet NOT detected (Ratio: {result['compliance_ratio']:.0%})\n"
            f"Action : Automatic Motor Power LOCKOUT Executed.\n"
            f"Incident #{incident_id}"
        )
        _telegram_send(alert_text, photo_path=snapshot)

    else:
        # 4b. Worker is wearing helmet -> AUTHORIZED! NO BREACH!
        store.set_machine_state(device_id, {
            "motor_state":              "RUNNING",
            "interlock_active":         False,
            "vicinity_presence_active": True,
            "vicinity_status":          "AUTHORIZED_OPERATOR_PPE_VERIFIED",
            "proximity_breach_active":  False,  # NOT a breach!
            "active_worker_id":         worker_id,
            "worker_compliant":         True,
        })
        print(f"[Safety Gate] Worker {worker_id} in vicinity with verified PPE helmet. Authorized operation (NO breach).")


def _mqtt_publish(topic: str, payload: dict[str, Any]) -> None:
    if _mqtt_client:
        try:
            _mqtt_client.publish(topic, json.dumps(payload), qos=1)
        except Exception as e:
            print(f"[MQTT] Publish failed on {topic}: {e}")


def _start_mqtt() -> None:
    """Connect to Eclipse Mosquitto and start the loop in a background thread."""
    global _mqtt_client
    try:
        import paho.mqtt.client as mqtt

        if hasattr(mqtt, "CallbackAPIVersion"):
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="armor-gateway")
        else:
            client = mqtt.Client(client_id="armor-gateway")

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT}")
                client.subscribe("machinocare/v1/#", qos=1)
            else:
                print(f"[MQTT] Connection failed, rc={rc}")

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode())
            except Exception:
                payload = {"_raw": msg.payload.decode(errors="replace")}

            # Capture into debug ring buffer
            _mqtt_ring.append({
                "topic": msg.topic,
                "payload": payload,
                "received_at": _utc_now(),
            })
            if len(_mqtt_ring) > _MQTT_RING_MAX:
                del _mqtt_ring[: len(_mqtt_ring) - _MQTT_RING_MAX]

            topic = msg.topic
            try:
                if topic.endswith("/telemetry"):
                    _handle_telemetry_message(payload)
                elif topic == "machinocare/v1/events/proximity":
                    threading.Thread(
                        target=_handle_breach_message,
                        args=(payload,),
                        daemon=True,
                    ).start()
            except Exception as e:
                # Never let a single malformed message kill the MQTT network thread.
                print(f"[MQTT] Handler failed on {topic}: {e!r}")

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        _mqtt_client = client
        client.loop_start()

    except Exception as e:
        print(f"[MQTT] Could not start: {e}. Running without MQTT (HTTP fallback only).")


# ══════════════════════════════════════════════════════════════════════════════
# FastAPI App
# ══════════════════════════════════════════════════════════════════════════════
app = FastAPI(
    title="ARMOR Gateway",
    version="1.0.0",
    description=(
        "Active Real-Time Machine & Operator Response System — "
        "FastAPI backend per ARMOR_System_Architecture_and_Implementation_Plan.md"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup():
    _start_mqtt()
    vision_engine.start()


@app.on_event("shutdown")
async def _shutdown():
    vision_engine.stop()
    if _mqtt_client:
        _mqtt_client.loop_stop()


# ══════════════════════════════════════════════════════════════════════════════
# MJPEG Video Stream (embedded in Streamlit via <iframe>)
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/video/stream", tags=["Vision"])
def video_stream():
    """
    Live MJPEG stream from VisionEngine.
    Streamlit embeds via:  <iframe src="http://localhost:8000/video/stream" />
    """
    return StreamingResponse(
        vision_engine.generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 3D Digital Twin (embedded in Streamlit via <iframe>)
# ----------------------------------------------------------------------------
@app.get("/twin", tags=["Vision"])
def digital_twin():
    """Serve the Three.js digital twin page. Connects to /ws/live via WebSocket."""
    twin_path = Path(__file__).resolve().parent.parent / "static" / "twin.html"
    if not twin_path.exists():
        raise HTTPException(status_code=404, detail="twin.html not found")
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=twin_path.read_text(encoding="utf-8"))


@app.post("/api/v1/vision/inspect/start", tags=["Vision"])
def vision_inspect_start(
    worker_id: str = "WORKER_EMP_402", device_id: str = "machino_node_01"
):
    """Start an async helmet inspection. Waits for a person in the camera,
    freezes that frame, runs Roboflow, returns immediately.
    Poll /api/v1/vision/inspect/status for the result.
    """
    if vision_engine is None:
        raise HTTPException(status_code=503, detail="Vision engine not available.")
    return vision_engine.start_inspection(worker_id, device_id)


@app.get("/api/v1/vision/inspect/status", tags=["Vision"])
def vision_inspect_status():
    """Return the current status of a pending inspection (for dashboard polling)."""
    if vision_engine is None:
        raise HTTPException(status_code=503, detail="Vision engine not available.")
    return vision_engine.get_inspection_status()


@app.post("/api/v1/vision/inspect", tags=["Vision"])
def vision_inspect(worker_id: str = "WORKER_EMP_402", device_id: str = "machino_node_01"):
    """
    Synchronous helmet compliance check (breach handler path).
    Runs person-detection gate first, then Roboflow helmet check if a person is present.
    """
    if vision_engine is None:
        raise HTTPException(status_code=503, detail="Vision engine not available.")
    result = vision_engine.inspect(worker_id=worker_id, device_id=device_id)
    return result


@app.get("/api/v1/vision/snapshot/{filename}", tags=["Vision"])
def vision_snapshot(filename: str):
    """Serve a saved inspection snapshot image."""
    from fastapi.responses import FileResponse

    path = SNAPSHOT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    return FileResponse(path)


@app.get("/api/v1/vision/state", tags=["Vision"])
def vision_state():
    """Return live Vision AI state: feed-freeze status, person detection, and helmet verdict."""
    if vision_engine is None:
        raise HTTPException(status_code=503, detail="Vision engine not available.")
    return vision_engine.get_state()


@app.post("/api/v1/vision/unfreeze", tags=["Vision"])
def vision_unfreeze():
    """Manually unfreeze the camera stream back to live scanning mode."""
    if vision_engine is None:
        raise HTTPException(status_code=503, detail="Vision engine not available.")
    vision_engine.unfreeze()
    return {"status": "unfrozen", "vision_state": "SCANNING"}


@app.get("/api/v1/vision/auto-freeze", tags=["Vision"])
def vision_get_auto_freeze():
    """Get current auto-freeze state."""
    if vision_engine is None:
        raise HTTPException(status_code=503, detail="Vision engine not available.")
    return {"auto_freeze_enabled": vision_engine.get_state().get("auto_freeze_enabled", False)}


@app.post("/api/v1/vision/auto-freeze", tags=["Vision"])
def vision_set_auto_freeze(enabled: bool = True):
    """Enable or disable automatic feed-freezing on person detection."""
    if vision_engine is None:
        raise HTTPException(status_code=503, detail="Vision engine not available.")
    vision_engine.set_auto_freeze(enabled)
    return {"status": "ok", "auto_freeze_enabled": enabled}


@app.get("/api/v1/vision/dwell-seconds", tags=["Vision"])
def vision_get_dwell_seconds():
    """Get the current dwell duration required before freeze is triggered."""
    if vision_engine is None:
        raise HTTPException(status_code=503, detail="Vision engine not available.")
    state = vision_engine.get_state()
    return {"person_dwell_seconds": state.get("dwell_required", 2.0)}


@app.post("/api/v1/vision/dwell-seconds", tags=["Vision"])
def vision_set_dwell_seconds(seconds: float = Query(2.0, ge=0.5, le=10.0)):
    """Set how many seconds a person must be detected continuously before triggering helmet check."""
    if vision_engine is None:
        raise HTTPException(status_code=503, detail="Vision engine not available.")
    vision_engine.set_dwell_seconds(seconds)
    return {"status": "ok", "person_dwell_seconds": seconds}


# Health
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/v1/health", tags=["System"])
def health():
    return {
        "status": "ok",
        "service": "armor-gateway",
        "mqtt_broker": f"{MQTT_BROKER}:{MQTT_PORT}",
        "mqtt_connected": _mqtt_client is not None,
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "timestamp": _utc_now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# ============================================================================
# Debug: recent raw MQTT messages (ring buffer)
# ============================================================================
@app.get("/api/v1/debug/mqtt", tags=["Debug"])
def debug_mqtt(limit: int = Query(default=50, ge=1, le=200)):
    """Return the most recent raw MQTT messages received from the ESP."""
    recent = _mqtt_ring[-limit:]
    return {"count": len(recent), "messages": recent}



# Telemetry  (HTTP fallback — ESP32 can also POST directly if MQTT unavailable)
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/v1/telemetry", status_code=202, tags=["Telemetry"])
def ingest_telemetry(payload: TelemetryIngestRequest):
    """
    Ingest ADXL345 / INA219 / DS18B20 telemetry from Machine Node ESP32.
    MQTT topic: armor/{device_id}/telemetry
    JSON schema per ARMOR spec section 5.1
    """
    vib = payload.vibration
    pwr = payload.power
    record = {
        "device_id":    payload.device_id,
        "timestamp":    payload.timestamp.isoformat(),
        "motor_state":  payload.motor_state,
        "accel_x":      vib.accel_x if vib else None,
        "accel_y":      vib.accel_y if vib else None,
        "accel_z":      vib.accel_z if vib else None,
        "rms":          vib.rms if vib else payload.flat_acc_mag(),
        "crest_factor": vib.crest_factor if vib else None,
        "voltage_v":    pwr.voltage_v if pwr else None,
        "current_ma":   pwr.current_ma if pwr else None,
        "power_mw":     pwr.power_mw if pwr else None,
        "temperature_c": payload.temperature_c,
    }
    store.insert_telemetry(record)

    # Predictive maintenance: score anomaly if a calibrated model exists
    try:
        package = _load_model_package(payload.device_id)
        if package is not None:
            recent = store.get_recent_samples_for_ml(payload.device_id, limit=50)
            fv = latest_feature_vector(recent, window_size=25)
            if fv is not None:
                score = _score_package(fv, package)
                if score is None:
                    return {"status": "accepted", "device_id": payload.device_id, "timestamp": _utc_now()}
                high = float(package.get("hysteresis_high", package.get("decision_threshold", 0.0)))
                low = float(package.get("hysteresis_low", high))
                is_anom = score >= high
                store.record_anomaly("machino_node_01", payload.device_id, score, high, is_anom)
                store.set_machine_state(payload.device_id, {
                    "is_anomaly": is_anom,
                })
    except Exception as e:
        print(f"[ML] Anomaly scoring failed: {e}")

    return {"status": "accepted", "device_id": payload.device_id, "timestamp": _utc_now()}


@app.get("/api/v1/telemetry/{device_id}", tags=["Telemetry"])
def get_telemetry(
    device_id: str,
    limit: int = Query(default=120, ge=1, le=1000),
):
    """Return recent telemetry records for a device (used by Streamlit charts)."""
    samples = store.get_recent_telemetry(device_id, limit=limit)
    return {"device_id": device_id, "count": len(samples), "samples": samples}


# ══════════════════════════════════════════════════════════════════════════════
# Proximity Breach  (machinocare/v1/events/proximity)
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/v1/breach", status_code=202, tags=["Safety"])
def proximity_breach(payload: ProximityBreachEvent):
    """
    Receive proximity breach event from Machine Node ESP32.
    Triggers Vision AI inspection pipeline automatically.
    MQTT topic: machinocare/v1/events/proximity
    JSON schema per ARMOR spec section 5.2
    """
    threading.Thread(
        target=_handle_breach_message,
        args=(payload.model_dump(mode="json"),),
        daemon=True,
    ).start()
    return {
        "status": "accepted",
        "device_id": payload.device_id,
        "worker_id": payload.worker_id,
        "message": "Vision inspection triggered",
        "timestamp": _utc_now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Interlock  (machinocare/v1/devices/{device}/interlock)
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/v1/interlock", status_code=200, tags=["Safety"])
def issue_interlock(payload: InterlockCommand, device_id: str = Query(default="machino_node_01")):
    """
    Issue a LOCKOUT or RESET command to Machine Node ESP32.
    Publishes to MQTT topic: armor/{device_id}/interlock
    JSON schema per ARMOR spec section 5.3
    """
    cmd_dict = payload.model_dump(mode="json")
    cmd_dict["device_id"] = device_id

    if payload.command == "LOCKOUT":
        store.set_machine_state(device_id, {
            "motor_state":     "LOCKED",
            "interlock_active": True,
        })
        store.log_interlock(cmd_dict)

    elif payload.command == "RESET":
        store.set_machine_state(device_id, {
            "motor_state":          "RUNNING",
            "interlock_active":     False,
            "proximity_breach_active": False,
            "active_worker_id":     None,
        })
        store.log_interlock(cmd_dict)
        _telegram_send(
            f"✅ ARMOR Interlock RESET\n"
            f"Device: {device_id}\n"
            f"Reset by: {payload.issued_by}\n"
            f"Time: {_utc_now()}"
        )

    # Publish to MQTT so machine node GPIO acts immediately
    _mqtt_publish(topic=f"machinocare/v1/devices/{device_id}/interlock", payload=cmd_dict)

    return {
        "status": "sent",
        "command": payload.command,
        "device_id": device_id,
        "timestamp": _utc_now(),
    }


@app.post("/api/v1/interlock/reset/{incident_id}", tags=["Safety"])
def reset_incident_interlock(
    incident_id: str,
    reset_by: str = Query(default="manager"),
    device_id: str = Query(default="machino_node_01"),
):
    """
    Manager resets interlock for a specific incident.
    Called from Streamlit dashboard or React Native app.
    """
    resolved = store.resolve_incident(incident_id, reset_by=reset_by)
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found.")

    reset_payload = InterlockCommand(
        command="RESET",
        source="DASHBOARD_OVERRIDE",
        reason=f"Manager reset — incident {incident_id}",
        issued_by=reset_by,
    )
    return issue_interlock(reset_payload, device_id=device_id)


# ══════════════════════════════════════════════════════════════════════════════
# Machine Status
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/v1/status/{device_id}", tags=["Status"])
def get_status(device_id: str):
    """
    Returns full live machine status.
    Used by Streamlit dashboard and React Native app.
    """
    state = store.get_machine_state(device_id)
    return {
        "device_id":                device_id,
        "motor_state":              state.get("motor_state", "UNKNOWN"),
        "interlock_active":         bool(state.get("interlock_active", False)),
        "last_telemetry_at":        state.get("last_telemetry_at"),
        "is_anomaly":               bool(state.get("is_anomaly", False)),
        "anomaly_score":            state.get("anomaly_score", 0.0),
        "anomaly_percentage":       state.get("anomaly_percentage", 0.0),
        "top_contributor":          state.get("top_contributor", "none"),
        "anomaly_window_count":     state.get("anomaly_window_count", 0),
        "anomaly_window_threshold": state.get("anomaly_window_threshold", 3),
        "predictive_advisory":       state.get("predictive_advisory"),
        "current_rms":              state.get("current_rms"),
        "current_voltage_v":        state.get("current_voltage_v"),
        "current_ma":               state.get("current_ma"),
        "current_temp_c":           state.get("current_temp_c"),
        "active_worker_id":         state.get("active_worker_id"),
        "vicinity_presence_active": bool(state.get("vicinity_presence_active", False)),
        "vicinity_status":          state.get("vicinity_status", "NOMINAL"),
        "proximity_breach_active":  bool(state.get("proximity_breach_active", False)),
        "server_timestamp":         _utc_now(),
    }


@app.get("/api/v1/devices", tags=["Status"])
def list_devices():
    """List all device IDs that have sent data."""
    return {"devices": store.list_all_devices()}


# ══════════════════════════════════════════════════════════════════════════════
# Incidents
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/v1/incidents", tags=["Incidents"])
def list_incidents(
    device_id: str | None = Query(default=None),
    resolved: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
):
    """Paginated incident log — used by Streamlit table and React Native log screen."""
    incidents = store.list_incidents(device_id=device_id, resolved=resolved, limit=limit)
    return {"count": len(incidents), "incidents": incidents}


@app.get("/api/v1/incidents/{incident_id}", tags=["Incidents"])
def get_incident(incident_id: str):
    """Single incident with snapshot path — used to display violation photo."""
    inc = store.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return inc


# ══════════════════════════════════════════════════════════════════════════════
# Worker Badges
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/v1/workers", status_code=201, tags=["Workers"])
def register_worker(payload: WorkerBadge):
    """Register or update an ESP32 Smart Badge (MAC → Worker ID mapping)."""
    badge = store.upsert_worker_badge(payload.model_dump(mode="json"))
    return {"status": "registered", "badge": badge}


@app.get("/api/v1/workers", tags=["Workers"])
def list_workers(active_only: bool = Query(default=False)):
    """List all registered worker badges."""
    badges = store.list_worker_badges(active_only=active_only)
    return {"count": len(badges), "badges": badges}


@app.get("/api/v1/breaches", tags=["Workers"])
def list_breaches(
    device_id: str = Query(default="machino_node_01"),
    limit: int = Query(default=30, ge=1, le=500),
):
    """Recent ESP-NOW proximity contacts reported by worker badges.

    Each row is one contact the machine node received from a badge, with the
    RSSI values and the distance estimate it derived.
    """
    events = store.get_recent_breaches(device_id, limit=limit)
    return {"count": len(events), "breaches": events}


@app.delete("/api/v1/workers/{badge_mac}", tags=["Workers"])
def deactivate_worker(badge_mac: str):
    """Deactivate a badge (worker left site)."""
    badge = store.get_worker_badge(badge_mac)
    if not badge:
        raise HTTPException(status_code=404, detail=f"Badge '{badge_mac}' not found.")
    store.upsert_worker_badge({**badge, "active": False})
    return {"status": "deactivated", "badge_mac": badge_mac}


# ============================================================================
# Calibration & Model (Predictive Maintenance / MachinoCare 1.0 ML)
# ============================================================================
@app.post("/api/v1/calibrate", tags=["Calibration"])
def calibrate(device_id: str = Query(default="machino_node_01"), contamination: float = Query(default=0.05, ge=0.01, le=0.4)):
    """Train the server-side IsolationForest on recent telemetry samples.

    Scoring runs on this PC, so the forest is kept intact rather than distilled
    into a linear surrogate for the ESP32.
    """
    samples = store.get_recent_samples_for_ml(device_id, limit=500)
    if len(samples) < 20:
        raise HTTPException(status_code=400, detail="Need at least 20 telemetry samples for calibration.")

    import numpy as np
    feature_matrix = build_feature_matrix(samples, window_size=25)
    if feature_matrix.shape[0] < 8:
        raise HTTPException(status_code=400, detail="Not enough windows for calibration.")

    model_path = Path(ARMOR_DB).parent / "models" / f"{device_id}.joblib"
    package = train_isolation_forest(
        feature_matrix,
        contamination=contamination,
        model_path=model_path,
    )

    baseline = compute_multimodal_baseline_stats(samples)

    store.save_model_package(
        machine_id="machino_node_01",
        device_id=device_id,
        package=package,
        baseline_stats=baseline,
        quality=None,
        window_count=package.get("window_count"),
    )

    return {
        "status": "completed",
        "device_id": device_id,
        "model_type": package.get("model_type"),
        "window_count": package.get("window_count"),
        "train_score_p95": package.get("train_score_p95"),
        "feature_order": package.get("feature_order"),
        "baseline_stats": baseline,
        "modalities": ["vibration", "current", "voltage", "temperature"],
        "model_package": package,
    }


@app.get("/api/v1/model/{machine_id}/{device_id}", tags=["Calibration"])
def get_model(machine_id: str, device_id: str):
    """Retrieve the latest model package for a device (used by ESP32 firmware)."""
    package = store.get_model_package(machine_id, device_id)
    if package is None:
        raise HTTPException(status_code=404, detail="No model package found.")
    return {"machine_id": machine_id, "device_id": device_id, "model_package": package}


@app.get("/api/v1/model/{device_id}", tags=["Calibration"])
def get_model_simple(device_id: str):
    """Simplified model retrieval (single machine)."""
    package = store.get_model_package("machino_node_01", device_id)
    if package is None:
        raise HTTPException(status_code=404, detail="No model package found.")
    return {"device_id": device_id, "model_package": package}


@app.get("/api/v1/anomalies", tags=["Calibration"])
def list_anomalies(
    device_id: str = Query(default="machino_node_01"),
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List recent anomaly events."""
    anomalies = store.get_recent_anomalies("machino_node_01", device_id, hours=hours, limit=limit)
    return {"count": len(anomalies), "anomalies": anomalies}


@app.get("/api/v1/telemetry/anomaly/decomposition/{device_id}", tags=["Calibration"])
def get_anomaly_decomposition(device_id: str):
    """Returns real-time anomaly percentage, modality weights, and per-parameter breakdown."""
    if device_id in _latest_decomp:
        return _latest_decomp[device_id]
    package = _load_model_package(device_id)
    recent = store.get_recent_samples_for_ml(device_id, limit=50)
    fv = latest_feature_vector(recent, window_size=10) if recent else None
    latest_sample = recent[-1] if recent else None
    decomp = decompose_anomaly(fv or np.zeros(len(FEATURE_ORDER)), package or {}, latest_sample=latest_sample)
    _latest_decomp[device_id] = decomp
    return decomp


@app.get("/api/v1/telemetry/prediction/{device_id}", tags=["Calibration"])
def get_predictive_advisory(device_id: str, force: bool = False):
    """Returns Groq LLM predictive advisory and window persistence statistics."""
    recent = store.get_recent_samples_for_ml(device_id, limit=50)
    last_rec = recent[-1] if recent else {}
    decomp = _latest_decomp.get(device_id)
    if not decomp:
        package = _load_model_package(device_id)
        if package:
            fv = latest_feature_vector(recent, window_size=25)
            if fv is not None:
                decomp = decompose_anomaly(fv, package)
    if not decomp:
        decomp = {"anomaly_percentage": 0.0, "is_anomaly": False, "modalities": {}}
    stats = rolling_anomaly_monitor.get_stats(device_id)
    advisory = generate_predictive_advisory(last_rec, decomp, stats, force_refresh=force)
    return {
        "device_id": device_id,
        "advisory": advisory,
        "window_stats": stats,
        "timestamp": _utc_now(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket — Live Push to Streamlit / React Native
# ══════════════════════════════════════════════════════════════════════════════
@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """
    Pushes live snapshots every 0.75s:
      { type, device_id, status, recent_incidents, timestamp }
    React Native and Streamlit connect here for instant in-app alerts.
    """
    await websocket.accept()

    device_id = websocket.query_params.get("device_id", "machino_node_01")

    await websocket.send_json({
        "type": "connected",
        "device_id": device_id,
        "timestamp": _utc_now(),
    })

    while True:
        try:
            # Non-blocking receive for client messages (ping / subscribe)
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_text(), timeout=LIVE_PUSH_INTERVAL
                )
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": _utc_now()})
                if data.get("device_id"):
                    device_id = data["device_id"]
            except asyncio.TimeoutError:
                pass

            state = store.get_machine_state(device_id)
            recent_telemetry = store.get_recent_telemetry(device_id, limit=1)
            open_incidents = store.list_incidents(
                device_id=device_id, resolved=False, limit=5
            )

            await websocket.send_json({
                "type": "snapshot",
                "device_id": device_id,
                "motor_state": state.get("motor_state", "UNKNOWN"),
                "interlock_active": bool(state.get("interlock_active", False)),
                "vicinity_presence_active": bool(state.get("vicinity_presence_active", False)),
                "vicinity_status": state.get("vicinity_status", "NOMINAL"),
                "proximity_breach_active": bool(state.get("proximity_breach_active", False)),
                "active_worker_id": state.get("active_worker_id"),
                "is_anomaly": bool(state.get("is_anomaly", False)),
                "anomaly_percentage": state.get("anomaly_percentage", 0.0),
                "anomaly_score": state.get("anomaly_score", 0.0),
                "top_contributor": state.get("top_contributor"),
                "anomaly_window_count": state.get("anomaly_window_count", 0),
                "predictive_advisory": state.get("predictive_advisory"),
                "current_rms": state.get("current_rms"),
                "current_temp_c": state.get("current_temp_c"),
                "current_ma": state.get("current_ma"),
                "latest_telemetry": recent_telemetry[-1] if recent_telemetry else None,
                "open_incidents": open_incidents,
                "timestamp": _utc_now(),
            })

        except WebSocketDisconnect:
            break
        except Exception:
            break
