import os
import sys
import time

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Handle running from d:\Armor or d:\Armor\armor-backend
backend_dir = os.path.join(os.path.dirname(__file__), "armor-backend")
if os.path.exists(backend_dir):
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
else:
    sys.path.insert(0, os.path.dirname(__file__))

from backend.vision_stub import vision_engine


def test_vision():
    print("=" * 60)
    print(" [ARMOR] TESTING VISION ENGINE STUB")
    print("=" * 60)

    # 1. Start engine
    print("\n[STEP 1] Starting VisionEngine capture loop...")
    vision_engine.start()
    time.sleep(1.0)  # Allow webcam or synthetic generator to warm up

    # 2. Run mock inspection
    print("[STEP 2] Running safety compliance inspection for 'WORKER_EMP_402'...")
    result = vision_engine.inspect(worker_id="WORKER_EMP_402", device_id="machino_node_01")

    print("\n--- Inspection Result ---")
    print(f"  Worker ID         : {result['worker_id']}")
    print(f"  Device ID         : {result['device_id']}")
    print(f"  Compliant?        : {result['compliant']}")
    print(f"  Compliance Ratio  : {result['compliance_ratio']} (Threshold >= {result['threshold_used']})")
    print(f"  Label             : {result['label']}")
    print(f"  Snapshot Saved To : {result['snapshot_path']}")

    if result.get("snapshot_path") and os.path.exists(result["snapshot_path"]):
        size = os.path.getsize(result["snapshot_path"])
        print(f"  Snapshot Size     : {size:,} bytes (verified on disk!)")

    # 3. Test frame stream generator (MJPEG)
    print("\n[STEP 3] Testing MJPEG frame generator for Streamlit / FastAPI...")
    stream = vision_engine.generate_frames()
    first_chunk = next(stream)
    print(f"  MJPEG Chunk Size  : {len(first_chunk):,} bytes (ready for /video/stream endpoint)")

    # 4. Cleanup
    vision_engine.stop()
    print("\n" + "=" * 60)
    print(" [SUCCESS] VISION ENGINE STUB TEST PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    test_vision()
