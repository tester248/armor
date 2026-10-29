# MachinoCare 2.0 — Merged Build Spec (corrected, single source of truth)

**Status:** APPROVED and **as built** — drafted 2026-10-27, reconciled with the shipped
code on 2026-10-29. Contracts in §6 now match the running endpoints; anything that was
still theoretical is marked *(planned)*.
**Sources merged:** `ARMOR_Full_Description` + `ARMOR_Work_Division_Guide` (both uploaded 2026-10-27).
**Internal codename:** A.R.M.O.R. / MachinoCare 2.0 — for internal docs only.
**PPT cover title:** NOT decided here. Per the user's 2026-10-25 constraint, the cover carries a plain academic title along "smart worker safety" lines, not a brand/product name. Two options were already offered on 2026-10-27 (see §10); pick one, do not put A.R.M.O.R. on the cover.

> How to use this: if the team approves this file, build from it and stop cross-checking the two old docs. Every conflict found between them is resolved in the Decision Log (§1) — if you disagree with a resolution, change it here, in one place, and re-issue.

## 1. Decision log — every inconsistency between the two docs, resolved

| # | Conflict | Chosen (this spec) | Why / what to change if you disagree |
|---|---|---|---|
| 1 | Which core pulls the L298N Enable pin? Full Description code: Core 1. Work Division text: Core 0. | **Core 1 (Network & Interlock task) pulls the pin LOW.** Core 0 does sensor acquisition only. | Core 1 is where the LOCKOUT payload lands, so it can act without waiting on Core 0. If you move it, move the code and the role table together. |
| 2 | MQTT topic: `…/interlock` vs `…/control` | **One topic: `machinocare/v1/devices/{deviceId}/interlock`, QoS 1, not retained.** Drop `…/control` everywhere. | Matches the Full Description's topic taxonomy table. Firmware, backend MQTT loop, and docs must all use this spelling. |
| 3 | Database: MongoDB time-series vs SQLite | **SQLite only.** | Zero setup in 24 h. The incident log, telemetry, and state tables live in SQLite; do not add MongoDB. |
| 4 | RPM: LM393 encoder phased out, yet telemetry/twin still claim "RPM measured via optical encoder" and "twin spins in sync with physical RPM" | **No encoder, no RPM claim.** Contract 4 (§6) drops `rpm`. The twin animates from motor state (`RUNNING` / `IDLE` / `LOCKED` / `UNKNOWN`) plus current draw, not a measured RPM. | With the encoder removed there is no true shaft speed to report. Do not put an RPM number on a slide unless it is labelled "state-driven animation, not measured". |
| 5 | YOLO "seg" vs detection | **For the local fallback: YOLOv8 detection only — no "-seg".** Code reads `results[0].boxes` and class labels; that is detection. *(The shipped primary path is the Roboflow workflow in Decision 13, which does return masks.)* | Detection is faster and is all the compliance rule needs offline. Do not describe the fallback as segmentation. |
| 6 | Model vs FPS: Sprint 1 demands >20 FPS, but the keremberke yolov8m model is heavy | **Primary model: YOLOv8n detection weights already found for this project (snehilsanyal `models/best.pt`, ~45 ms/image on CPU, classes Person / Hardhat / NO-Hardhat / Safety Vest / NO-Safety Vest / Mask / NO-Mask).** keremberke yolov8m is a fallback only if a GPU is available. **Drop the ">20 FPS" requirement; replace with "measure FPS on the demo laptop and put the measured number on the slide".** On a laptop CPU, expect roughly 5–10 FPS with yolov8m, ~20 FPS-class with yolov8n — verify, do not promise. | Keeps the FPS claim honest and the demo runnable offline. Whichever weights file is loaded, the compliance rule must match its exact class spellings (see §4). *(Superseded for the shipped demo by Decision 13; this remains the offline fallback path.)* |
| 7 | Latency: "under 500 ms" end-to-end; "shaft rotation halted in under 50 ms" | **Split the claim (see §7).** GPIO power cut: <50 ms. End-to-end (breach → power cut): measure it; expect roughly 0.5–2 s once EMA smoothing + wake-up + inference + MQTT are included. Sprint 3 DoD is "measured and recorded", not "under 500 ms". "Power cut" — not "shaft stopped": cutting Enable removes power; the motor then coasts to a stop. | A judge who knows motors or signal processing will poke both original wordings. Put the measured number on the slide. |
| 8 | FSM: no compliant return path; "temporary countdown buffer" with no length | **Added: INSPECTION_PENDING → NORMAL on a compliant verdict (§3). Countdown buffer named: 3 s, badge buzzer sounds during it.** (Shipped default is 2 s via `PERSON_DWELL_SECONDS`.) | Without the return arrow, a compliant worker can never leave INSPECTION_PENDING on paper. |
| 9 | Badge packet includes `raw_rssi` | **Removed from the badge packet.** RSSI is measured by the receiver (machine node), not the badge. The node attaches `rssi` (measured) and `smoothed_rssi` (EMA) when it forwards the event (§6, Contract 1). | Badge packet now: `sender_mac`, `badge_id`, `sequence_num`, `battery_voltage`. |
| 10 | SW Member 2 overload: FastAPI + Streamlit + Telegram + Expo app + Three.js twin in 24 h | **Cut order if time gets tight: (1) Expo app first, (2) twin complexity second. Keep FastAPI + Streamlit + Telegram.** Expo is stretch, not part of the hour-12 minimum viable demo. Telegram already covers "manager gets notified". | Do not let the app or the twin eat the safety loop. Twin fallback: simple primitives / state-colour CSS components over the same WebSocket stream. |
| 11 | Telegram vs "no venue-WiFi dependency" | **Core loop is offline; Telegram is not.** Vision check, lockout, snapshot, and buzzer/LED run offline. Telegram needs internet and is a bonus when WiFi is up, not part of the core safety demo. | Test tonight with laptop WiFi off: lockout + snapshot + buzzer/LED must still fire; expect no Telegram alert in that test. |
| 12 | IDs: `worker_id` / `badge_id` / `EMP-402` / `BADGE-EMP-402` used interchangeably | **One ID: `badge_id`, e.g. `BADGE-EMP-402`.** Use it in every contract. Where a contract previously said `worker_id`, it now means the same `badge_id` value. | Prevents a lookup miss between badge, vision verdict, and incident log. |
| 13 | YOLOv8n detection plan (§Decision 6) vs the vision engine that actually shipped | **Roboflow workflow `helmet-check-hackathon-demo-1793134805931` (RF-DETR + SAM 3) is the primary path**, with a local helmet-colour heuristic whenever the key or the network is missing. The verdict is fail-closed: an 8 s timeout reports `HELMET_FAIL`. | The workflow returns the verdict, compliance ratio and an annotated image in one call; the local path keeps the demo alive offline (and must be labelled a heuristic on stage). |
| 14 | Decision 10 said cut the Expo app first | **The app shipped** — five tabs (Live, Safety, Vision, Records, System), Material 3 dark "Blueprint Control" theme, on the orphan branch `armor-app`. For LAN testers, ship the exported **web build**; native builds go through EAS (`@u4up/armor-mobile`). | The twin turned out cheap enough to keep both. Keep `armor-app` history separate — port changes by hand. |
| 15 | Interlock was `LOCKOUT` \| `RESET` only | **Four commands: `START`, `STOP`, `LOCKOUT`, `RESET`.** `START` returns **409** while interlocked; `RESET` clears the latch but does **not** re-energise the drive — a separate `START` is required. | Mirrors the firmware rule `motor_requested && !interlock`, so a reset can never restart a motor by accident. |
| 16 | Lockout only on a vision violation | **Added the ML gate:** three anomalous windows inside five seconds (`ANOMALY_WINDOW_SECONDS=5`, `ANOMALY_LOCKDOWN_THRESHOLD=3`) also issues `LOCKOUT`. Single spikes stay advisory. | Vision sees PPE; the anomaly engine sees the machine. Both are safety-relevant. |
| 17 | Contract paths drifted from the code | **Use the running paths:** proximity is `POST /api/v1/breach` (not `/api/v1/events/proximity`), live stream is `WS /ws/live` (not `/api/v1/ws/live`), reset is `POST /api/v1/interlock/reset/{incident_id}`. | The old spellings appear in the historical plan docs; the code and this spec are now the source of truth. |

