# ARMOR — Data Streaming: Machine Node → Backend

## Transport decision

- **Primary:** MQTT over Wi-Fi (Eclipse Mosquitto on the backend host). The gateway
  subscribes to `machinocare/v1/#` at QoS 1.
- **Fallback:** HTTP POST to the same gateway when the broker is unreachable or Wi-Fi is
  down.
- **Badge → machine node:** ESP-NOW (the badge needs no Wi-Fi; the machine node measures
  RSSI).

MQTT keeps overhead and latency low on the local network; the HTTP fallback keeps
telemetry flowing during broker outages (queue in RAM, flush every 5 s, retry on
timeout).

## Topic taxonomy

| Channel | Topic / endpoint | QoS | Direction | Cadence |
|---|---|---|---|---|
| Telemetry | `machinocare/v1/devices/{id}/telemetry` · `POST /api/v1/telemetry` | 0, not retained | node → backend | 1 Hz (100 Hz sampling averaged) |
| Proximity presence / breach | `machinocare/v1/events/proximity` · `POST /api/v1/breach` | 0 | node → backend | on threshold crossing / presence change |
| Interlock command | `machinocare/v1/devices/{id}/interlock` · `POST /api/v1/interlock` | 1, not retained | backend → node | on event or operator action |
| Live snapshot | `WS /ws/live?device_id=` | — | backend → dashboards | every 0.75 s |
| Camera frame | `GET /api/v1/vision/frame` | — | backend → clients | on demand (~1–5 Hz per client) |
| Evidence image | `GET /api/v1/vision/snapshot/{filename}` | — | backend → clients | on demand |

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
(encoder removed — see merged spec Decision 4). The HTTP route answers **202** and the
response is the normalized row that was stored.

## Proximity payload (JSON)

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

`rssi_raw`/`rssi_smoothed` are measured and computed by the **machine node** (not the
badge). Threshold: EMA α = 0.35, nominal −65 dBm at 1.5 m (calibrate at the venue).

The backend reframes this event: a **vicinity presence** (`vicinity_presence_active`,
`vicinity_status`) is reported while a badge is in range, and
`proximity_breach_active` is reserved for an actual zone breach. That distinction is
what the dashboard banner, the twin worker marker and the app's Safety tab read.

## Interlock command payload (JSON)

```json
{ "command": "START" | "STOP" | "LOCKOUT" | "RESET",
  "source": "MOBILE_APP",
  "reason": "Operator started motor from mobile app",
  "issued_by": "mobile_app",
  "timestamp": "<epoch ms>" }
```

- `LOCKOUT` / `RESET` are the safety path. `RESET` clears the latch but does not
  re-energise the drive.
- `START` / `STOP` mirror the Blynk V0 motor switch. `START` is rejected with **409**
  while an interlock is active.
- `POST /api/v1/bench?enabled=true|false` publishes `BENCH_ON` / `BENCH_OFF` on the same
  topic; bench mode suppresses ESP-NOW proximity lockouts while an engineer calibrates
  the rig (no Blynk account required).

The machine node subscribes on Core 1; on `LOCKOUT` it sets a flag consumed by Core 0,
which pulls the relay (GPIO 32, active-LOW) and ENA (GPIO 25) LOW within < 50 ms. No
blocking network calls on the actuation path (Landmine C).

## Live snapshot (WebSocket)

`WS /ws/live?device_id=machino_node_01` — `{"type":"connected", …}` on connect, then
`{"type":"snapshot", …}` every 0.75 s:

```
device_id, motor_state, interlock_active, vicinity_presence_active, vicinity_status,
proximity_breach_active, active_worker_id, is_anomaly, anomaly_percentage,
anomaly_score, top_contributor, anomaly_window_count, predictive_advisory,
current_rms, current_temp_c, current_ma, latest_telemetry, open_incidents, timestamp
```

Clients may send `{"type":"ping"}`; the server replies `{"type":"pong"}`. The dashboard,
the 3D twin and the mobile app all consume this one payload — there is no second
contract to keep in sync.

## Vision transport

The app polls single JPEGs rather than an MJPEG stream:

```js
fetch(`${API_BASE}/api/v1/vision/frame?t=${Date.now()}`)
```

- No cropping, no multipart buffering, works over plain HTTP on a LAN.
- `GET /video/stream` still exists for legacy dashboard MJPEG embedding.
- Snapshots are written under `SNAPSHOT_DIR` (`data/snapshots`) and exposed by filename
  at `/api/v1/vision/snapshot/{filename}`; the backend returns the stored path, and the
  client only ever needs the basename.

## Core split (FreeRTOS)

- **Core 0 — Sensor acquisition & actuation:** ADXL345 (SPI Mode 3), INA219 (I2C),
  DS18B20 (1-Wire), 100 Hz sampling loop, SPI mutex, auto-recovery, interlock GPIO.
  Does NOT touch Wi-Fi/MQTT.
- **Core 1 — Network & interlock:** ESP-NOW receive + RSSI/EMA, MQTT client,
  telemetry/breach publish, interlock subscribe, HTTP fallback.

## Resilience

- If the MQTT broker is unreachable → queue samples in RAM, flush via HTTP POST every
  5 s, retry on timeout.
- The core safety loop (vision check → lockout → snapshot → buzzer/LED) runs offline;
  only telemetry/breach upload, the Roboflow call, the Groq advisory and Telegram need
  the network.
- Badge buzzer sounds on threshold breach even if the backend is unreachable.
- The twin and the app both detect a stalled stream and say so (`TELEMETRY LOST`,
  `STALE 8s`) instead of showing the last frame as if it were live.
