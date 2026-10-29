# ARMOR: 24-Hour Hackathon Work Division & Execution Roadmap

> **Status (2026-10-29): this plan was executed.** The sprint table below is kept as
> the historical division of work. What actually shipped, and where it differs from
> the plan:
>
> | Planned | Shipped |
> |---|---|
> | YOLO instance segmentation masks | Roboflow workflow (RF-DETR + SAM 3) with person-gated **feed freeze**, dwell countdown and a local CV fallback |
> | MQTT topics `armor/machine01/*` | `machinocare/v1/devices/{id}/telemetry` and `…/interlock` |
> | Enable pin LOW on lockout | Relay GPIO 32 (hard 12 V cut) **and** ENA GPIO 25 LOW |
> | Expo app as stretch | Shipped: 5-tab Expo app on the `armor-app` branch, plus a web build for LAN testers |
> | Twin as "simple primitives" | Shipped: full three.js machine model with state-driven animation |
> | Streamlit only | Streamlit + 3D twin + mobile app, all on one `/ws/live` feed |
> | — (not planned) | Multi-modal IsolationForest anomaly engine, 3 anomalous windows in 5 s → auto lockout, Groq advisory, bench mode, START/STOP motor control |
>
> See `README.md` for run instructions and `docs/ARMOR_System_Architecture_and_Implementation_Plan.md`
> for the as-built architecture.

---

### 1. Team Roles & Responsibilities

To maximize speed and prevent blocking dependencies during a 24-hour sprint, the 4-member team is divided strictly across specialized domains:

```
                  ┌──────────────────────────────────────────┐
                  │        ARMOR PROJECT LEADERSHIP          │
                  └────────────────────┬─────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌───────────────────────┐                             ┌───────────────────────┐
│     HARDWARE TEAM     │                             │     SOFTWARE TEAM     │
├───────────────────────┤                             ├───────────────────────┤
│ HW 1: Machine Rig &   │                             │ SW 1: Vision AI & Edge│
│       Sensors Lead    │                             │       Segmentation    │
│ HW 2: Wearable Badge &│                             │ SW 2: Backend Gateway,│
│       Proximity Lead  │                             │       Dashboard & App │
└───────────────────────┘                             └───────────────────────┘
```

#### Hardware Team
* **HW Member 1 (Machine Rig, Sensors & Interlock Specialist)**:
  * RS-555 12V DC motor mounting, L298N dual H-Bridge motor driver wiring.
  * ADXL345 accelerometer (SPI Mode 3), INA219 power sensor (I2C), and DS18B20 temperature sensor (OneWire). *(Note: LM393 optical encoder omitted).*
  * ESP32 firmware for sensor reading, MQTT publishing, and L298N Enable pin pull-down logic.
* **HW Member 2 (Wearable Badge & Proximity Specialist)**:
  * ESP32 Smart Badge assembly (LiPo battery, charger module, status LEDs, piezo buzzer).
  * ESP-NOW radio broadcaster firmware transmitting unique Worker IDs and RSSI beacons.
  * Exponential Moving Average (EMA) signal filtering on the machine node for reliable 1.5m proximity detection.

#### Software Team
* **SW Member 1 (Vision AI & Edge Analytics Specialist)**:
  * OpenCV webcam frame ingestion pipeline.
  * Person-gated **feed freeze** with dwell countdown, then Roboflow RF-DETR + SAM 3
    helmet/PPE check (local CV fallback).
  * Head/PPE compliance rule and annotated snapshot generation.
* **SW Member 2 (Backend, Dashboard & Mobile App Lead)**:
  * FastAPI server with Eclipse Mosquitto MQTT broker and WebSocket endpoints.
  * SQLite database models for telemetry, incidents, and worker logs.
  * Streamlit Web Operator Control Room (`dashboard/app.py`) and the three.js digital
    twin (`static/twin.html`).
  * React Native Expo mobile app for floor managers (five tabs, on the `armor-app`
    branch), shipped as a web build for LAN testers.
  * Telegram bot integration for instant alert dispatching.

---

### 2. 24-Hour Sprint Milestone Roadmap