## 2. System in one paragraph

MachinoCare 1.0 was passive monitoring (RS-555 motor, INA219 current/voltage, DS18B20 temperature, ADXL345 vibration, ESP32 node, Streamlit dashboard). MachinoCare 2.0 adds an active safety cell: a wearable ESP32 badge broadcasts ESP-NOW beacons; the machine ESP32 node smooths the measured RSSI (EMA, α = 0.35) and, at the calibrated 1.5 m threshold (nominal −65 dBm — calibrate at the venue, do not trust the number blindly), sends a wake-up to the FastAPI backend; the backend freezes the laptop webcam frame, runs the Roboflow helmet/PPE workflow on it (local CV fallback when the key or network is absent), and if a PPE item is missing it publishes MQTT LOCKOUT. The machine node (Core 1) cuts 12 V via the relay (GPIO 32, active-LOW) and pulls L298N ENA (GPIO 25) LOW, captures a snapshot, logs the incident, and — when internet is available — sends a Telegram alert to the manager. A multi-modal anomaly gate (3 anomalous windows in 5 s) enters the same lockout without a vision event. (Authoritative pinout: docs/hardware-pinout.md)

## 3. Finite state machine (corrected)

```
NORMAL ── smoothed RSSI ≥ −65 dBm ──► PROXIMITY_ALERT ── camera active ──► INSPECTION_PENDING
   ▲                                                                          │
   │  compliant verdict (within the dwell window)                                   │ violation OR timeout
   │                                                                          ▼
   └────────────── manager ack + compliant re-check + RESET ──◄── LOCKOUT ◄──┘
                     (POST /api/v1/interlock/reset/{incident_id}; Enable HIGH)
```

