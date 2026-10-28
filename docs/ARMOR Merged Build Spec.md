# MachinoCare 2.0 — Merged Build Spec (corrected, single source of truth)

**Status:** DRAFT for team approval — prepared 2026-10-27 evening, from the two docs the user shared that day.
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
| 4 | RPM: LM393 encoder phased out, yet telemetry/twin still claim "RPM measured via optical encoder" and "twin spins in sync with physical RPM" | **No encoder, no RPM claim.** Contract 4 (§6) drops `rpm`. The twin animates from motor state (RUNNING = spinning, LOCKED_OUT = stopped) + PWM/enable state, not a measured RPM. | With the encoder removed there is no true shaft speed to report. Do not put an RPM number on a slide unless it is labelled "state-driven animation, not measured". |
| 5 | YOLO "seg" vs detection | **YOLOv8 detection only — drop "-seg".** Code reads `results[0].boxes` and class labels; that is detection. | Detection is faster and is all the compliance rule needs. No masks in the pipeline, dashboard, or slides. |
| 6 | Model vs FPS: Sprint 1 demands >20 FPS, but the keremberke yolov8m model is heavy | **Primary model: YOLOv8n detection weights already found for this project (snehilsanyal `models/best.pt`, ~45 ms/image on CPU, classes Person / Hardhat / NO-Hardhat / Safety Vest / NO-Safety Vest / Mask / NO-Mask).** keremberke yolov8m is a fallback only if a GPU is available. **Drop the ">20 FPS" requirement; replace with "measure FPS on the demo laptop and put the measured number on the slide".** On a laptop CPU, expect roughly 5–10 FPS with yolov8m, ~20 FPS-class with yolov8n — verify, do not promise. | Keeps the FPS claim honest and the demo runnable offline. Whichever weights file is loaded, the compliance rule must match its exact class spellings (see §4). |
| 7 | Latency: "under 500 ms" end-to-end; "shaft rotation halted in under 50 ms" | **Split the claim (see §7).** GPIO power cut: <50 ms. End-to-end (breach → power cut): measure it; expect roughly 0.5–2 s once EMA smoothing + wake-up + inference + MQTT are included. Sprint 3 DoD is "measured and recorded", not "under 500 ms". "Power cut" — not "shaft stopped": cutting Enable removes power; the motor then coasts to a stop. | A judge who knows motors or signal processing will poke both original wordings. Put the measured number on the slide. |
| 8 | FSM: no compliant return path; "temporary countdown buffer" with no length | **Added: INSPECTION_PENDING → NORMAL on a compliant verdict (§3). Countdown buffer named: 3 s, badge buzzer sounds during it.** | Without the return arrow, a compliant worker can never leave INSPECTION_PENDING on paper. |
| 9 | Badge packet includes `raw_rssi` | **Removed from the badge packet.** RSSI is measured by the receiver (machine node), not the badge. The node attaches `rssi` (measured) and `smoothed_rssi` (EMA) when it forwards the event (§6, Contract 1). | Badge packet now: `sender_mac`, `badge_id`, `sequence_num`, `battery_voltage`. |
| 10 | SW Member 2 overload: FastAPI + Streamlit + Telegram + Expo app + Three.js twin in 24 h | **Cut order if time gets tight: (1) Expo app first, (2) twin complexity second. Keep FastAPI + Streamlit + Telegram.** Expo is stretch, not part of the hour-12 minimum viable demo. Telegram already covers "manager gets notified". | Do not let the app or the twin eat the safety loop. Twin fallback: simple primitives / state-colour CSS components over the same WebSocket stream. |
| 11 | Telegram vs "no venue-WiFi dependency" | **Core loop is offline; Telegram is not.** Vision check, lockout, snapshot, and buzzer/LED run offline. Telegram needs internet and is a bonus when WiFi is up, not part of the core safety demo. | Test tonight with laptop WiFi off: lockout + snapshot + buzzer/LED must still fire; expect no Telegram alert in that test. |
| 12 | IDs: `worker_id` / `badge_id` / `EMP-402` / `BADGE-EMP-402` used interchangeably | **One ID: `badge_id`, e.g. `BADGE-EMP-402`.** Use it in every contract. Where a contract previously said `worker_id`, it now means the same `badge_id` value. | Prevents a lookup miss between badge, vision verdict, and incident log. |

## 2. System in one paragraph

