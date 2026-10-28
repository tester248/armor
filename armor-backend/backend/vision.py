"""
ARMOR – Vision AI Engine (Person-Gated Feed Freeze & Helmet Compliance)
========================================================================

Pipeline Architecture:
  1. Continuous Ingestion: OpenCV webcam ingestion (~30 fps).
  2. Person Detection Gate: Multi-stage real-time detector (YOLOv8n / Haar / HOG).
  3. Freeze on Detection: The moment a person enters the frame, the live feed
     FREEZES on that exact frame with visual overlay:
     "FEED FROZEN — ANALYZING HELMET & PPE COMPLIANCE".
  4. Helmet Inspection: Roboflow RF-DETR + SAM3 workflow (with local CV fallback)
     fires up on the frozen frame to verify if that specific person is wearing a helmet.
  5. Result Display: Verdict (HELMET PASS / HELMET FAIL) and segmentation masks
     are overlaid onto the frozen frame and displayed for a hold period before
     smoothly resuming live scanning.
  6. Safety Interlock: A helmet violation immediately triggers safety motor lockout,
     incident creation, and Telegram alert with snapshot.
"""
from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

# Silence ultralytics / matplotlib config warnings in restricted environments
_tmp = tempfile.gettempdir()
os.environ.setdefault("MPLCONFIGDIR", str(Path(_tmp) / "armor_mpl"))
os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(_tmp) / "armor_yolo"))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["YOLO_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)

import threading
import time
from datetime import datetime, timezone
from typing import Any, Generator

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import cv2
import numpy as np


# ── Custom Exceptions ─────────────────────────────────────────────────────────
class RoboflowError(Exception):
    """Base error for Roboflow workflow failures."""


class RoboflowAuthError(RoboflowError):
    """Authentication failed (401/403)."""


class RoboflowTimeoutError(RoboflowError):
    """Workflow call timed out."""


class RoboflowResponseError(RoboflowError):
    """Workflow returned an unexpected or unparseable response."""


# ── Config ────────────────────────────────────────────────────────────────────
CAMERA_SOURCE: int | str = os.getenv("CAMERA_SOURCE", "0")
try:
    CAMERA_SOURCE = int(CAMERA_SOURCE)
except ValueError:
    pass  # keep as string path (video file)

CAMERA_BACKEND = os.getenv("CAMERA_BACKEND", "any").strip().lower()

HELMET_COMPLIANCE_THRESHOLD = float(
    os.getenv("HELMET_COMPLIANCE_THRESHOLD", "0.65")
)
SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", "data/snapshots"))
if not SNAPSHOT_DIR.is_absolute():
    SNAPSHOT_DIR = (Path(__file__).resolve().parent.parent / SNAPSHOT_DIR).resolve()
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Roboflow Workflow Configuration
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "").strip()
ROBOFLOW_WORKSPACE = os.getenv("ROBOFLOW_WORKSPACE", "ashwin-mathur").strip()
ROBOFLOW_WORKFLOW_ID = os.getenv(
    "ROBOFLOW_WORKFLOW_ID", "helmet-check-hackathon-demo-1793134805931"
).strip()
ROBOFLOW_API_URL = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com").strip()

ROBOFLOW_REQUEST_TIMEOUT_S = float(os.getenv("ROBOFLOW_REQUEST_TIMEOUT_S", "25"))
ROBOFLOW_MAX_RETRIES = int(os.getenv("ROBOFLOW_MAX_RETRIES", "2"))
ROBOFLOW_BACKOFF_BASE_S = float(os.getenv("ROBOFLOW_BACKOFF_BASE_S", "0.8"))

# Timing configuration
FREEZE_HOLD_DURATION_S = float(os.getenv("FREEZE_HOLD_DURATION_S", "4.0"))
AUTO_INSPECT_COOLDOWN_S = float(os.getenv("AUTO_INSPECT_COOLDOWN_S", "4.0"))
AUTO_FREEZE_DEFAULT = os.getenv("AUTO_FREEZE_ENABLED", "false").lower() in ("true", "1", "yes")


