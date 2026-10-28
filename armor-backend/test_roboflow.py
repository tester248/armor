"""
ARMOR - Roboflow Workflow Smoke Test
------------------------------------
Runs the configured Roboflow helmet workflow on a single image and prints the
raw response so you can calibrate the helmet_status parsing in backend/vision.py.

Usage:
    # on a saved image:
    python test_roboflow.py path/to/photo.jpg

    # capture one frame from the webcam:
    python test_roboflow.py --webcam

Requires ROBOFLOW_API_KEY in .env (or environment).
"""
import argparse
import json
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from backend.vision import (
    ROBOFLOW_API_KEY,
    ROBOFLOW_WORKSPACE,
    ROBOFLOW_WORKFLOW_ID,
    ROBOFLOW_API_URL,
    _try_load_roboflow,
    _roboflow_client,
)

import cv2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", help="Path to an image file")
    parser.add_argument("--webcam", action="store_true", help="Capture one frame from webcam")
    args = parser.parse_args()

    if not ROBOFLOW_API_KEY:
        print("ERROR: ROBOFLOW_API_KEY is not set. Put it in armor-backend/.env")
        sys.exit(1)

    if args.webcam:
        cap = cv2.VideoCapture(0)
        time.sleep(1.0)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            print("ERROR: could not read from webcam")
            sys.exit(1)
        tmp = os.path.join(os.path.dirname(__file__), "data", "snapshots", "_roboflow_test.jpg")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        cv2.imwrite(tmp, frame)
        image_path = tmp
    else:
        if not args.image:
            print("ERROR: provide an image path or --webcam")
            sys.exit(1)
        image_path = args.image

    print(f"Workspace : {ROBOFLOW_WORKSPACE}")
    print(f"Workflow  : {ROBOFLOW_WORKFLOW_ID}")
    print(f"Image     : {image_path}")
    print("-" * 60)

    if not _try_load_roboflow():
        print("ERROR: could not configure Roboflow client")
        sys.exit(1)

    # reach the client via the module global
    import backend.vision as V

    with V._roboflow_lock:
        client = V._roboflow_client

    result = client.run_workflow(
        workspace_name=ROBOFLOW_WORKSPACE,
        workflow_id=ROBOFLOW_WORKFLOW_ID,
        images={"image": image_path},
        use_cache=True,
    )

    print("RAW RESULT:")
    print(json.dumps(result, indent=2, default=str)[:8000])
    print("-" * 60)

    entry = result[0] if isinstance(result, (list, tuple)) and result else result
    if isinstance(entry, dict):
        print("helmet_status:", repr(entry.get("helmet_status")))
        print("top-level keys:", list(entry.keys()))


if __name__ == "__main__":
    main()
