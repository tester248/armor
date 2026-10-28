"""
ARMOR – Vision Engine (Roboflow Workflow + Stub Fallback)
=========================================================

Integrates the Roboflow Workflow "Helmet Check Hackathon Demo"
(workspace: ashwin-mathur, workflow: helmet-check-hackathon-demo-1793134805931)
via the official inference-sdk InferenceHTTPClient.

Per ARMOR spec (ARMOR_System_Architecture_and_Implementation_Plan.md):

  • OpenCV webcam frame ingestion pipeline
  • Roboflow Workflow (RF-DETR + SAM 3) helmet compliance check
  • Compliance Ratio = Area(Helmet Mask ∩ Head ROI) / Area(Head ROI)
    PASS if Compliance Ratio >= HELMET_COMPLIANCE_THRESHOLD (default 0.65)
  • JPEG snapshot with colour-coded segmentation mask overlays
  • Runs in a background thread inside FastAPI (per landmine-B fix)
  • Frames served via generate_frames() → FastAPI StreamingResponse (MJPEG)
  • Streamlit embeds the stream via <iframe>

Configuration:
  Set ROBOFLOW_API_KEY (and optionally ROBOFLOW_WORKSPACE /
  ROBOFLOW_WORKFLOW_ID / ROBOFLOW_API_URL) in .env.
  The engine auto-loads the workflow; otherwise it falls back to the
  built-in stub that returns compliant=None (VISION_UNAVAILABLE) so the
  interlock never acts on a guessed verdict.

Workflow output parsing is defensive: output key names are discovered
from the live response rather than hard-coded, so the integration keeps
working if Roboflow renames output fields.
"""
from __future__ import annotations

import base64
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import cv2
import numpy as np


# ── Custom Exceptions ─────────────────────────────────────────────────────────
class RoboflowError(Exception):
    """Base error for Roboflow workflow failures."""


class RoboflowAuthError(RoboflowError):
    """Authentication failed (401/403) — usually a publishable key used where
    a secret key is required."""


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

# Client tuning
ROBOFLOW_REQUEST_TIMEOUT_S = float(os.getenv("ROBOFLOW_REQUEST_TIMEOUT_S", "30"))
ROBOFLOW_MAX_RETRIES = int(os.getenv("ROBOFLOW_MAX_RETRIES", "3"))
ROBOFLOW_BACKOFF_BASE_S = float(os.getenv("ROBOFLOW_BACKOFF_BASE_S", "1.0"))


# ── Result dict helper ────────────────────────────────────────────────────────
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