- **NORMAL:** Motor running, Core 0 sampling, Core 1 listening. `motor_state` is `RUNNING`; it becomes `IDLE` after `STOP`.
- **PROXIMITY_ALERT:** Badge inside 1.5 m. Wake-up ping dispatched. Badge buzzer sounds.
- **INSPECTION_PENDING:** The frame is frozen and the helmet/PPE workflow runs on it. A **dwell countdown** (`PERSON_DWELL_SECONDS`, default 2 s) delays the freeze so the worker is fully in frame; the verdict is held on screen for `FREEZE_HOLD_DURATION_S` (default 4 s). Badge buzzer warns during the buffer. **Compliant → NORMAL. Violation or timeout → LOCKOUT.**
- **LOCKOUT:** Latched. Core 1 holds Enable LOW, red LED on, telemetry flagged with the lockout condition code. Snapshot captured, incident logged in SQLite, Telegram alert attempted (internet-dependent). **A sustained ML anomaly (3 windows in 5 s) enters the same state** without a vision event.
- **RESET:** Only after manager acknowledgement AND a compliant re-check (or an explicit, logged manager override). Enable restored HIGH → NORMAL. There is no automatic reset on timeout.

## 4. Vision pipeline (Roboflow Workflow: RF-DETR + SAM 3)

- Model: Roboflow Workflow "Helmet Check Hackathon Demo"
  - Workspace: `ashwin-mathur`
  - Workflow ID: `helmet-check-hackathon-demo-1793134805931`
  - Endpoint: `POST https://serverless.roboflow.com/ashwin-mathur/workflows/helmet-check-hackathon-demo-1793134805931`
  - Declared input: `image` (image)
- Client: `inference_sdk.InferenceHTTPClient` with header-based auth
  - `api_key_transport="header"` (never query string or body)
  - Per-request timeout: 30 s (configurable via `ROBOFLOW_REQUEST_TIMEOUT_S`)
  - Retries: 3 attempts with exponential backoff (1s, 2s, 4s)
  - Typed errors: `RoboflowAuthError` (401/403), `RoboflowTimeoutError`, `RoboflowResponseError`
- Auth: `ROBOFLOW_API_KEY` from `.env` (gitignored). Get it at app.roboflow.com/settings/api — use a **secret (private)** key, not a publishable one.
- Frame handling (shipped): continuous capture (~30 fps) behind a three-tier person gate (YOLOv8n → Haar → HOG). No workflow call until a person is detected, so idle frames cost almost nothing.
- **Person-gated freeze (shipped):** the feed freezes on the frame where a person is detected, a dwell countdown (`/api/v1/vision/dwell-seconds`, default configurable) runs so the worker is fully in frame, and only then is the workflow called. Verdict and masks are held on the frozen frame for a hold period, then the live feed resumes or `POST /api/v1/vision/unfreeze` forces it.
- **Frame transport (shipped):** `GET /api/v1/vision/frame` returns one JPEG (cache-busted by clients); `GET /video/stream` remains as the legacy MJPEG path. Snapshots are served from `/api/v1/vision/snapshot/{filename}`.
- Compliance rule: PASS if `compliance_ratio >= HELMET_COMPLIANCE_THRESHOLD` (default 0.65). The ratio is read from the workflow's real output (discovered dynamically from response keys such as `compliance_ratio`, `confidence`, `score`); if the workflow omits it, 0.9/0.1 is derived from pass/fail.
- Helmet status: discovered dynamically from response keys (`helmet_status`, `status`, `helmet`, `result`, `label`, `prediction`).
- Output image: base64-decoded from workflow output keys (`output_image`, `annotated_image`, `segmented_helmet_image`, …) and written to the snapshot directory. Never logged or held in memory longer than needed.
- Fallback: when `ROBOFLOW_API_KEY` is not configured, or the workflow call fails, the local helmet-colour heuristic (`_local_safety_inspect`, labelled `ARMOR Edge Vision (Local)`) returns the verdict. It is a heuristic on the head ROI, so describe it as such — the cloud workflow is the real model. `inspect()` is fail-closed: an 8 s timeout returns `compliant=False` / `HELMET_FAIL`.
- Verification: `backend.vision.smoke_test(image_path)` runs the workflow on one sample image and asserts output keys exist.

