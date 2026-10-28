"""
ARMOR – ESP32 Machine Telemetry Simulator
==========================================
Simulates the Machine Node ESP32 streaming ADXL345, INA219, and DS18B20 data.
Sends realistic fluctuating time-series to the FastAPI backend every second.
"""
import math
import random
import sys
import time
from datetime import datetime, timezone
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

API_URL = "http://localhost:8000/api/v1/telemetry"
DEVICE_ID = "machino_node_01"


def run_simulator():
    print("=" * 60)
    print(" 📡 ARMOR ESP32 TELEMETRY SIMULATOR RUNNING")
    print(" Streaming to:", API_URL)
    print(" Press Ctrl+C to stop.")
    print("=" * 60)

    tick = 0
    motor_state = "RUNNING"

    while True:
        try:
            tick += 1

            # Baseline sine oscillation + random noise
            sine = math.sin(tick * 0.1)
            rms = max(0.02, 0.045 + 0.015 * sine + random.gauss(0, 0.005))
            crest_factor = round(2.0 + random.uniform(-0.2, 0.3), 2)

            # INA219 nominal 12V supply, current around 420mA
            voltage_v = round(12.1 + random.uniform(-0.1, 0.1), 2)
            current_ma = round(420.0 + 35.0 * sine + random.uniform(-10.0, 10.0), 1)
            power_mw = round(voltage_v * current_ma, 2)

            # DS18B20 temperature gradual warming around 34-36°C
            temperature_c = round(34.0 + 1.5 * (1 - math.exp(-tick / 40.0)) + random.uniform(-0.2, 0.2), 2)

            payload = {
                "device_id": DEVICE_ID,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "motor_state": motor_state,
                "vibration": {
                    "accel_x": round(random.gauss(0, 0.02), 3),
                    "accel_y": round(random.gauss(0, 0.03), 3),
                    "accel_z": round(0.98 + random.gauss(0, 0.02), 3),
                    "rms": round(rms, 4),
                    "crest_factor": crest_factor,
                },
                "power": {
                    "voltage_v": voltage_v,
                    "current_ma": current_ma,
                    "power_mw": power_mw,
                },
                "temperature_c": temperature_c,
            }

            resp = requests.post(API_URL, json=payload, timeout=2.0)
            if resp.status_code == 202:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Telemetry sent: RMS={rms:.3f}g, Current={current_ma:.1f}mA, Temp={temperature_c:.1f}°C")
            else:
                print(f"[!] Server returned status {resp.status_code}")

            time.sleep(1.0)

        except requests.exceptions.ConnectionError:
            print("[!] Cannot connect to FastAPI server (http://localhost:8000). Retrying in 2s...")
            time.sleep(2.0)
        except KeyboardInterrupt:
            print("\nSimulator stopped by user.")
            break


if __name__ == "__main__":
    run_simulator()
