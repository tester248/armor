"""
ARMOR – Proximity Breach Simulator
===================================
Simulates an authorized worker entering the 1.5m danger zone.
Triggers edge AI vision inspection and closed-loop lockout in the backend.
"""
import sys
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BREACH_URL = "http://localhost:8000/api/v1/breach"


def trigger_breach(worker_id: str = "WORKER_EMP_402", distance_m: float = 1.2):
    print("=" * 60)
    print(" 🚨 SIMULATING PROXIMITY PERIMETER BREACH (<1.5M)")
    print("=" * 60)

    payload = {
        "device_id": "machino_node_01",
        "worker_id": worker_id,
        "badge_mac": "24:6F:28:AB:C1:02",
        "distance_est_m": distance_m,
        "rssi_smoothed": -60.5,
    }

    try:
        resp = requests.post(BREACH_URL, json=payload, timeout=3.0)
        if resp.status_code == 202:
            print(f"✅ Breach event sent for {worker_id} (Distance: {distance_m}m).")
            print("Vision inspection activated! Check your Streamlit dashboard for the alert.")
        else:
            print(f"Server response ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"Failed to connect to backend: {e}")


if __name__ == "__main__":
    worker = sys.argv[1] if len(sys.argv) > 1 else "WORKER_EMP_402"
    trigger_breach(worker_id=worker)