## 5. Firmware split (corrected)

- **Core 0 — Sensor acquisition:** ADXL345 (SPI Mode 3), INA219 (I2C), DS18B20 (1-Wire), 100 Hz sampling loop, SPI mutex, SPI auto-recovery (re-init bus, CS HIGH, rewrite register 0x2D = 0x08). Core 0 does NOT touch the Enable pin.
- **Core 1 — Network & interlock:** ESP-NOW beacon reception + RSSI measurement/EMA, MQTT listener on `machinocare/v1/devices/{deviceId}/interlock` (QoS 1), WebSocket telemetry. On LOCKOUT: set `interlock_engaged`, cut 12 V relay (GPIO 32, active-LOW) + `digitalWrite(ENA, LOW)` (GPIO 25). ENA HIGH / relay HIGH at boot. (See docs/hardware-pinout.md)
- Badge: ESP-NOW beacons only (`sender_mac`, `badge_id`, `sequence_num`, `battery_voltage`); buzzer on threshold breach / unacknowledged breach. No `raw_rssi` in the badge packet.

## 6. Contracts (single versions — as built)

### Contract 1 — Proximity breach event (machine node → backend)
HTTP `POST /api/v1/breach` (202) or MQTT `machinocare/v1/events/proximity`.
`{ "device_id": "machino_node_01", "worker_id": "BADGE-EMP-402", "badge_mac": "24:6F:28:AB:C1:02", "rssi_raw": -68, "rssi_smoothed": -64.2, "distance_est_m": 1.2, "timestamp": <epoch ms> }`
`rssi_raw`/`rssi_smoothed` are measured and computed by the machine node. The backend
answers 202 and does not wait on vision.

### Contract 2 — Interlock command (backend → machine node) — ONLY topic
MQTT `machinocare/v1/devices/{deviceId}/interlock` (QoS 1, not retained), also
`POST /api/v1/interlock?device_id={deviceId}` for the same effect over HTTP.
`{ "command": "START" | "STOP" | "LOCKOUT" | "RESET", "source": "MOBILE_APP", "reason": "…", "issued_by": "mobile_app", "timestamp": <epoch ms> }`
`START` while interlocked → **409**. `RESET` clears the latch but does not restart the
drive.

### Contract 3 — Vision verdict (vision engine → backend)
The engine runs in-process; the client-facing surface is
`POST /api/v1/vision/inspect` (synchronous), `POST /api/v1/vision/inspect/start` +
`GET …/inspect/status` (async) and `GET /api/v1/vision/state`.
Verdict fields (from `_make_result` in `vision.py`): `worker_id`, `device_id`,
`compliant: true|false`, `compliance_ratio`, `threshold_used`, `label`
(`HELMET_PASS` / `HELMET_FAIL`), `confidence`, `snapshot_path`, `detection_source`
(`ROBOFLOW_RF_DETR_SAM3`, `ARMOR Edge Vision (Local)`, `… (Fallback)`), `details`,
`timestamp`.
Fail-closed rule: if the inspection cannot return a result within 8 s, `inspect()`
returns `compliant: false` with `label: "HELMET_FAIL"` — the gate assumes a violation.
A `null` verdict (no path currently emits one) is what the breach handler treats as
`VICINITY_OCCUPIED_UNCHECKED`, i.e. presence recorded, no lockout.

