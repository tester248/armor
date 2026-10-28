"""
ARMOR – Vision Engine (Stub / Swap-Ready)
-----------------------------------------
Per ARMOR spec (ARMOR_System_Architecture_and_Implementation_Plan.md):

  • OpenCV webcam frame ingestion pipeline
  • YOLO instance segmentation model loader (motorcycle helmet dataset)
  • Head ROI extraction + polygon mask compliance calculation
        Compliance Ratio = Area(Helmet Mask ∩ Head ROI) / Area(Head ROI)
        PASS if Compliance Ratio >= 0.65
  • JPEG snapshot with colour-coded segmentation mask overlays
  • Runs in a background thread inside FastAPI (per landmine-B fix)
  • Frames served via generate_frames() → FastAPI StreamingResponse (MJPEG)
  • Streamlit embeds the stream via <iframe>

Configuration:
  Set ROBOFLOW_API_KEY (and optionally ROBOFLOW_WORKSPACE /
  ROBOFLOW_WORKFLOW_ID) in .env. The engine auto-loads the workflow;
  otherwise it falls back to the built-in stub.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import cv2
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────
CAMERA_SOURCE: int | str = os.getenv("CAMERA_SOURCE", "0")
try:
    CAMERA_SOURCE = int(CAMERA_SOURCE)
except ValueError:
    pass  # keep as string path (video file)

# Optional capture backend override: any | dshow | msmf (Windows).
CAMERA_BACKEND = os.getenv("CAMERA_BACKEND", "any").strip().lower()

HELMET_COMPLIANCE_THRESHOLD = float(
    os.getenv("HELMET_COMPLIANCE_THRESHOLD", "0.65")
)
SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", "data/snapshots"))
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

# --- Roboflow Workflow (RF-DETR + SAM 3 helmet check) ---
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "").strip()
ROBOFLOW_WORKSPACE = os.getenv("ROBOFLOW_WORKSPACE", "ashwin-mathur").strip()
ROBOFLOW_WORKFLOW_ID = os.getenv(
    "ROBOFLOW_WORKFLOW_ID", "helmet-check-hackathon-demo-1793134805931"
).strip()
ROBOFLOW_API_URL = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com").strip()


# ── Result dataclass (plain dict so no Pydantic import needed here) ────────────
def _make_result(
    worker_id: str,
    device_id: str,
    compliant: bool | None,
    compliance_ratio: float,
    label: str,
    snapshot_path: str | None = None,
    confidence: float | None = None,
) -> dict:
    return {
        "worker_id": worker_id,
        "device_id": device_id,
        "compliant": compliant,
        "compliance_ratio": round(compliance_ratio, 4),
        "threshold_used": HELMET_COMPLIANCE_THRESHOLD,
        "label": label,
        "confidence": confidence,
        "snapshot_path": snapshot_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# �� Roboflow Workflow (RF-DETR + SAM 3) ��������������������������������������
_roboflow_client = None
_roboflow_lock = threading.Lock()


def _try_load_roboflow() -> bool:
    """Try to build a Roboflow InferenceHTTPClient. Returns True if configured."""
    global _roboflow_client
    if not ROBOFLOW_API_KEY:
        return False
    try:
        from inference_sdk import InferenceHTTPClient, InferenceConfiguration  # type: ignore

        client = InferenceHTTPClient(
            api_url=ROBOFLOW_API_URL, api_key=ROBOFLOW_API_KEY
        ).configure(InferenceConfiguration(api_key_transport="header"))
        with _roboflow_lock:
            _roboflow_client = client
        print(f"[VisionEngine] Roboflow workflow configured: {ROBOFLOW_WORKSPACE}/{ROBOFLOW_WORKFLOW_ID}")
        return True
    except Exception as e:
        print(f"[VisionEngine] Could not configure Roboflow client: {e}.")
        return False


def _extract_image_from_result(result) -> bytes | None:
    """Best-effort extraction of image bytes from a workflow result value."""
    if result is None:
        return None
    if isinstance(result, dict):
        for key in ("value", "image", "data", "base64"):
            if key in result:
                img = _extract_image_from_result(result[key])
                if img is not None:
                    return img
        return None
    if isinstance(result, (bytes, bytearray)):
        return bytes(result)
    if isinstance(result, str):
        s = result.strip()
        if s.startswith("http://") or s.startswith("https://"):
            try:
                import requests

                r = requests.get(s, timeout=10)
                if r.status_code == 200:
                    return r.content
            except Exception:
                return None
            return None
        try:
            import base64

            if "," in s and s.split(",", 1)[0].startswith("data:"):
                s = s.split(",", 1)[1]
            return base64.b64decode(s, validate=False)
        except Exception:
            return None
    if isinstance(result, (list, tuple)) and result:
        return _extract_image_from_result(result[0])
    return None


def _roboflow_status_to_compliant(status) -> bool:
    """Interpret the workflow's helmet_status string."""
    if status is None:
        return False
    s = str(status).strip().lower()
    if not s:
        return False
    if any(tok in s for tok in ("missing", "no helmet", "no-helmet", "absent", "without", "not detected", "fail")):
        return False
    if any(tok in s for tok in ("helmet", "present", "pass", "compliant", "detected")):
        return True
    return False


