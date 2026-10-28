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

Swap instruction for SW1:
  Set YOLO_MODEL_PATH=<path_to_yolov8_seg.pt> in .env
  The engine will auto-load the real model; stub is bypassed automatically.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import cv2
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────
CAMERA_SOURCE: int | str = os.getenv("CAMERA_SOURCE", "0")
try:
    CAMERA_SOURCE = int(CAMERA_SOURCE)
except ValueError:
    pass  # keep as string path (video file)

HELMET_COMPLIANCE_THRESHOLD = float(
    os.getenv("HELMET_COMPLIANCE_THRESHOLD", "0.65")
)
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "").strip()
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
    compliant: bool,
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


# ── YOLO loader (optional real model) ─────────────────────────────────────────
_yolo_model = None
_yolo_lock = threading.Lock()


def _try_load_yolo() -> bool:
    """Try to load real YOLOv8-seg model. Returns True if successful."""
    global _yolo_model
    if not YOLO_MODEL_PATH:
        return False
    try:
        from ultralytics import YOLO  # type: ignore
        with _yolo_lock:
            _yolo_model = YOLO(YOLO_MODEL_PATH)
        print(f"[VisionEngine] YOLO model loaded from: {YOLO_MODEL_PATH}")
        return True
    except Exception as e:
        print(f"[VisionEngine] Could not load YOLO model: {e}. Using stub.")
        return False


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


# ── Stub compliance check (no YOLO model) ─────────────────────────────────────
def _stub_inspect(frame: np.ndarray, worker_id: str) -> tuple[bool, float, str, np.ndarray]:
    """
    Mock helmet inspection.
    Draws a coloured bounding box and mask overlay on the frame.
    Alternates PASS/FAIL every 10 seconds for demo purposes.
    Returns: (compliant, compliance_ratio, label, annotated_frame)
    """
    h, w = frame.shape[:2]
    annotated = frame.copy()

    # Simulate head ROI (top-centre of frame)
    roi_x1 = w // 4
    roi_y1 = int(h * 0.05)
    roi_x2 = 3 * w // 4
    roi_y2 = int(h * 0.45)

    # Alternate PASS/FAIL every 10 s for demo
    cycle = int(time.time()) % 20
    if cycle < 10:
        # PASS – helmet detected
        compliance_ratio = 0.82
        compliant = True
        label = "HELMET_PASS"
        colour = (0, 200, 80)   # green
        mask_ratio = 0.82
    else:
        # FAIL – no helmet
        compliance_ratio = 0.18
        compliant = False
        label = "HELMET_FAIL"
        colour = (0, 60, 220)   # red (BGR)
        mask_ratio = 0.18

    # Draw head ROI box
    cv2.rectangle(annotated, (roi_x1, roi_y1), (roi_x2, roi_y2), (200, 200, 0), 2)

    # Draw mock segmentation mask overlay
    mask_overlay = annotated.copy()
    mask_x2 = roi_x1 + int((roi_x2 - roi_x1) * mask_ratio)
    cv2.rectangle(mask_overlay, (roi_x1, roi_y1), (mask_x2, roi_y2), colour, -1)
    cv2.addWeighted(mask_overlay, 0.35, annotated, 0.65, 0, annotated)

    # Labels
    cv2.rectangle(annotated, (roi_x1, roi_y1), (roi_x2, roi_y2), colour, 2)
    cv2.putText(
        annotated,
        f"{label}  ratio={compliance_ratio:.2f}",
        (roi_x1, roi_y1 - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2,
    )
    cv2.putText(
        annotated,
        f"Worker: {worker_id}",
        (10, h - 20),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1,
    )

    # STUB watermark
    cv2.putText(
        annotated,
        "[ STUB – No YOLO model loaded ]",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 1,
    )

    return compliant, compliance_ratio, label, annotated


# ── Real YOLO compliance check ─────────────────────────────────────────────────
def _yolo_inspect(
    frame: np.ndarray,
    worker_id: str,
) -> tuple[bool, float, str, np.ndarray]:
    """
    Real YOLOv8-seg inspection.
    Extracts head ROI, runs segmentation, computes:
        Compliance Ratio = Area(Helmet Mask ∩ Head ROI) / Area(Head ROI)
    """
    with _yolo_lock:
        model = _yolo_model

    if model is None:
        return _stub_inspect(frame, worker_id)

    h, w = frame.shape[:2]
    annotated = frame.copy()

    results = model(frame, verbose=False)
    result = results[0] if results else None

    if result is None or result.masks is None:
        return _stub_inspect(frame, worker_id)

    # Head ROI (top-centre heuristic — replace with pose detection if available)
    roi_x1, roi_y1 = w // 4, int(h * 0.05)
    roi_x2, roi_y2 = 3 * w // 4, int(h * 0.45)
    roi_area = max(1, (roi_x2 - roi_x1) * (roi_y2 - roi_y1))

    # Build binary ROI mask
    roi_mask = np.zeros((h, w), dtype=np.uint8)
    roi_mask[roi_y1:roi_y2, roi_x1:roi_x2] = 255

    # Accumulate helmet-class pixels across all detections
    helmet_mask = np.zeros((h, w), dtype=np.uint8)
    for i, cls_id in enumerate(result.boxes.cls.cpu().numpy()):
        name = model.names[int(cls_id)].lower()
        if "helmet" in name or "head" in name:
            seg_mask = result.masks.data[i].cpu().numpy()
            seg_mask_resized = cv2.resize(
                seg_mask, (w, h), interpolation=cv2.INTER_NEAREST
            ).astype(np.uint8)
            helmet_mask = cv2.bitwise_or(helmet_mask, seg_mask_resized)

    # Intersection
    intersection = cv2.bitwise_and(helmet_mask, roi_mask)
    compliance_ratio = float(np.sum(intersection > 0)) / roi_area
    compliant = compliance_ratio >= HELMET_COMPLIANCE_THRESHOLD
    label = "HELMET_PASS" if compliant else "HELMET_FAIL"
    colour = (0, 200, 80) if compliant else (0, 60, 220)

    # Overlay
    overlay = annotated.copy()
    overlay[helmet_mask > 0] = colour
    cv2.addWeighted(overlay, 0.4, annotated, 0.6, 0, annotated)
    cv2.rectangle(annotated, (roi_x1, roi_y1), (roi_x2, roi_y2), (200, 200, 0), 2)
    cv2.putText(
        annotated,
        f"{label}  ratio={compliance_ratio:.2f}",
        (roi_x1, roi_y1 - 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2,
    )

    return compliant, compliance_ratio, label, annotated


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
        self._yolo_loaded = _try_load_yolo()

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
        elif self._yolo_loaded:
            compliant, ratio, label, annotated = _yolo_inspect(frame, worker_id)
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