### Contract 4 — Live telemetry / twin stream (backend → dashboards)
WebSocket `/ws/live?device_id={deviceId}`, one `type: "snapshot"` frame every 0.75 s:
`{ "device_id", "motor_state": "RUNNING" | "IDLE" | "LOCKED" | "UNKNOWN", "interlock_active", "vicinity_presence_active", "vicinity_status", "proximity_breach_active", "active_worker_id", "is_anomaly", "anomaly_percentage", "anomaly_score", "top_contributor", "anomaly_window_count", "predictive_advisory", "current_rms", "current_temp_c", "current_ma", "latest_telemetry", "open_incidents", "timestamp" }`
**No `rpm` field** (encoder removed — see Decision 4). Twin motor animation is driven by
`motor_state` plus current draw, not by a measured RPM.

### Other endpoints
`POST /api/v1/interlock/reset/{incident_id}` (manager reset, §3) ·
`POST /api/v1/bench?enabled=true|false` (suppress proximity lockouts while calibrating) ·
`GET /api/v1/health` · `GET /api/v1/incidents` · `GET /api/v1/telemetry/{device_id}` ·
`POST /api/v1/calibrate` · `GET /api/v1/telemetry/anomaly/decomposition/{device_id}`.
SQLite tables: `telemetry`, `machine_state`, `incidents`, `worker_badges`,
`breach_events`, `interlock_log`.

## 7. Numbers to say on the slide (and only these)

- L298N Enable pull-down (power cut): **<50 ms** (GPIO action itself).
- End-to-end breach → power cut: **measured value, expected roughly 0.5–2 s** — measure at the venue and write the measured number down. Do not claim <500 ms.
- Say **"power cut"**, not "shaft stopped" — the motor coasts after power is removed.
- FPS: **measured on the demo laptop** with whichever model actually loaded (Roboflow workflow or the local fallback). Do not claim >20 FPS unless measured.
- Danger zone: **1.5 m, nominal −65 dBm, EMA α = 0.35** — calibrated at the venue with a person walking in, not a wall.

## 8. Roles & sprints (unchanged structure, corrected DoDs)

- **HW Member 1:** machine node + interlock (Core 0 sensors, Core 1 interlock per §5).
- **HW Member 2:** wearable badge + buzzer; calibrate RSSI at 0.5 / 1.0 / 1.5 / 2.0 m at the venue.
- **SW Member 1:** vision pipeline (§4).
- **SW Member 2:** FastAPI + SQLite + Streamlit + Telegram **+ Expo app + Three.js twin (all shipped)**.
- **Sprint 1 (0–6 h):** standalone modules. **Sprint 2 (6–12 h): hour-12 minimum viable demo = full loop badge → wake-up → helmet verdict → MQTT LOCKOUT → Enable LOW.** **Sprint 3 (12–18 h):** hardening + Telegram + measured latency. **Sprint 4 (18–24 h):** polish, twin, mobile app, pitch prep.
- Fallbacks already in the plan, kept: RSSI unreliable → OpenCV tripwire trigger; Streamlit video lag → FastAPI JPEG frame / snapshot-only; no PPE props → mask pivot / COCO hazard pivot / phone-screen hard-hat image; twin scope creep → CSS state components.

## 9. Demo script (2 minutes, corrected wording)

0:00–0:30 normal running: dashboard, twin (state-driven animation) and the mobile app on the same feed. 0:30–1:00 badge crosses 1.5 m → buzzer, feed freezes, twin ring amber and the worker marker appears. 1:00–1:30 no hard hat → red NO-Hardhat box, MQTT LOCKOUT, relay + ENA LOW (**power cut**, motor coasts), twin red and spinning down. 1:30–2:00 the same incident on the app's Records tab, Telegram alert (if WiFi up) on the manager phone, manager reset then START, motor resumes. If WiFi is down, say so plainly: the safety action already happened offline; Telegram is the notification layer, not the safety layer.

## 10. Open items (post-build)

1. **PPT cover title** — academic style, "smart worker safety" lines, not A.R.M.O.R. (user constraint, 2026-10-25). Options already offered 2026-10-27: *"A Proximity-Triggered, Vision-Verified Safety Architecture for Industry 4.0 Workcells"* or *"Smart Worker Safety Through Vision and Automation"* — pick one.
2. **Trigger** — this spec follows the two docs (RSSI/ESP-NOW primary). If the team wants HC-SR04 instead, that is a separate call: note the wiring gotcha (5 V ECHO → ESP32 GPIO needs a 1k/2k divider or level shifter; ±15° beam, angle 2–3 sensors outward, calibrate with a person).
3. **Any Decision Log row the team disagrees with** — change it here, not in the old docs.
4. **Native mobile distribution** — the app is built and EAS-configured (`@u4up/armor-mobile`, `preview` = internal). iOS device installs still need an Apple Developer Program membership; until then, share the exported web build on the LAN.