def _roboflow_inspect(frame, worker_id):
    """Run the Roboflow helmet workflow on a frame."""
    import tempfile

    with _roboflow_lock:
        client = _roboflow_client

    if client is None:
        return _stub_inspect(frame, worker_id)

    h, w = frame.shape[:2]
    annotated = frame.copy()

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
    os.close(tmp_fd)
    cv2.imwrite(tmp_path, frame)

    try:
        result = client.run_workflow(
            workspace_name=ROBOFLOW_WORKSPACE,
            workflow_id=ROBOFLOW_WORKFLOW_ID,
            images={"image": tmp_path},
            use_cache=True,
        )
    except Exception as e:
        print(f"[VisionEngine] Roboflow workflow call failed: {e}")
        if "401" in str(e) or "Unauthorized" in str(e):
            print("[VisionEngine] Hint: use a Roboflow *secret* (private) API key, not a publishable one.")
        return _stub_inspect(frame, worker_id)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    entry = result[0] if isinstance(result, (list, tuple)) and result else result
    if not isinstance(entry, dict):
        print(f"[VisionEngine] Unexpected Roboflow result type: {type(entry)}")
        return _stub_inspect(frame, worker_id)

    print(f"[VisionEngine] Roboflow result keys: {list(entry.keys())}")

    helmet_status = entry.get("helmet_status")
    if helmet_status is None:
        for k in ("status", "helmet", "result"):
            if k in entry:
                helmet_status = entry[k]
                break

    print(f"[VisionEngine] Roboflow helmet_status: {helmet_status!r}")

    compliant = _roboflow_status_to_compliant(helmet_status)
    label = "HELMET_PASS" if compliant else "HELMET_FAIL"
    compliance_ratio = 0.9 if compliant else 0.1
    colour = (0, 200, 80) if compliant else (0, 60, 220)

    out_img_bytes = None
    for key in ("output_image", "bounding_box_image", "segmented_helmet_image"):
        if key in entry:
            out_img_bytes = _extract_image_from_result(entry[key])
            if out_img_bytes is not None:
                break

    if out_img_bytes is not None:
        try:
            arr = np.frombuffer(out_img_bytes, dtype=np.uint8)
            decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if decoded is not None:
                annotated = decoded
        except Exception as e:
            print(f"[VisionEngine] Could not decode Roboflow output image: {e}")

    if annotated is frame:
        annotated = frame.copy()
        cv2.putText(
            annotated, f"{label}  status={helmet_status}", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2,
        )
        cv2.putText(
            annotated, f"Worker: {worker_id}", (10, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1,
        )
        cv2.putText(
            annotated, "[ Roboflow RF-DETR + SAM 3 ]", (10, 55),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1,
        )

    return compliant, compliance_ratio, label, annotated


# ── No-vision fallback (no model configured) ──────────────────────────────────
def _stub_inspect(frame: np.ndarray, worker_id: str) -> tuple[None, float, str, np.ndarray]:
    """
    Helmet inspection is unavailable when no Roboflow credentials are configured.

    This deliberately does NOT fabricate a PASS/FAIL verdict. Returning
    compliant=None tells the caller to skip the interlock decision, because
    pretending a worker is safe (or unsafe) would be worse than reporting
    that vision is offline.

    Returns: (None, 0.0, "VISION_UNAVAILABLE", annotated_frame)
    """
    h, w = frame.shape[:2]
    annotated = frame.copy()

    colour = (0, 200, 255)  # amber (BGR)
    cv2.rectangle(annotated, (0, 0), (w - 1, h - 1), colour, 3)
    cv2.putText(
        annotated,
        "VISION UNAVAILABLE - helmet check skipped",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2,
    )
    cv2.putText(
        annotated,
        "Configure ROBOFLOW_API_KEY to enable compliance checks",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1,
    )
    cv2.putText(
        annotated,
        f"Worker: {worker_id}",
        (10, h - 20),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1,
    )

    return None, 0.0, "VISION_UNAVAILABLE", annotated


# ── Vision Engine ──────────────────────────────────────────────────────────────
class VisionEngine:
    """
    Background thread that continuously captures webcam frames.
    Runs in FastAPI's startup lifecycle.
    Provides:
      - generate_frames()  → MJPEG bytes for StreamingResponse
      - inspect(worker_id, device_id)  → compliance result dict + saves snapshot
    """

    def __init__(self) -> None:
        self._cap: cv2.VideoCapture | None = None
        self._latest_frame: np.ndarray | None = None
        self._frame_lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._roboflow_loaded = _try_load_roboflow()

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        """Call from FastAPI startup event."""
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print("[VisionEngine] Started. Camera:", CAMERA_SOURCE)

    def stop(self) -> None:
        """Call from FastAPI shutdown event."""
        self._running = False
        if self._cap:
            self._cap.release()

    # ── Capture loop (background thread) ──────────────────────────────────────
    def _capture_loop(self) -> None:
        backend_map = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "any": cv2.CAP_ANY}
        backend = backend_map.get(CAMERA_BACKEND, cv2.CAP_ANY)
        self._cap = cv2.VideoCapture(CAMERA_SOURCE, backend)
        if not self._cap.isOpened() and backend != cv2.CAP_ANY:
            # fall back to default backend
            self._cap = cv2.VideoCapture(CAMERA_SOURCE)
        if not self._cap.isOpened():
            print("[VisionEngine] WARNING: Camera not available. Generating blank frames.")

        while self._running:
            if self._cap and self._cap.isOpened():
                ret, frame = self._cap.read()
                if ret:
                    with self._frame_lock:
                        self._latest_frame = frame
                else:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop video file
            else:
                # Generate blank frame with text if no camera
                blank = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    blank, "No Camera – ARMOR Vision Engine",
                    (60, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 200, 255), 2,
                )
                with self._frame_lock:
                    self._latest_frame = blank
            time.sleep(0.033)  # ~30 fps

    def _get_frame(self) -> np.ndarray:
        with self._frame_lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(
            blank, "Initialising...",
            (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 200, 200), 2,
        )
        return blank

    # ── MJPEG stream ──────────────────────────────────────────────────────────
    def generate_frames(self) -> Generator[bytes, None, None]:
        """
        Yields MJPEG bytes for FastAPI StreamingResponse.
        Streamlit embeds via: st.markdown('<iframe src="..." />', unsafe_allow_html=True)
        """
        while True:
            frame = self._get_frame()
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg.tobytes()
                + b"\r\n"
            )
            time.sleep(0.05)  # ~20 fps for stream

    # ── Inspection (triggered by breach event) ────────────────────────────────
    def inspect(self, worker_id: str, device_id: str) -> dict:
        """
        Run helmet compliance check on the current frame.
        Returns result dict and saves snapshot JPEG.
        Called by the FastAPI breach handler.
        """
        frame = self._get_frame()

        if self._roboflow_loaded:
            compliant, ratio, label, annotated = _roboflow_inspect(frame, worker_id)
        else:
            compliant, ratio, label, annotated = _stub_inspect(frame, worker_id)

        # Save snapshot
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{device_id}_{worker_id}_{ts_str}.jpg"
        snapshot_path = str(SNAPSHOT_DIR / filename)
        cv2.imwrite(snapshot_path, annotated)

        return _make_result(
            worker_id=worker_id,
            device_id=device_id,
            compliant=compliant,
            compliance_ratio=ratio,
            label=label,
            snapshot_path=snapshot_path,
        )


# ── Singleton (imported by main.py) ───────────────────────────────────────────
vision_engine = VisionEngine()
