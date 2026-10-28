# ARMOR — Data Streaming: Machine Node → Backend

## Transport decision
- **Primary:** MQTT over WiFi (Eclipse Mosquitto on the backend host).
- **Fallback:** HTTP POST (when the broker is unreachable or WiFi is down).
- **Badge → machine node:** ESP-NOW (badge needs no WiFi; machine node measures RSSI).

Rationale: MQTT gives lower overhead and lower latency on the local network; HTTP
fallback keeps telemetry flowing during broker outages (old-repo pattern: queue
samples, flush every 5 s, retry on timeout).

## Topic taxonomy (QoS per merged build spec)
| Channel | Topic / Endpoint | QoS | Direction | Cadence |
|---|---|---|---|---|
| Telemetry | `machinocare/v1/devices/{id}/telemetry` (MQTT) or `POST /api/v1/telemetry` | 0, not retained | machine → backend | 1 Hz (100 Hz sampling averaged) |
| Proximity breach | `machinocare/v1/events/proximity` (MQTT) or `POST /api/v1/breach` | 0 | machine → backend | on threshold crossing only |
| Interlock command | `machinocare/v1/devices/{id}/interlock` | 1, not retained | backend → machine | on event |

## Telemetry payload (JSON)
```json
{
  "device_id": "machino_node_01",
  "timestamp": "<epoch ms or ISO8601>",
  "motor_state": "RUNNING",
  "vibration": { "accel_x": 0.02, "accel_y": 0.05, "accel_z": 0.98, "rms": 0.048, "crest_factor": 2.1 },
  "power": { "voltage_v": 12.1, "current_ma": 420.5, "power_mw": 5088.05 },
  "temperature_c": 34.2
}
```
Matches `TelemetryIngestRequest` in `armor-backend/backend/models.py`. No `rpm` field
(encoder removed — see merged spec Decision 4).

## Proximity breach payload (JSON)
```json
{
  "device_id": "machino_node_01",
  "worker_id": "BADGE-EMP-402",
  "badge_mac": "24:6F:28:AB:C1:02",
  "rssi_raw": -68,
  "rssi_smoothed": -64.2,
  "distance_est_m": 1.2,
  "timestamp": "<epoch ms>"
}
```
`rssi`/`smoothed_rssi` are measured and computed by the **machine node** (not the
badge). Threshold: EMA α = 0.35, nominal −65 dBm at 1.5 m (calibrate at venue).

## Interlock command payload (JSON)
```json
{ "command": "LOCKOUT" | "RESET", "reason": "PPE_VIOLATION_MISSING_HELMET",
  "incident_id": "INC-...", "timestamp": "<epoch ms>" }
```
Machine node subscribes on Core 1; on `LOCKOUT`, sets a flag consumed by Core 0,
which pulls the relay (GPIO 32) LOW and ENA (GPIO 25) LOW within < 50 ms. No
blocking network calls on the actuation path (Landmine C).

## Core split (FreeRTOS)
- **Core 0 — Sensor acquisition & actuation:** ADXL345 (SPI Mode 3), INA219 (I2C),
  DS18B20 (1-Wire), 100 Hz sampling loop, SPI mutex, auto-recovery, interlock GPIO.
  Does NOT touch WiFi/MQTT.
- **Core 1 — Network & interlock:** ESP-NOW receive + RSSI/EMA, MQTT client,
  telemetry/breach publish, interlock subscribe, HTTP fallback.

## Resilience
- If MQTT broker unreachable → queue samples in RAM, flush via HTTP POST every 5 s,
  retry on timeout (old-repo pattern).
- Core safety loop (vision check → lockout → snapshot → buzzer/LED) runs offline;
  only telemetry/breach upload and Telegram need internet.
- Badge buzzer sounds on threshold breach even if the backend is unreachable.
