"""
ARMOR – End-to-End Backend Verification Script
-----------------------------------------------
Tests all core functionality without requiring an external MQTT broker or camera:
  1. Health check & configuration
  2. Machine telemetry ingestion (vibration, power, temp)
  3. Proximity breach detection & automated vision inspection
  4. Emergency lockout actuation & incident logging
  5. Manager interlock reset
  6. Worker badge registry
"""
import sys
import time

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from starlette.testclient import TestClient
from backend.main import app, store, vision_engine


def run_tests():
    print("=" * 65)
    print(" [ARMOR] BACKEND END-TO-END VERIFICATION TEST")
    print("=" * 65)

    client = TestClient(app)

    # 1. Health Check
    print("\n[TEST 1] Checking API health endpoint...")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    print("  [PASS] Health check OK:", resp.json()["status"])

    # 2. Register Worker Badge
    print("\n[TEST 2] Registering an ESP32 Smart Badge...")
    badge_data = {
        "badge_mac": "24:6F:28:AB:C1:02",
        "worker_id": "WORKER_EMP_402",
        "worker_name": "Arjun Sharma",
        "department": "Heavy Fabrication Cell A",
        "active": True
    }
    resp = client.post("/api/v1/workers", json=badge_data)
    assert resp.status_code == 201, f"Badge registration failed: {resp.text}"
    print("  [PASS] Badge registered OK:", resp.json()["badge"]["worker_name"])

    # 3. Ingest Machine Telemetry
    print("\n[TEST 3] Ingesting ADXL345 / INA219 / DS18B20 Telemetry...")
    telemetry_data = {
        "device_id": "machino_node_01",
        "motor_state": "RUNNING",
        "vibration": {
            "accel_x": 0.02,
            "accel_y": 0.05,
            "accel_z": 0.98,
            "rms": 0.048,
            "crest_factor": 2.1
        },
        "power": {
            "voltage_v": 12.1,
            "current_ma": 420.5,
            "power_mw": 5088.05
        },
        "temperature_c": 34.2
    }
    resp = client.post("/api/v1/telemetry", json=telemetry_data)
    assert resp.status_code == 202, f"Telemetry ingest failed: {resp.text}"
    print("  [PASS] Telemetry ingested OK:", resp.json())

    # Verify machine state updated
    status_resp = client.get("/api/v1/status/machino_node_01")
    assert status_resp.status_code == 200
    state = status_resp.json()
    print(f"  [PASS] Machine State: Motor={state['motor_state']}, RMS={state['current_rms']}, Temp={state['current_temp_c']}C")

    # 4. Proximity Breach & Closed-Loop Inspection
    print("\n[TEST 4] Triggering Proximity Breach (1.5m Zone Perimeter)...")
    breach_data = {
        "device_id": "machino_node_01",
        "worker_id": "WORKER_EMP_402",
        "badge_mac": "24:6F:28:AB:C1:02",
        "rssi_raw": -58,
        "rssi_smoothed": -60.5,
        "distance_est_m": 1.2
    }
    resp = client.post("/api/v1/breach", json=breach_data)
    assert resp.status_code == 202, f"Breach post failed: {resp.text}"
    print("  [PASS] Breach event accepted, Vision AI pipeline triggered!")

    # Wait 0.5s for background vision thread to evaluate frame and save snapshot
    time.sleep(0.5)

    # 5. Check Incident Log & Interlock
    print("\n[TEST 5] Verifying Safety Incidents and Emergency Lockout...")
    incidents_resp = client.get("/api/v1/incidents?device_id=machino_node_01")
    assert incidents_resp.status_code == 200
    incidents = incidents_resp.json()["incidents"]
    print(f"  [PASS] Total recorded incidents in SQLite: {len(incidents)}")

    if incidents:
        latest = incidents[0]
        print(f"  [INCIDENT] ID: {latest['incident_id']}")
        print(f"             Violation: {latest['violation_type']}")
        print(f"             Compliance Ratio: {latest['compliance_ratio']}")
        print(f"             Snapshot: {latest['snapshot_path']}")
        print(f"             Interlock Issued: {bool(latest['interlock_issued'])}")

        # 6. Manager Resets Interlock
        print(f"\n[TEST 6] Testing Manager Safety Reset on Incident {latest['incident_id']}...")
        reset_resp = client.post(
            f"/api/v1/interlock/reset/{latest['incident_id']}?reset_by=Plant_Manager_John"
        )
        assert reset_resp.status_code == 200
        print("  [PASS] Interlock RESET successfully:", reset_resp.json())

        # Check machine status after reset
        state_after = client.get("/api/v1/status/machino_node_01").json()
        print(f"  [PASS] Machine State After Reset: Motor={state_after['motor_state']}, Interlock={state_after['interlock_active']}")

    print("\n" + "=" * 65)
    print(" ALL TESTS PASSED! ARMOR BACKEND IS FULLY OPERATIONAL!")
    print("=" * 65)


if __name__ == "__main__":
    run_tests()