MachinoCare 1.0 was passive monitoring (RS-555 motor, INA219 current/voltage, DS18B20 temperature, ADXL345 vibration, ESP32 node, Streamlit dashboard). MachinoCare 2.0 adds an active safety cell: a wearable ESP32 badge broadcasts ESP-NOW beacons; the machine ESP32 node smooths the measured RSSI (EMA, α = 0.35) and, at the calibrated 1.5 m threshold (nominal −65 dBm — calibrate at the venue, do not trust the number blindly), sends a wake-up to the FastAPI backend; the backend runs YOLOv8n PPE detection on the laptop webcam frame inside the ROI tripwire polygon; if hard hat or vest is missing, the backend sends MQTT LOCKOUT and the machine node (Core 1) cuts 12 V via the relay (GPIO 32, active-LOW) and pulls L298N ENA (GPIO 25) LOW, captures a snapshot, and - when internet is available - sends a Telegram alert to the manager. (Authoritative pinout: docs/hardware-pinout.md)

## 3. Finite state machine (corrected)

```
NORMAL ── smoothed RSSI ≥ −65 dBm ──► PROXIMITY_ALERT ── camera active ──► INSPECTION_PENDING
   ▲                                                                          │
   │  compliant verdict (within 3 s buffer)                                   │ violation OR timeout
   │                                                                          ▼
   └────────────── manager ack + compliant re-check + RESET ──◄── LOCKOUT ◄──┘
                     (POST /api/v1/interlock/reset; Enable HIGH)
```

- **NORMAL:** Motor running, Core 0 sampling, Core 1 listening.
- **PROXIMITY_ALERT:** Badge inside 1.5 m. Wake-up ping dispatched. Badge buzzer sounds.
- **INSPECTION_PENDING:** Camera + YOLO inference active. Motor still running under a **3 s countdown buffer**; badge buzzer warns during the buffer. **Compliant → NORMAL. Violation or timeout → LOCKOUT.**
- **LOCKOUT:** Latched. Core 1 holds Enable LOW, red LED on, telemetry flagged with the lockout condition code. Snapshot captured, incident logged in SQLite, Telegram alert attempted (internet-dependent).
- **RESET:** Only after manager acknowledgement AND a compliant re-check (or an explicit, logged manager override). Enable restored HIGH → NORMAL. There is no automatic reset on timeout.

## 4. Vision pipeline (detection, not segmentation)

- Model: YOLOv8n detection, `snehilsanyal/Construction-Site-Safety-PPE-Detection` → `models/best.pt`, offline on the laptop. Fallback only: keremberke yolov8m (slower; do not claim its FPS).
- Confidence threshold: `conf = 0.40`.
- Frame handling: event-driven only (idle until a proximity wake-up); evaluate every 3rd–5th frame to cut compute.
- ROI: OpenCV tripwire polygon over the danger zone; only boxes whose centre falls inside the polygon count.
- Compliance rule (must match the loaded weights' spellings exactly): **violation = Person in ROI AND (NO-Hardhat OR NO-Safety Vest)**. Note the spellings differ between weight sets (`NO-Hardhat` here vs `No hardhat` in Roboflow's hosted model) — check the string before the demo, not during it.
- Output: verdict + annotated frame (boxes only, no masks).

## 5. Firmware split (corrected)

- **Core 0 — Sensor acquisition:** ADXL345 (SPI Mode 3), INA219 (I2C), DS18B20 (1-Wire), 100 Hz sampling loop, SPI mutex, SPI auto-recovery (re-init bus, CS HIGH, rewrite register 0x2D = 0x08). Core 0 does NOT touch the Enable pin.
- **Core 1 — Network & interlock:** ESP-NOW beacon reception + RSSI measurement/EMA, MQTT listener on `machinocare/v1/devices/{deviceId}/interlock` (QoS 1), WebSocket telemetry. On LOCKOUT: set `interlock_engaged`, cut 12 V relay (GPIO 32, active-LOW) + `digitalWrite(ENA, LOW)` (GPIO 25). ENA HIGH / relay HIGH at boot. (See docs/hardware-pinout.md)
- Badge: ESP-NOW beacons only (`sender_mac`, `badge_id`, `sequence_num`, `battery_voltage`); buzzer on threshold breach / unacknowledged breach. No `raw_rssi` in the badge packet.

## 6. Contracts (single versions — delete all other spellings)

### Contract 1 — Proximity breach event (machine node → backend)
HTTP POST `/api/v1/events/proximity` or MQTT `machinocare/v1/events/proximity` (QoS 0).
`{ "badge_id": "BADGE-EMP-402", "machine_id": "CELL-RS555-01", "rssi": -68, "smoothed_rssi": -64.2, "timestamp": <epoch ms> }`
`rssi`/`smoothed_rssi` are measured and computed by the machine node.