| Sprint & Hours | Hardware Member 1 | Hardware Member 2 | Software Member 1 | Software Member 2 |
| :--- | :--- | :--- | :--- | :--- |
| **Sprint 1 (Hours 0–6)**<br>*Setup & Baselines* | Wire RS-555 motor, L298N, ADXL345, INA219, DS18B20 to ESP32. Verify raw sensor readings. | Program ESP32 wearable badge to broadcast ESP-NOW packets with MAC & Worker ID. | Setup OpenCV webcam capture. Test pretrained YOLO segmentation model on test images. | Setup FastAPI backend, MQTT broker, and SQLite DB schema. Build basic Streamlit layout. |
| **Sprint 2 (Hours 6–12)**<br>*Inter-Module MVD* | Stream sensor telemetry to MQTT topic `armor/machine01/telemetry`. Wire L298N Enable pin. | Calibrate RSSI thresholding with EMA filter on machine node to trigger at ~1.5 meters. | Implement live webcam loop with helmet polygon mask rendering (Green=Pass, Red=Fail). | Connect Streamlit to MQTT streams. Create FastAPI route for proximity breach events. |
| **Sprint 3 (Hours 12–18)**<br>*Active Interlock & App* | Test emergency hardware lockout: pulling L298N Enable LOW upon MQTT command. | Integrate localized buzzer alert on wearable badge during zone breaches. | Connect Vision AI script to FastAPI breach event endpoint; trigger inference on ping. | Build React Native Expo app (Live Status, Interlock Override, Push Alerts, Incident Log). |
| **Sprint 4 (Hours 18–24)**<br>*Polish & Pitch Prep* | Fine-tune FreeRTOS task priorities so telemetry stays live during motor lockout. | Calibrate venue RF noise threshold; set up ultrasonic fallback sensor if needed. | Optimize frame rate (infer on every 3rd frame if CPU bound). Polish snapshot mask rendering. | Connect Telegram Bot alert API. Conduct end-to-end rehearsal and prep 2-min demo script. |

---

### 3. Engineering Landmines & Fallback Strategies

1. **Landmine A: RF Interference & RSSI Noise in Crowded Venue**
   * *Risk*: Wi-Fi/BLE RSSI fluctuates due to crowds, causing false proximity triggers or missed breaches.
   * *Fallback*: Use an **Exponential Moving Average (EMA)** filter on the last 5 RSSI samples ($S_t = lpha Y_t + (1-lpha)S_{t-1}$). If RSSI remains erratic during calibration, switch immediately to a hardware **Ultrasonic (HC-SR04)** or **PIR sensor** on the machine frame as the zone trigger.
2. **Landmine B: Streamlit Video Latency & UI Freezes**
   * *Risk*: Streamlit reruns scripts top-to-bottom; running OpenCV/YOLO inside Streamlit causes high latency and UI freezes.
   * *Fallback*: Keep YOLO inference in a background Python thread inside FastAPI. Serve processed frames via a FastAPI `StreamingResponse` (MJPEG stream) and embed it into Streamlit via a clean `<iframe>`.
3. **Landmine C: ESP32 Blocking Network Calls During Faults**
   * *Risk*: Calling blocking `WiFiClient` or MQTT publish loops delays hardware motor cutoff.
   * *Fallback*: Use **FreeRTOS dual-core tasks**:
     * **Core 0**: High-priority sensor sampling and hardware interlock GPIO actuation.
     * **Core 1**: MQTT/WiFi network communication.
4. **Landmine D: Mobile Notification Delays**
   * *Risk*: Push notification services may introduce 2–5 second delays during hackathon network congestion.
   * *Fallback*: Connect the React Native Expo app directly to the FastAPI WebSocket server so live in-app alert modals fire instantaneously alongside mobile push notifications.

---

### 4. 2-Minute Judge Presentation Script & Live Playbook

> The wording below is the original pitch. For the as-built demo beats (twin states,
> app tabs, anomaly gate), use `docs/ARMOR Merged Build Spec.md` §9 instead.

* **[0:00 - 0:30] The Core Pitch & Machine Health**:
  * *Presenter*: "Judges, Industry 4.0 dashboards only show you graphs while accidents happen. Meets ARMOR—an active, closed-loop cyber-physical safety cell. On the table, our RS-555 motor is running normally, streaming vibration, current, and temperature data to our Streamlit dashboard and React Native manager app."
* **[0:30 - 0:55] Proximity Detection**:
  * *Presenter*: "Watch what happens when a worker wearing our ESP32 smart badge approaches the machine. As soon as he steps within the 1.5-meter danger zone, the badge's ESP-NOW signal triggers a proximity breach."
* **[0:55 - 1:25] Event-Driven AI Inspection & Violation**:
  * *Presenter*: "The breach instantly wakes up our vision engine. OpenCV runs YOLO instance segmentation. Notice the worker is not wearing a helmet—the AI draws a red violation mask over his head region."
* **[1:25 - 1:45] Physical Interlock Actuation**:
  * *Presenter*: "Instantly—without human intervention—the backend sends an emergency lockout command. The machine node pulls the L298N driver's Enable pin LOW, and the motor halts with an audible stop! Simultaneously, a push notification with the violation snapshot lands on our React Native mobile app and Telegram channel."
* **[1:45 - 2:00] Safety Reset & Recovery**:
  * *Presenter*: "The worker puts on his helmet, passes inspection, the manager taps 'Reset Interlock' on the mobile app, and normal operations resume. ARMOR turns passive monitoring into active human protection."

---