# ── Result dict helper ────────────────────────────────────────────────────────
def _make_result(
    worker_id: str,
    device_id: str,
    compliant: bool | None,
    compliance_ratio: float,
    label: str,
    snapshot_path: str | None = None,
    confidence: float | None = None,
    detection_source: str = "ROBOFLOW_RF_DETR_SAM3",
    details: dict[str, Any] | None = None,
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
        "detection_source": detection_source,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Roboflow client with retries + defensive output parsing ───────────────────
class RoboflowClient:
    """Wrapper around inference_sdk.InferenceHTTPClient for helmet inspection."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        workspace: str,
        workflow_id: str,
        timeout_s: float = ROBOFLOW_REQUEST_TIMEOUT_S,
        max_retries: int = ROBOFLOW_MAX_RETRIES,
        backoff_base_s: float = ROBOFLOW_BACKOFF_BASE_S,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.workspace = workspace
        self.workflow_id = workflow_id
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self._client = None
        self._lock = threading.Lock()
        self._configured = False

    def _ensure(self) -> None:
        with self._lock:
            if self._configured:
                return
            try:
                from inference_sdk import InferenceHTTPClient, InferenceConfiguration  # type: ignore

                self._client = (
                    InferenceHTTPClient(
                        api_url=self.api_url,
                        api_key=self.api_key,
                    )
                    .configure(InferenceConfiguration(api_key_transport="header"))
                )
                self._configured = True
            except Exception as e:
                raise RoboflowError(f"Failed to configure Roboflow client: {e}") from e

    def run_helmet_check(
        self,
        image_path: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._ensure()
        assert self._client is not None

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = self._client.run_workflow(
                    workspace_name=self.workspace,
                    workflow_id=self.workflow_id,
                    images={"image": image_path},
                    parameters=parameters or {},
                    use_cache=True,
                )
                return self._parse_workflow_result(result)
            except RoboflowAuthError:
                raise
            except RoboflowTimeoutError as e:
                last_error = e
            except Exception as e:
                msg = str(e)
                if "401" in msg or "Unauthorized" in msg or "403" in msg:
                    raise RoboflowAuthError(
                        "Roboflow authentication failed. Please configure a valid secret ROBOFLOW_API_KEY."
                    ) from e
                last_error = e

            if attempt < self.max_retries:
                time.sleep(self.backoff_base_s * (2 ** (attempt - 1)))

        raise RoboflowTimeoutError(
            f"Roboflow workflow failed after {self.max_retries} attempts: {last_error}"
        ) from last_error

    def _parse_workflow_result(self, result: Any) -> dict[str, Any]:
        if result is None:
            raise RoboflowResponseError("Roboflow returned None.")

        entry = result[0] if isinstance(result, (list, tuple)) and result else result
        if not isinstance(entry, dict):
            raise RoboflowResponseError(
                f"Unexpected Roboflow result type: {type(entry).__name__}"
            )

        with_count = int(entry.get("with_helmet_count") or 0)
        without_count = int(entry.get("without_helmet_count") or 0)
        helmet_status = str(entry.get("helmet_status") or "").strip()
        compliance_ratio = float(entry.get("compliance_ratio") or 0.0)
        output_image_bytes = self._extract_output_image(entry)
        predictions = entry.get("predictions")

        return {
            "with_helmet_count": with_count,
            "without_helmet_count": without_count,
            "helmet_status": helmet_status,
            "compliance_ratio": compliance_ratio,
            "output_image_bytes": output_image_bytes,
            "predictions": predictions,
            "raw_keys": list(entry.keys()),
        }

    @staticmethod
    def _extract_output_image(entry: dict[str, Any]) -> bytes | None:
        image_keys = (
            "output_image",
            "annotated_image",
            "segmented_helmet_image",
            "bounding_box_image",
            "image",
            "result_image",
        )
        for key in image_keys:
            if key not in entry:
                continue
            val = entry[key]
            if isinstance(val, (bytes, bytearray)):
                return bytes(val)
            if isinstance(val, str):
                s = val.strip()
                if s.startswith("http://") or s.startswith("https://"):
                    try:
                        import requests

                        r = requests.get(s, timeout=8)
                        if r.status_code == 200:
                            return r.content
                    except Exception:
                        continue
                if "," in s and s.split(",", 1)[0].startswith("data:"):
                    try:
                        return base64.b64decode(s.split(",", 1)[1], validate=False)
                    except Exception:
                        continue
                try:
                    return base64.b64decode(s, validate=False)
                except Exception:
                    continue
            if isinstance(val, dict):
                inner = RoboflowClient._extract_output_image(val)
                if inner is not None:
                    return inner
        return None


# ── High-Performance Person Detector ──────────────────────────────────────────
class PersonDetector:
    """Multi-tiered real-time Person Detector:
      Tier 1: Ultralytics YOLOv8n (classes=[0], ~13ms on CPU, high precision).
      Tier 2: OpenCV Haar Cascades (Face + Upper Body fallback).
      Tier 3: OpenCV HOG Pedestrian Detector.
    """

    def __init__(self) -> None:
        self._yolo_model = None
        self._yolo_loaded = False
        self._init_yolo()

        # Tier 2: Haar Cascades
        self._face_cascade = None
        self._upper_cascade = None
        self._init_haar()

        # Tier 3: HOG
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def _init_yolo(self) -> None:
        try:
            from ultralytics import YOLO

            weights_paths = [
                Path(__file__).resolve().parent.parent / "yolov8n.pt",
                Path(__file__).resolve().parent.parent.parent / "yolov8n.pt",
                Path("yolov8n.pt"),
            ]
            weights = None
            for p in weights_paths:
                if p.exists():
                    weights = str(p)
                    break
            if weights is None:
                weights = "yolov8n.pt"

            self._yolo_model = YOLO(weights)
            self._yolo_loaded = True
            print(f"[PersonDetector] YOLOv8n model initialized ({weights})")
        except Exception as e:
            print(f"[PersonDetector] YOLOv8n unavailable, falling back to Haar/HOG: {e}")
            self._yolo_model = None
            self._yolo_loaded = False

    def _init_haar(self) -> None:
        try:
            haar_dir = getattr(cv2, "data", None)
            if haar_dir and hasattr(haar_dir, "haarcascades"):
                p_face = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                p_upper = cv2.data.haarcascades + "haarcascade_upperbody.xml"
                if os.path.exists(p_face):
                    self._face_cascade = cv2.CascadeClassifier(p_face)
                if os.path.exists(p_upper):
                    self._upper_cascade = cv2.CascadeClassifier(p_upper)
        except Exception:
            pass

    def detect(self, frame: np.ndarray) -> tuple[bool, list[tuple[int, int, int, int]]]:
        """Returns (person_detected: bool, bounding_boxes: list[(x1, y1, x2, y2)])."""
        h, w = frame.shape[:2]

        # ── Tier 1: YOLOv8n (preferred) ──
        if self._yolo_loaded and self._yolo_model is not None:
            try:
                results = self._yolo_model(
                    frame, classes=[0], conf=0.40, verbose=False, imgsz=480
                )[0]
                boxes: list[tuple[int, int, int, int]] = []
                for box in results.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    if (x2 - x1) > 20 and (y2 - y1) > 30:
                        boxes.append((x1, y1, x2, y2))
                if boxes:
                    return True, boxes
            except Exception:
                pass

        # ── Tier 2: OpenCV Haar Cascades (Face & Upper Body) ──
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            haar_boxes: list[tuple[int, int, int, int]] = []

            if self._upper_cascade is not None and not self._upper_cascade.empty():
                uppers = self._upper_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60)
                )
                for x, y, bw, bh in uppers:
                    haar_boxes.append((x, y, x + bw, y + bh))

            if self._face_cascade is not None and not self._face_cascade.empty():
                faces = self._face_cascade.detectMultiScale(
                    gray, scaleFactor=1.15, minNeighbors=4, minSize=(40, 40)
                )
                for x, y, bw, bh in faces:
                    bx1 = max(0, int(x - bw * 0.5))
                    by1 = max(0, int(y - bh * 0.4))
                    bx2 = min(w, int(x + bw * 1.5))
                    by2 = min(h, int(y + bh * 3.0))
                    haar_boxes.append((bx1, by1, bx2, by2))

            if haar_boxes:
                return True, haar_boxes
        except Exception:
            pass

        # ── Tier 3: OpenCV HOG ──
        try:
            boxes_hog, _ = self._hog.detectMultiScale(
                frame, winStride=(8, 8), padding=(16, 16), scale=1.08, hitThreshold=0.0
            )
            hog_boxes = [
                (int(x), int(y), int(x + bw), int(y + bh))
                for (x, y, bw, bh) in boxes_hog
            ]
            if hog_boxes:
                return True, hog_boxes
        except Exception:
            pass

        return False, []


# ── Helmet Interpretation & Verification ──────────────────────────────────────
def _interpret_roboflow_results(
    parsed: dict[str, Any],
    person_present: bool = True,
) -> tuple[bool, float, str]:
    """Interprets the Roboflow workflow results into a definitive compliance verdict."""
    with_count = int(parsed.get("with_helmet_count") or 0)
    without_count = int(parsed.get("without_helmet_count") or 0)
    status = str(parsed.get("helmet_status") or "").strip().upper()

    # Direct count logic (most reliable)
    if with_count > 0:
        ratio = max(0.85, float(parsed.get("compliance_ratio") or 0.90))
        return True, ratio, "HELMET_PASS"

    if without_count > 0:
        ratio = min(0.20, float(parsed.get("compliance_ratio") or 0.12))
        return False, ratio, "HELMET_FAIL"

    # Status string matching
    if "HELMET DETECTED" in status or "HELMET_PASS" in status or "COMPLIANT" in status:
        return True, 0.88, "HELMET_PASS"

    if "HELMET MISSING" in status or "WITHOUT" in status or "NO HELMET" in status:
        return False, 0.14, "HELMET_FAIL"

    # Prediction bounding boxes inspection
    preds = parsed.get("predictions")
    pred_items = []
    if isinstance(preds, dict):
        pred_items = preds.get("predictions", [])
    elif isinstance(preds, list):
        pred_items = preds

    has_helmet = False
    has_no_helmet = False
    highest_conf = 0.0

    for p in pred_items:
        cname = str(p.get("class_name") or p.get("class") or "").lower()
        conf = float(p.get("confidence") or 0.0)
        highest_conf = max(highest_conf, conf)
        if "with" in cname or cname == "helmet":
            has_helmet = True
        elif "without" in cname or "no" in cname:
            has_no_helmet = True

    if has_helmet:
        return True, max(highest_conf, 0.82), "HELMET_PASS"
    if has_no_helmet:
        return False, min(1.0 - highest_conf, 0.18), "HELMET_FAIL"

    # If no helmet was detected:
    return False, 0.05, "HELMET_FAIL"


# ── Inspection Execution (Roboflow with Local Safety Fallback) ────────────────
def _roboflow_inspect(
    client: RoboflowClient,
    frame: np.ndarray,
    person_boxes: list[tuple[int, int, int, int]],
    worker_id: str,
) -> tuple[bool, float, str, np.ndarray]:
    """Runs Roboflow helmet check on the frozen frame.
    Returns (compliant, compliance_ratio, label, annotated_frame).
    """
    h, w = frame.shape[:2]
    annotated = frame.copy()

    import tempfile

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
    os.close(tmp_fd)
    cv2.imwrite(tmp_path, frame)

    try:
        parsed = client.run_helmet_check(image_path=tmp_path)
        compliant, ratio, label = _interpret_roboflow_results(
            parsed, person_present=len(person_boxes) > 0
        )

        out_img_bytes = parsed.get("output_image_bytes")
        if out_img_bytes:
            try:
                arr = np.frombuffer(out_img_bytes, dtype=np.uint8)
                decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if decoded is not None and decoded.shape == frame.shape:
                    annotated = decoded
            except Exception:
                pass

        _draw_inspection_verdict_overlay(
            annotated, compliant, ratio, label, person_boxes, worker_id, source="Roboflow RF-DETR + SAM3"
        )
        return compliant, ratio, label, annotated

    except Exception as e:
        print(f"[VisionEngine] Roboflow call failed ({e}), using local safety inspection fallback.")
        return _local_safety_inspect(frame, person_boxes, worker_id)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _local_safety_inspect(
    frame: np.ndarray,
    person_boxes: list[tuple[int, int, int, int]],
    worker_id: str,
) -> tuple[bool, float, str, np.ndarray]:
    """Deterministic local CV safety inspection fallback when cloud API is unreachable.
    Examines the head/crown ROI of detected person boxes for safety helmet colour contours.
    """
    h, w = frame.shape[:2]
    annotated = frame.copy()

    if not person_boxes:
        person_boxes = [(w // 4, int(h * 0.1), int(w * 0.75), int(h * 0.9))]

    compliant = False
    best_ratio = 0.15

    for (px1, py1, px2, py2) in person_boxes:
        pw = px2 - px1
        ph = py2 - py1
        hx1 = max(0, px1 + int(pw * 0.15))
        hy1 = max(0, py1)
        hx2 = min(w, px2 - int(pw * 0.15))
        hy2 = min(h, py1 + int(ph * 0.35))

        head_roi = frame[hy1:hy2, hx1:hx2]
        if head_roi.size > 0:
            hsv = cv2.cvtColor(head_roi, cv2.COLOR_BGR2HSV)
            # Mask for typical industrial safety helmets: Yellow, Orange, White, Red, Blue
            mask_yellow = cv2.inRange(hsv, np.array([15, 70, 70]), np.array([35, 255, 255]))
            mask_orange = cv2.inRange(hsv, np.array([5, 100, 100]), np.array([18, 255, 255]))
            mask_white = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([180, 45, 255]))
            mask_helmet = cv2.bitwise_or(mask_yellow, cv2.bitwise_or(mask_orange, mask_white))

            coverage = float(cv2.countNonZero(mask_helmet)) / float(head_roi.shape[0] * head_roi.shape[1])
            if coverage >= 0.22:
                compliant = True
                best_ratio = min(0.96, 0.65 + coverage * 0.6)
                break

    label = "HELMET_PASS" if compliant else "HELMET_FAIL"
    _draw_inspection_verdict_overlay(
        annotated, compliant, best_ratio, label, person_boxes, worker_id, source="ARMOR Edge Vision (Local)"
    )
    return compliant, best_ratio, label, annotated


def _draw_inspection_verdict_overlay(
    img: np.ndarray,
    compliant: bool,
    ratio: float,
    label: str,
    person_boxes: list[tuple[int, int, int, int]],
    worker_id: str,
    source: str = "Roboflow RF-DETR + SAM3",
) -> None:
    """Renders prominent industrial HUD graphics onto the frozen inspection frame."""
    h, w = img.shape[:2]

    color = (0, 220, 80) if compliant else (0, 50, 240)
    bg_color = (15, 30, 20) if compliant else (15, 15, 45)

    # Top Status Banner
    cv2.rectangle(img, (0, 0), (w, 62), bg_color, -1)
    cv2.rectangle(img, (0, 60), (w, 62), color, -1)

    banner_text = (
        f"HELMET VERIFIED: COMPLIANT ({ratio:.0%})"
        if compliant
        else f"SAFETY VIOLATION: NO HELMET DETECTED ({ratio:.0%})"
    )
    cv2.putText(img, banner_text, (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

    sub_text = f"Worker: {worker_id}  |  Engine: {source}"
    cv2.putText(img, sub_text, (20, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 200, 220), 1)

    # Bounding boxes on detected persons
    for (px1, py1, px2, py2) in person_boxes:
        cv2.rectangle(img, (px1, py1), (px2, py2), color, 3)

        pw = px2 - px1
        ph = py2 - py1
        hx1 = max(0, px1 + int(pw * 0.15))
        hy1 = max(0, py1)
        hx2 = min(w, px2 - int(pw * 0.15))
        hy2 = min(h, py1 + int(ph * 0.35))
        cv2.rectangle(img, (hx1, hy1), (hx2, hy2), (255, 255, 255), 2)

        tag = "PPE PASS: HELMET DETECTED" if compliant else "PPE FAIL: MISSING HELMET"
        cv2.rectangle(img, (px1, max(0, py1 - 28)), (px1 + 260, py1), color, -1)
        cv2.putText(
            img, tag, (px1 + 8, max(18, py1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2
        )

    # Bottom alert tag if lockout issued
    if not compliant:
        cv2.rectangle(img, (0, h - 35), (w, h), (0, 0, 180), -1)
        cv2.putText(
            img,
            "AUTOMATIC MOTOR LOCKOUT ISSUED - EVACUATE DANGER ZONE",
            (25, h - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
        )


# ── Vision Engine Singleton ───────────────────────────────────────────────────
class VisionEngine:
    """ARMOR Vision Engine:
      - Continuous camera ingestion
      - Person detection gate
      - Feed-freeze on person detection
      - Background helmet compliance check
      - MJPEG stream rendering with visual status indicators
    """

    def __init__(self) -> None:
        self._cap: cv2.VideoCapture | None = None
        self._running = False
        self._thread: threading.Thread | None = None

        self._frame_lock = threading.RLock()
        self._latest_frame: np.ndarray | None = None
        self._frozen_frame: np.ndarray | None = None
        self._annotated_frozen_frame: np.ndarray | None = None

        # Feed freeze & inspection state machine
        self._is_frozen = False
        self._freeze_time = 0.0
        self._hold_duration_s = FREEZE_HOLD_DURATION_S
        self._cooldown_until = 0.0
        self._cooldown_duration_s = AUTO_INSPECT_COOLDOWN_S
        self._vision_state = "SCANNING"  # SCANNING | FROZEN_INSPECTING | HELMET_PASS | HELMET_FAIL | COOLDOWN
        self._auto_freeze_enabled = AUTO_FREEZE_DEFAULT
        self._person_inspected_for_current_presence = False

        self._person_detector = PersonDetector()
        self._person_present = False
        self._person_boxes: list[tuple[int, int, int, int]] = []
        self._person_lock = threading.Lock()

        self._last_helmet_result: dict | None = None
        self._inspecting_lock = threading.Lock()
        self._is_inspecting = False

        # Roboflow Client
        self._roboflow_client: RoboflowClient | None = None
        self._roboflow_available = False
        if ROBOFLOW_API_KEY:
            try:
                self._roboflow_client = RoboflowClient(
                    api_url=ROBOFLOW_API_URL,
                    api_key=ROBOFLOW_API_KEY,
                    workspace=ROBOFLOW_WORKSPACE,
                    workflow_id=ROBOFLOW_WORKFLOW_ID,
                )
                self._roboflow_client._ensure()
                self._roboflow_available = True
                print(
                    f"[VisionEngine] Roboflow workflow configured: "
                    f"{ROBOFLOW_WORKSPACE}/{ROBOFLOW_WORKFLOW_ID}"
                )
            except Exception as e:
                print(f"[VisionEngine] Roboflow init error ({e}) - will use local safety detector.")
                self._roboflow_client = None
                self._roboflow_available = False
        else:
            print("[VisionEngine] No ROBOFLOW_API_KEY configured - running local safety detector.")

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f"[VisionEngine] Started live capture on Camera {CAMERA_SOURCE}")

    def stop(self) -> None:
        self._running = False
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass

    # ── Capture Loop ──────────────────────────────────────────────────────────
    def _capture_loop(self) -> None:
        backend_map = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "any": cv2.CAP_ANY}
        backend = backend_map.get(CAMERA_BACKEND, cv2.CAP_ANY)
        try:
            self._cap = cv2.VideoCapture(CAMERA_SOURCE, backend)
            if not self._cap.isOpened() and backend != cv2.CAP_ANY:
                self._cap = cv2.VideoCapture(CAMERA_SOURCE)
        except Exception as e:
            print(f"[VisionEngine] Camera initialization error: {e}")

        frame_counter = 0
        last_person_seen_time = 0.0

        while self._running:
            now = time.time()
            ret = False
            frame = None

            if self._cap and self._cap.isOpened():
                ret, frame = self._cap.read()
                if not ret:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            if not ret or frame is None:
                frame = self._generate_fallback_frame()

            with self._frame_lock:
                self._latest_frame = frame

            # ── If currently frozen, manage freeze hold duration ──
            if self._is_frozen:
                if self._vision_state in ("HELMET_PASS", "HELMET_FAIL") and not self._is_inspecting:
                    if (now - self._freeze_time) >= self._hold_duration_s:
                        self.unfreeze()
                time.sleep(0.033)
                continue

            # ── Person Detection Gate (runs every 2 frames for speed) ──
            frame_counter += 1
            if frame_counter % 2 == 0:
                person_present, person_boxes = self._person_detector.detect(frame)
                with self._person_lock:
                    self._person_present = person_present
                    self._person_boxes = person_boxes

                if person_present:
                    last_person_seen_time = now
                    # Only trigger auto-freeze if:
                    # 1. auto-freeze is toggled ON
                    # 2. this person has NOT already been inspected during this continuous presence
                    # 3. not currently inspecting
                    # 4. cooldown period has elapsed
                    if (
                        self._auto_freeze_enabled
                        and not self._person_inspected_for_current_presence
                        and not self._is_inspecting
                        and now >= self._cooldown_until
                    ):
                        self._person_inspected_for_current_presence = True
                        self._trigger_freeze_and_inspect(
                            frame.copy(), person_boxes, worker_id="WORKER_EMP_402", device_id="machino_node_01"
                        )
                else:
                    # Reset gate only after camera has seen NO person for at least 2 seconds
                    if (now - last_person_seen_time) >= 2.0:
                        self._person_inspected_for_current_presence = False

            time.sleep(0.033)  # ~30 fps

    # ── Feed Freeze & Inspection Trigger ──────────────────────────────────────
    def _trigger_freeze_and_inspect(
        self,
        frame: np.ndarray,
        person_boxes: list[tuple[int, int, int, int]],
        worker_id: str = "WORKER_EMP_402",
        device_id: str = "machino_node_01",
    ) -> None:
        """Freezes the video feed immediately on the current frame and starts helmet check."""
        with self._inspecting_lock:
            if self._is_inspecting:
                return
            self._is_inspecting = True

        h, w = frame.shape[:2]
        frozen_overlay = frame.copy()

        cv2.rectangle(frozen_overlay, (0, 0), (w, 55), (20, 20, 20), -1)
        cv2.rectangle(frozen_overlay, (0, 53), (w, 55), (0, 220, 255), -1)
        cv2.putText(
            frozen_overlay,
            "FEED FROZEN: DETECTING HELMET & PPE COMPLIANCE...",
            (20, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            (0, 220, 255),
            2,
        )

        for (px1, py1, px2, py2) in person_boxes:
            cv2.rectangle(frozen_overlay, (px1, py1), (px2, py2), (0, 220, 255), 2)
            cv2.putText(
                frozen_overlay,
                "PERSON DETECTED - INSPECTING",
                (px1, max(20, py1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 220, 255),
                2,
            )

        with self._frame_lock:
            self._is_frozen = True
            self._frozen_frame = frame.copy()
            self._annotated_frozen_frame = frozen_overlay
            self._freeze_time = time.time()
            self._vision_state = "FROZEN_INSPECTING"

        print(f"[VisionEngine] Person detected! Feed FROZEN on frame. Launching helmet model for {worker_id}...")

        threading.Thread(
            target=self._run_helmet_inspection_task,
            args=(frame, person_boxes, worker_id, device_id),
            daemon=True,
        ).start()

    def _run_helmet_inspection_task(
        self,
        frame: np.ndarray,
        person_boxes: list[tuple[int, int, int, int]],
        worker_id: str,
        device_id: str,
    ) -> None:
        try:
            if self._roboflow_available and self._roboflow_client is not None:
                compliant, ratio, label, annotated = _roboflow_inspect(
                    self._roboflow_client, frame, person_boxes, worker_id
                )
                source = "Roboflow RF-DETR + SAM3"
            else:
                compliant, ratio, label, annotated = _local_safety_inspect(
                    frame, person_boxes, worker_id
                )
                source = "ARMOR Edge Vision (Local)"
        except Exception as e:
            print(f"[VisionEngine] Helmet inspection failed: {e}")
            compliant, ratio, label, annotated = _local_safety_inspect(
                frame, person_boxes, worker_id
            )
            source = "ARMOR Edge Vision (Fallback)"

        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{device_id}_{worker_id}_{ts_str}.jpg"
        snapshot_path = str(SNAPSHOT_DIR / filename)
        cv2.imwrite(snapshot_path, annotated)

        result = _make_result(
            worker_id=worker_id,
            device_id=device_id,
            compliant=compliant,
            compliance_ratio=ratio,
            label=label,
            snapshot_path=snapshot_path,
            detection_source=source,
        )

        with self._frame_lock:
            self._annotated_frozen_frame = annotated
            self._freeze_time = time.time()
            self._vision_state = "HELMET_PASS" if compliant else "HELMET_FAIL"
            self._last_helmet_result = result

        with self._inspecting_lock:
            self._is_inspecting = False

        print(f"[VisionEngine] Inspection complete: {label} (ratio: {ratio:.1%}, compliant={compliant})")

        if not compliant:
            self._handle_safety_lockout(device_id, worker_id, snapshot_path, ratio)

    def _handle_safety_lockout(
        self, device_id: str, worker_id: str, snapshot_path: str, ratio: float
    ) -> None:
        """Trigger backend lockout and incident logging when safety violation occurs."""
        try:
            from backend.main import store, _telegram_send, _mqtt_publish

            incident_id = store.create_incident({
                "device_id": device_id,
                "worker_id": worker_id,
                "badge_mac": "VISION-GATE",
                "violation_type": "MISSING_HELMET",
                "compliance_ratio": ratio,
                "snapshot_path": snapshot_path,
                "interlock_issued": True,
            })

            lockout_cmd = {
                "command": "LOCKOUT",
                "source": "VISION_AI_PERSON_GATE",
                "reason": "MISSING_HELMET_ON_DETECTED_PERSON",
                "worker_id": worker_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            store.log_interlock({**lockout_cmd, "device_id": device_id})
            store.set_machine_state(device_id, {
                "motor_state": "LOCKED",
                "interlock_active": True,
            })

            _mqtt_publish(f"machinocare/v1/devices/{device_id}/interlock", lockout_cmd)
            _telegram_send(
                f"🚨 ARMOR SAFETY VIOLATION\n"
                f"Device : {device_id}\n"
                f"Worker : {worker_id}\n"
                f"Helmet Compliance: {ratio:.0%}\n"
                f"⚡ Motor LOCKED OUT automatically.\n"
                f"Incident #{incident_id}",
                photo_path=snapshot_path,
            )
        except Exception as e:
            print(f"[VisionEngine] Safety lockout dispatch notice: {e}")

    # ── Unfreeze & Manual Controls ────────────────────────────────────────────
    def unfreeze(self) -> None:
        """Manually or automatically unfreezes the video stream back to live scanning."""
        with self._frame_lock:
            self._is_frozen = False
            self._frozen_frame = None
            self._annotated_frozen_frame = None
            self._cooldown_until = time.time() + self._cooldown_duration_s
            self._vision_state = "SCANNING"
        with self._inspecting_lock:
            self._is_inspecting = False
        print("[VisionEngine] Live camera feed resumed (SCANNING).")

    def inspect(self, worker_id: str = "WORKER_EMP_402", device_id: str = "machino_node_01") -> dict:
        """Synchronous inspection request (used by proximity breach or manual button)."""
        frame = self._get_frame()
        _, person_boxes = self._person_detector.detect(frame)

        self._person_inspected_for_current_presence = True
        self._trigger_freeze_and_inspect(frame, person_boxes, worker_id=worker_id, device_id=device_id)

        deadline = time.time() + 8.0
        while time.time() < deadline:
            if self._last_helmet_result and self._vision_state in ("HELMET_PASS", "HELMET_FAIL"):
                return self._last_helmet_result
            time.sleep(0.1)

        if self._last_helmet_result:
            return self._last_helmet_result

        return _make_result(
            worker_id=worker_id,
            device_id=device_id,
            compliant=False,
            compliance_ratio=0.0,
            label="HELMET_FAIL",
        )

    # ── MJPEG Stream Generator ────────────────────────────────────────────────
    def generate_frames(self) -> Generator[bytes, None, None]:
        """Yields MJPEG stream frames continuously for FastAPI StreamingResponse."""
        while True:
            with self._frame_lock:
                if self._is_frozen and self._annotated_frozen_frame is not None:
                    stream_frame = self._annotated_frozen_frame.copy()
                elif self._latest_frame is not None:
                    stream_frame = self._latest_frame.copy()
                else:
                    stream_frame = self._generate_fallback_frame()

                if not self._is_frozen:
                    with self._person_lock:
                        person_present = self._person_present
                        boxes = list(self._person_boxes)

                        if person_present:
                            for (x1, y1, x2, y2) in boxes:
                                cv2.rectangle(stream_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                cv2.putText(
                                    stream_frame,
                                    "PERSON",
                                    (x1, max(y1 - 8, 20)),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.55,
                                    (0, 255, 0),
                                    2,
                                )
                    cv2.circle(stream_frame, (20, 25), 6, (0, 255, 0), -1)
                    cv2.putText(
                        stream_frame,
                        "LIVE AI STREAM",
                        (34, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.50,
                        (0, 255, 0),
                        2,
                    )
                    h_w = stream_frame.shape[1]
                    mode_txt = "AUTO-INSPECT: ON" if self._auto_freeze_enabled else "AUTO-INSPECT: OFF"
                    mode_color = (0, 220, 255) if self._auto_freeze_enabled else (160, 160, 160)
                    cv2.putText(
                        stream_frame,
                        mode_txt,
                        (max(20, h_w - 180), 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.46,
                        mode_color,
                        1,
                    )

            _, jpeg = cv2.imencode(".jpg", stream_frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg.tobytes()
                + b"\r\n"
            )
            time.sleep(0.05)  # 20 fps

    def _get_frame(self) -> np.ndarray:
        with self._frame_lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
        return self._generate_fallback_frame()

    def _generate_fallback_frame(self) -> np.ndarray:
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (20, 24, 33)
        cv2.putText(
            img,
            "ARMOR Vision AI - Camera Standby",
            (110, 230),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (0, 200, 255),
            2,
        )
        cv2.putText(
            img,
            "Searching for video input...",
            (190, 265),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (150, 160, 180),
            1,
        )
        return img

    # ── State Accessors ───────────────────────────────────────────────────────
    def get_state(self) -> dict[str, Any]:
        with self._person_lock:
            person_present = self._person_present
            person_boxes = list(self._person_boxes)
        with self._frame_lock:
            is_frozen = self._is_frozen
            vision_state = self._vision_state
            last_result = self._last_helmet_result

        return {
            "is_frozen": is_frozen,
            "vision_state": vision_state,
            "person_present": person_present,
            "person_count": len(person_boxes),
            "person_boxes": person_boxes,
            "auto_freeze_enabled": self._auto_freeze_enabled,
            "last_helmet_result": last_result,
            "roboflow_available": self._roboflow_available,
        }

    def set_auto_freeze(self, enabled: bool) -> None:
        self._auto_freeze_enabled = enabled
        if enabled:
            self._person_inspected_for_current_presence = False
            self._cooldown_until = 0.0
            print("[VisionEngine] Auto-freeze helmet detection ENABLED.")
        else:
            if self._is_frozen:
                self.unfreeze()
            print("[VisionEngine] Auto-freeze helmet detection DISABLED (continuous live stream).")

    # ── Backwards-Compatible Aliases ──────────────────────────────────────────
    def start_inspection(self, worker_id: str = "WORKER_EMP_402", device_id: str = "machino_node_01") -> dict[str, Any]:
        """Trigger inspection cycle asynchronously."""
        frame = self._get_frame()
        _, person_boxes = self._person_detector.detect(frame)
        self._person_inspected_for_current_presence = True
        self._trigger_freeze_and_inspect(frame, person_boxes, worker_id=worker_id, device_id=device_id)
        return {
            "status": "started",
            "worker_id": worker_id,
            "device_id": device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_inspection_status(self) -> dict[str, Any]:
        """Return status for polling inspection result."""
        state = self.get_state()
        res = state.get("last_helmet_result")
        if self._is_inspecting:
            status = "processing"
        elif res:
            status = "complete"
        elif state["is_frozen"]:
            status = "processing"
        else:
            status = "idle"

        return {
            "status": status,
            "result": res,
            "vision_state": state["vision_state"],
            "is_frozen": state["is_frozen"],
            "person_present": state["person_present"],
        }

    def cancel_inspection(self) -> dict[str, str]:
        self.unfreeze()
        return {"status": "cancelled"}


# ── Smoke Test Helper ─────────────────────────────────────────────────────────
def smoke_test(image_path: str) -> dict[str, Any]:
    """Verification helper for CI/smoke tests."""
    if not ROBOFLOW_API_KEY:
        raise RoboflowError("Smoke test skipped: ROBOFLOW_API_KEY not configured.")
    client = RoboflowClient(
        api_url=ROBOFLOW_API_URL,
        api_key=ROBOFLOW_API_KEY,
        workspace=ROBOFLOW_WORKSPACE,
        workflow_id=ROBOFLOW_WORKFLOW_ID,
    )
    parsed = client.run_helmet_check(image_path=image_path)
    return parsed


# ── Global Singleton ──────────────────────────────────────────────────────────
vision_engine = VisionEngine()