### Contract 2 — Interlock command (backend → machine node) — ONLY topic
MQTT `machinocare/v1/devices/{deviceId}/interlock` (QoS 1, not retained).
`{ "command": "LOCKOUT" | "RESET", "reason": "PPE_VIOLATION_MISSING_HELMET", "incident_id": "INC-20261024-089", "timestamp": <epoch ms> }`

### Contract 3 — Vision verdict (vision engine → backend)
HTTP POST `/api/v1/vision/verdict`.
`{ "incident_id", "badge_id", "ppe_compliant": true|false, "detected_objects": ["Person", "NO-Hardhat", "Safety Vest"], "confidence": 0.91, "image_snapshot_base64": "…" }`

### Contract 4 — Live telemetry / twin stream (backend → dashboards)
WebSocket `/api/v1/ws/live`.
`{ "machine_state": "RUNNING" | "WARNING" | "LOCKED_OUT", "motor_enabled": true|false, "pwm_duty": <0–100>, "current_draw_a", "temp_c", "vibration_rms", "active_badge_id", "zone_breached": true|false, "last_incident": { "incident_id", "type": "PPE_VIOLATION", "timestamp" } }`
**No `rpm` field** (encoder removed — see Decision 4). Twin motor animation is driven by `machine_state`/`motor_enabled`, not by a measured RPM.

### Other endpoints
`POST /api/v1/interlock/reset` (manager reset, §3) · `GET /api/v1/health` · SQLite tables: telemetry, machine states, incidents.

## 7. Numbers to say on the slide (and only these)

- L298N Enable pull-down (power cut): **<50 ms** (GPIO action itself).
- End-to-end breach → power cut: **measured value, expected roughly 0.5–2 s** — measure at the venue and write the measured number down. Do not claim <500 ms.
- Say **"power cut"**, not "shaft stopped" — the motor coasts after power is removed.
- FPS: **measured on the demo laptop** with the yolov8n weights. Do not claim >20 FPS unless measured.
- Danger zone: **1.5 m, nominal −65 dBm, EMA α = 0.35** — calibrated at the venue with a person walking in, not a wall.

## 8. Roles & sprints (unchanged structure, corrected DoDs)

- **HW Member 1:** machine node + interlock (Core 0 sensors, Core 1 interlock per §5).
- **HW Member 2:** wearable badge + buzzer; calibrate RSSI at 0.5 / 1.0 / 1.5 / 2.0 m at the venue.
- **SW Member 1:** vision pipeline (§4).
- **SW Member 2:** FastAPI + SQLite + Streamlit + Telegram; **Expo app = stretch, twin = simplified primitives, both after the core loop works.**
- **Sprint 1 (0–6 h):** standalone modules. **Sprint 2 (6–12 h): hour-12 minimum viable demo = full loop badge → wake-up → YOLO verdict → MQTT LOCKOUT → Enable LOW.** **Sprint 3 (12–18 h):** hardening + Telegram + measured latency. **Sprint 4 (18–24 h):** polish, twin, pitch prep.
- Fallbacks already in the plan, kept: RSSI unreliable → OpenCV tripwire trigger; Streamlit video lag → FastAPI MJPEG / snapshot-only; no PPE props → mask pivot / COCO hazard pivot / phone-screen hard-hat image; twin scope creep → CSS state components.

## 9. Demo script (2 minutes, corrected wording)

0:00–0:30 normal running, dashboard + twin (state-driven animation). 0:30–1:00 badge crosses 1.5 m → buzzer, camera wakes, twin ring amber. 1:00–1:30 no hard hat → red NO-Hardhat box, MQTT LOCKOUT, Enable LOW (**power cut**, motor coasts), twin red. 1:30–2:00 Telegram alert (if WiFi up) shown on manager phone, compliant re-check + manager reset, motor resumes, Simulation Mode for Q&A. If WiFi is down, say so plainly: the safety action already happened offline; Telegram is the notification layer, not the safety layer.

## 10. Still open — not decided in this draft

1. **PPT cover title** — academic style, "smart worker safety" lines, not A.R.M.O.R. (user constraint, 2026-10-25). Options already offered 2026-10-27: *"A Proximity-Triggered, Vision-Verified Safety Architecture for Industry 4.0 Workcells"* or *"Smart Worker Safety Through Vision and Automation"* — pick one.
2. **Trigger** — this spec follows the two docs (RSSI/ESP-NOW primary). If the team wants HC-SR04 instead, that is a separate call: note the wiring gotcha (5 V ECHO → ESP32 GPIO needs a 1k/2k divider or level shifter; ±15° beam, angle 2–3 sensors outward, calibrate with a person).
3. **Any Decision Log row the team disagrees with** — change it here, not in the old docs.
