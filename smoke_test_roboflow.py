"""
ARMOR – Roboflow Workflow Smoke Test
====================================
Runs the "Helmet Check Hackathon Demo" workflow on a single sample image
and asserts the expected output keys exist.

Usage:
  .\armor-backend\.venv\Scripts\python.exe smoke_test_roboflow.py [image_path]

If no image_path is given, creates a synthetic test image (red helmet-shaped
blob on a person-like background) and runs the workflow on it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "armor-backend"))

from backend.vision import smoke_test, RoboflowError


def _make_synthetic_image() -> Path:
    """Create a small synthetic image for testing when no real image is available."""
    import cv2
    import numpy as np

    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (40, 40, 60)  # dark background

    # Draw a person-like blob
    cv2.circle(img, (320, 300), 100, (200, 150, 100), -1)  # head/skin
    cv2.circle(img, (320, 200), 50, (30, 30, 150), -1)     # helmet (red-ish in BGR)

    out = Path("data/smoke_test_sample.jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    return out


def main() -> int:
    image_path = sys.argv[1] if len(sys.argv) > 1 else None

    if image_path is None:
        print("[Smoke Test] No image provided — generating synthetic test image.")
        image_path = _make_synthetic_image()
        print(f"[Smoke Test] Synthetic image: {image_path}")
    else:
        image_path = Path(image_path)
        if not image_path.exists():
            print(f"[Smoke Test] Image not found: {image_path}")
            return 1

    try:
        result = smoke_test(str(image_path))
        print(f"[Smoke Test] PASSED — {result}")
        return 0
    except RoboflowError as e:
        print(f"[Smoke Test] FAILED — {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