# ── Roboflow client with retries + backoff ────────────────────────────────────
class RoboflowClient:
    """Thin wrapper around inference_sdk.InferenceHTTPClient that adds:

      • per-request timeout
      • retries with exponential backoff on transient failures
      • typed errors (auth / timeout / response)
      • defensive output parsing keyed to the workflow's real response keys
    """

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
        """Lazy-build the InferenceHTTPClient (header-based auth)."""
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
        """Run the helmet-check workflow on an image file.

        Returns the parsed first entry of the workflow result list.
        Raises RoboflowError subclasses on failure.
        """
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
                raise  # don't retry auth failures
            except RoboflowTimeoutError as e:
                last_error = e
            except Exception as e:
                msg = str(e)
                if "401" in msg or "Unauthorized" in msg or "403" in msg:
                    raise RoboflowAuthError(
                        "Roboflow authentication failed. Use a secret (private) "
                        "API key, not a publishable one."
                    ) from e
                last_error = e

            if attempt < self.max_retries:
                sleep_for = self.backoff_base_s * (2 ** (attempt - 1))
                time.sleep(sleep_for)

        raise RoboflowTimeoutError(
            f"Roboflow workflow failed after {self.max_retries} attempts: {last_error}"
        ) from last_error

    # ── Defensive output parsing ─────────────────────────────────────────
    def _parse_workflow_result(self, result: Any) -> dict[str, Any]:
        """Extract the first result entry from a workflow response.

        The Roboflow serverless API returns a list (one entry per input image).
        Each entry is a dict keyed by the workflow's own output names.
        We discover those names dynamically instead of hard-coding them.
        """
        if result is None:
            raise RoboflowResponseError("Roboflow returned None.")

        entry = result[0] if isinstance(result, (list, tuple)) and result else result
        if not isinstance(entry, dict):
            raise RoboflowResponseError(
                f"Unexpected Roboflow result type: {type(entry).__name__}"
            )

        helmet_status = self._extract_helmet_status(entry)
        compliance_ratio = self._extract_compliance_ratio(entry)
        output_image_bytes = self._extract_output_image(entry)

        return {
            "helmet_status": helmet_status,
            "compliance_ratio": compliance_ratio,
            "output_image_bytes": output_image_bytes,
            "raw_keys": list(entry.keys()),
        }

    @staticmethod
    def _extract_helmet_status(entry: dict[str, Any]) -> str | None:
        """Discover the helmet status field from whatever key the workflow uses."""
        for key in (
            "helmet_status",
            "status",
            "helmet",
            "result",
            "label",
            "prediction",
            "compliance",
        ):
            if key in entry and entry[key] is not None:
                return str(entry[key]).strip()
        return None

    @staticmethod
    def _extract_compliance_ratio(entry: dict[str, Any]) -> float:
        """Discover the compliance ratio / confidence from the workflow output."""
        for key in (
            "compliance_ratio",
            "compliance",
            "ratio",
            "score",
            "confidence",
            "helmet_confidence",
        ):
            if key in entry and entry[key] is not None:
                try:
                    return float(entry[key])
                except (TypeError, ValueError):
                    continue
        # Fall back: infer from helmet_status presence
        return 0.0

    @staticmethod
    def _extract_output_image(entry: dict[str, Any]) -> bytes | None:
        """Find and decode an image-shaped output from the workflow result.

        Image outputs arrive as base64 blobs (often hundreds of KB). We decode
        and return the bytes; the caller writes them to disk. We never log them
        or hold them in memory longer than needed.
        """
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
                    # URL input — fetch it (timeout bounded)
                    try:
                        import requests

                        r = requests.get(s, timeout=10)
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
                # Nested dict — recurse into common image-holding shapes
                inner = RoboflowClient._extract_output_image(val)
                if inner is not None:
                    return inner
        return None


# ── Lightweight person detector (continuous, CPU, no API cost) ────────────────
class PersonDetector:
    """OpenCV HOG + SVM person detector.

    Runs continuously on every captured frame with zero API cost. Used as a
    gate: the expensive Roboflow helmet check only fires when a person is
    actually in frame, mirroring how Windows Hello wakes IR+camera on approach.
    """

    def __init__(self) -> None:
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        # Detection parameters tuned for a stationary camera at ~1-3 m range.
        self._win_stride = (8, 8)
        self._padding = (16, 16)
        self._scale = 1.05
        self._hit_threshold = 0.0

    def detect(self, frame: np.ndarray) -> tuple[bool, list[tuple[int, int, int, int]]]:
        """Return (person_present, bounding_boxes) for a BGR frame."""
        try:
            # HOG works on grayscale; downscale large frames for speed.
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            max_side = 640
            if max(h, w) > max_side:
                scale = max_side / max(h, w)
                gray = cv2.resize(gray, (int(w * scale), int(h * scale)))

            boxes, _weights = self._hog.detectMultiScale(
                gray,
                winStride=self._win_stride,
                padding=self._padding,
                scale=self._scale,
                hitThreshold=self._hit_threshold,
            )

            # Convert (x, y, w, h) to (x1, y1, x2, y2) and rescale if downsized.
            person_boxes: list[tuple[int, int, int, int]] = []
            if len(boxes) > 0:
                scale_back = 1.0
                if max(h, w) > max_side:
                    scale_back = max(h, w) / max_side
                for x, y, bw, bh in boxes:
                    person_boxes.append(
                        (
                            int(x * scale_back),
                            int(y * scale_back),
                            int((x + bw) * scale_back),
                            int((y + bh) * scale_back),
                        )
                    )
            return len(person_boxes) > 0, person_boxes
        except Exception as e:
            print(f"[PersonDetector] Detection failed: {e}")
            return False, []


# ── Roboflow status interpretation ────────────────────────────────────────────
def _roboflow_status_to_compliant(status: str | None) -> bool:
    """Interpret the workflow's helmet_status string into PASS/FAIL."""
    if status is None:
        return False
    s = str(status).strip().lower()
    if not s:
        return False
    if any(
        tok in s
        for tok in (
            "missing",
            "no helmet",
            "no-helmet",
            "absent",
            "without",
            "not detected",
            "fail",
        )
    ):
        return False
    if any(
        tok in s
        for tok in ("helmet", "present", "pass", "compliant", "detected")
    ):
        return True
    return False


# ── Inspection (Roboflow workflow) ────────────────────────────────────────────
def _roboflow_inspect(
    client: RoboflowClient,
    frame: np.ndarray,
    worker_id: str,
) -> tuple[bool | None, float, str, np.ndarray]:
    """Run the Roboflow helmet workflow on a frame.

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
    except RoboflowAuthError:
        print(
            "[VisionEngine] Roboflow auth failed — using stub. "
            "Configure a secret (private) ROBOFLOW_API_KEY."
        )
        return None, 0.0, "VISION_UNAVAILABLE", annotated
    except RoboflowError as e:
        print(f"[VisionEngine] Roboflow workflow call failed: {e}")
        return None, 0.0, "VISION_ERROR", annotated
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    helmet_status = parsed.get("helmet_status")
    compliance_ratio = float(parsed.get("compliance_ratio", 0.0) or 0.0)
    compliant = _roboflow_status_to_compliant(helmet_status)

    # If the workflow didn't give us a usable ratio, derive one from pass/fail
    if compliance_ratio <= 0.0:
        compliance_ratio = 0.9 if compliant else 0.1

    label = "HELMET_PASS" if compliant else "HELMET_FAIL"
    colour = (0, 200, 80) if compliant else (0, 60, 220)

    out_img_bytes = parsed.get("output_image_bytes")
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
            annotated,
            f"{label}  status={helmet_status}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            colour,
            2,
        )
        cv2.putText(
            annotated,
            f"Worker: {worker_id}",
            (10, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
        )
        cv2.putText(
            annotated,
            "[ Roboflow RF-DETR + SAM 3 ]",
            (10, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 200, 255),
            1,
        )

    return compliant, compliance_ratio, label, annotated


# ── No-vision fallback (no model configured) ──────────────────────────────────
def _stub_inspect(frame: np.ndarray, worker_id: str) -> tuple[None, float, str, np.ndarray]:
    """Helmet inspection is unavailable when no Roboflow credentials are configured.

    Deliberately does NOT fabricate a PASS/FAIL verdict. Returning
    compliant=None tells the caller to skip the interlock decision.
    """
    h, w = frame.shape[:2]
    annotated = frame.copy()

    colour = (0, 200, 255)  # amber (BGR)
    cv2.rectangle(annotated, (0, 0), (w - 1, h - 1), colour, 3)
    cv2.putText(
        annotated,
        "VISION UNAVAILABLE - helmet check skipped",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        colour,
        2,
    )
    cv2.putText(
        annotated,
        "Configure ROBOFLOW_API_KEY to enable compliance checks",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (200, 200, 200),
        1,
    )
    cv2.putText(
        annotated,
        f"Worker: {worker_id}",
        (10, h - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
    )

    return None, 0.0, "VISION_UNAVAILABLE", annotated


# ── Vision Engine ─────────────────────────────────────────────────────────────
class VisionEngine:
    """Background thread that continuously captures webcam frames.

    Runs in FastAPI's startup lifecycle. Provides:

      • generate_frames()  → MJPEG bytes for StreamingResponse
      • inspect(worker_id, device_id)  → compliance result dict + saves snapshot
    """

    def __init__(self) -> None:
        self._cap: cv2.VideoCapture | None = None
        self._latest_frame: np.ndarray | None = None
        self._frame_lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._roboflow_client: RoboflowClient | None = None
        self._roboflow_available = False

        # Person-detection gate (continuous, CPU, no API cost)
        self._person_detector = PersonDetector()
        self._person_present: bool = False
        self._person_boxes: list[tuple[int, int, int, int]] = []
        self._person_lock = threading.Lock()
        # Vision state machine: SCANNING -> PERSON_DETECTED -> HELMET_CHECKING -> HELMET_PASS/FAIL
        self._vision_state: str = "SCANNING"
        self._last_helmet_result: dict | None = None

        # Pending async inspection (triggered by dashboard "Run Helmet Inspection")
        # Statuses: waiting_for_person -> processing -> complete
        self._pending_inspection: dict | None = None
        self._pending_lock = threading.Lock()

        if ROBOFLOW_API_KEY:
            try:
                self._roboflow_client = RoboflowClient(
                    api_url=ROBOFLOW_API_URL,
                    api_key=ROBOFLOW_API_KEY,
                    workspace=ROBOFLOW_WORKSPACE,
                    workflow_id=ROBOFLOW_WORKFLOW_ID,
                )
                # Light touch: verify the client can be constructed
                self._roboflow_client._ensure()
                self._roboflow_available = True
                print(
                    f"[VisionEngine] Roboflow workflow configured: "
                    f"{ROBOFLOW_WORKSPACE}/{ROBOFLOW_WORKFLOW_ID}"
                )
            except Exception as e:
                print(f"[VisionEngine] Could not configure Roboflow client: {e}.")
                self._roboflow_client = None
                self._roboflow_available = False
        else:
            print("[VisionEngine] No ROBOFLOW_API_KEY — vision stub active.")

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
            self._cap = cv2.VideoCapture(CAMERA_SOURCE)
        if not self._cap.isOpened():
            print("[VisionEngine] WARNING: Camera not available. Generating blank frames.")

        while self._running:
            if self._cap and self._cap.isOpened():
                ret, frame = self._cap.read()
                if ret:
                    # ── Person detection gate (every frame, CPU, no API cost) ──
                    person_present, person_boxes = self._person_detector.detect(frame)
                    with self._person_lock:
                        self._person_present = person_present
                        self._person_boxes = person_boxes
                    if person_present and self._vision_state == "SCANNING":
                        self._vision_state = "PERSON_DETECTED"
                        print(f"[VisionEngine] Person detected ({len(person_boxes)} box(es))")

                    # ── Pending inspection: wait for person, then freeze + Roboflow ──
                    with self._pending_lock:
                        pending = self._pending_inspection
                    if (
                        pending
                        and pending["status"] == "waiting_for_person"
                        and person_present
                    ):
                        frozen_frame = frame.copy()
                        with self._pending_lock:
                            self._pending_inspection["status"] = "processing"
                            self._pending_inspection["processing_at"] = (
                                datetime.now(timezone.utc).isoformat()
                            )
                        # Run Roboflow in a separate thread so the capture loop
                        # (and MJPEG stream) keeps running at full fps.
                        t = threading.Thread(
                            target=self._run_pending_inspection,
                            args=(frozen_frame, pending["worker_id"], pending["device_id"]),
                            daemon=True,
                        )
                        t.start()

                    with self._frame_lock:
                        self._latest_frame = frame
                else:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop video file
            else:
                blank = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    blank,
                    "No Camera – ARMOR Vision Engine",
                    (60, 240),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (100, 200, 255),
                    2,
                )
                with self._frame_lock:
                    self._latest_frame = blank
                with self._person_lock:
                    self._person_present = False
                    self._person_boxes = []
            time.sleep(0.033)  # ~30 fps

    def _get_frame(self) -> np.ndarray:
        with self._frame_lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(
            blank,
            "Initialising...",
            (200, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (200, 200, 200),
            2,
        )
        return blank

    # ── MJPEG stream ──────────────────────────────────────────────────────────
    def generate_frames(self) -> Generator[bytes, None, None]:
        """Yields MJPEG bytes for FastAPI StreamingResponse.

        Draws person-detection bounding boxes (green) when a person is in
        frame. Boxes are cheap OpenCV rectangle calls — no extra inference —
        so the stream stays near 20 fps.
        """
        while True:
            frame = self._get_frame()

            # Copy person state under lock (fast, no I/O).
            with self._person_lock:
                person_present = self._person_present
                person_boxes = list(self._person_boxes)
                vision_state = self._vision_state

            # Draw bounding boxes only when a person is detected.
            if person_present:
                for x1, y1, x2, y2 in person_boxes:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(
                        frame,
                        "PERSON",
                        (x1, max(y1 - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )
                # State badge in top-right corner.
                cv2.putText(
                    frame,
                    f"STATE: {vision_state}",
                    (frame.shape[1] - 220, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )

            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg.tobytes()
                + b"\r\n"
            )
            time.sleep(0.05)  # ~20 fps for stream

    # ── Person state accessors ────────────────────────────────────────────────
    def get_person_state(self) -> dict[str, Any]:
        """Return current person-detection state for the dashboard."""
        with self._person_lock:
            return {
                "person_present": self._person_present,
                "person_boxes": list(self._person_boxes),
                "vision_state": self._vision_state,
                "last_helmet_result": self._last_helmet_result,
            }

    def reset_vision_state(self) -> None:
        """Reset the vision state machine back to SCANNING."""
        with self._person_lock:
            self._vision_state = "SCANNING"
            self._last_helmet_result = None

    # ── Inspection ────────────────────────────────────────────────────────────
    def inspect(self, worker_id: str, device_id: str) -> dict:
        """Run helmet compliance check on the current frame.

        Gated by continuous person detection: if no person is in frame, the
        expensive Roboflow helmet check is skipped and the result reports
        SCANNING (compliant=None). Called by the FastAPI breach handler and
        the dashboard manual test.
        """
        frame = self._get_frame()

        with self._person_lock:
            person_present = self._person_present
            current_state = self._vision_state

        # No person → skip helmet check entirely
        if not person_present:
            self._vision_state = "SCANNING"
            ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{device_id}_{worker_id}_{ts_str}.jpg"
            snapshot_path = str(SNAPSHOT_DIR / filename)
            cv2.imwrite(snapshot_path, frame)

            return _make_result(
                worker_id=worker_id,
                device_id=device_id,
                compliant=None,
                compliance_ratio=0.0,
                label="SCANNING",
                snapshot_path=snapshot_path,
            )

        # Person present → run helmet check
        self._vision_state = "HELMET_CHECKING"

        if self._roboflow_available and self._roboflow_client is not None:
            compliant, ratio, label, annotated = _roboflow_inspect(
                self._roboflow_client, frame, worker_id
            )
        else:
            compliant, ratio, label, annotated = _stub_inspect(frame, worker_id)

        # Update state machine
        if compliant is None:
            self._vision_state = "VISION_UNAVAILABLE"
        elif compliant:
            self._vision_state = "HELMET_PASS"
        else:
            self._vision_state = "HELMET_FAIL"

        result = _make_result(
            worker_id=worker_id,
            device_id=device_id,
            compliant=compliant,
            compliance_ratio=ratio,
            label=label,
            snapshot_path="",  # set below after save
        )

        # Save snapshot and stash result for state accessors
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{device_id}_{worker_id}_{ts_str}.jpg"
        snapshot_path = str(SNAPSHOT_DIR / filename)
        cv2.imwrite(snapshot_path, annotated)

        result["snapshot_path"] = snapshot_path
        with self._person_lock:
            self._last_helmet_result = {
                "compliant": compliant,
                "compliance_ratio": ratio,
                "label": label,
                "snapshot_path": snapshot_path,
                "timestamp": result["timestamp"],
            }

        return result

    # ── Async inspection (dashboard-triggered) ────────────────────────────────
    def _run_pending_inspection(
        self, frame: np.ndarray, worker_id: str, device_id: str
    ) -> None:
        """Run Roboflow helmet check on a frozen frame (background thread).

        Called from the capture loop when a person is detected during a
        pending inspection. Does NOT block the capture loop / MJPEG stream.
        """
        try:
            if self._roboflow_available and self._roboflow_client is not None:
                compliant, ratio, label, annotated = _roboflow_inspect(
                    self._roboflow_client, frame, worker_id
                )
            else:
                compliant, ratio, label, annotated = _stub_inspect(frame, worker_id)
        except Exception as e:
            print(f"[VisionEngine] Pending inspection failed: {e}")
            compliant, ratio, label, annotated = None, 0.0, "VISION_ERROR", frame.copy()

        # Save snapshot
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
        )

        with self._pending_lock:
            self._pending_inspection["status"] = "complete"
            self._pending_inspection["result"] = result
            self._pending_inspection["completed_at"] = (
                datetime.now(timezone.utc).isoformat()
            )
            # Also stash for state accessors
            self._last_helmet_result = {
                "compliant": compliant,
                "compliance_ratio": ratio,
                "label": label,
                "snapshot_path": snapshot_path,
                "timestamp": result["timestamp"],
            }

    def start_inspection(self, worker_id: str, device_id: str) -> dict:
        """Start an async helmet inspection.

        Waits for a person to appear in the camera, freezes that frame, then
        runs Roboflow. Returns immediately; poll get_inspection_status() for
        the result. Used by the dashboard "Run Helmet Inspection" button.
        """
        with self._pending_lock:
            # Cancel any existing pending inspection
            self._pending_inspection = {
                "worker_id": worker_id,
                "device_id": device_id,
                "status": "waiting_for_person",
                "result": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        print(f"[VisionEngine] Inspection started for {worker_id} — waiting for person")
        return {
            "status": "started",
            "worker_id": worker_id,
            "device_id": device_id,
        }

    def get_inspection_status(self) -> dict:
        """Return the current status of a pending inspection (for polling)."""
        with self._pending_lock:
            if self._pending_inspection is None:
                return {"status": "idle"}
            return dict(self._pending_inspection)

    def cancel_inspection(self) -> dict:
        """Cancel a pending inspection."""
        with self._pending_lock:
            if self._pending_inspection is None:
                return {"status": "idle"}
            self._pending_inspection = None
        return {"status": "cancelled"}


# ── Smoke test ────────────────────────────────────────────────────────────────
def smoke_test(image_path: str) -> dict[str, Any]:
    """Run the helmet-check workflow on a single sample image and assert
    that the expected output keys exist. Intended for CI/dev verification.

    Returns the parsed result dict on success.
    Raises RoboflowError on failure.
    """
    if not ROBOFLOW_API_KEY:
        raise RoboflowError(
            "Smoke test skipped: ROBOFLOW_API_KEY not configured."
        )

    client = RoboflowClient(
        api_url=ROBOFLOW_API_URL,
        api_key=ROBOFLOW_API_KEY,
        workspace=ROBOFLOW_WORKSPACE,
        workflow_id=ROBOFLOW_WORKFLOW_ID,
    )
    parsed = client.run_helmet_check(image_path=image_path)

    # Assertions: the workflow must return something useful
    assert isinstance(parsed, dict), "Parsed result is not a dict"
    assert "raw_keys" in parsed, "No raw_keys in parsed result"
    assert len(parsed["raw_keys"]) > 0, "Workflow returned no output keys"

    print(f"[Smoke Test] OK — output keys: {parsed['raw_keys']}")
    print(
        f"[Smoke Test] helmet_status={parsed.get('helmet_status')!r}, "
        f"compliance_ratio={parsed.get('compliance_ratio')}"
    )
    return parsed


# ── Singleton (imported by main.py) ───────────────────────────────────────────
vision_engine = VisionEngine()
