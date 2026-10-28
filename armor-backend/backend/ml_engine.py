from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.linear_model import Ridge

FEATURE_ORDER = [
    "mean_acc_mag",
    "std_acc_mag",
    "max_acc_mag",
    "crest_factor",
    "temperature_c",
    "current_mean",
    "current_std",
    "range_ratio",
]


def _values(window: Sequence[Mapping[str, float]], key: str) -> np.ndarray:
    out: list[float] = []
    for sample in window:
        try:
            out.append(float(sample.get(key, 0.0)))
        except (TypeError, ValueError):
            out.append(0.0)
    return np.array(out, dtype=float)


def _std(values: np.ndarray) -> float:
    if values.size <= 1:
        return 0.0
    return float(np.std(values))


def extract_feature_vector(window: Sequence[Mapping[str, float]]) -> np.ndarray:
    """Build the 8-feature vector scored by the server-side model.

    The ESP32 reports RMS vibration, crest factor, temperature and current; the
    old vector was padded with gyro/axis features that are always zero, which
    left IsolationForest with almost no structure to separate normal from
    abnormal operation.
    """
    if not window:
        raise ValueError("Cannot extract features from an empty window.")

    acc = _values(window, "acc_mag")
    crest = _values(window, "crest_factor")
    temp = _values(window, "temperature_c")
    current = _values(window, "current_ma")

    mean_acc = float(np.mean(acc))
    acc_range = float(np.max(acc) - np.min(acc))

    return np.array(
        [
            mean_acc,
            _std(acc),
            float(np.max(acc)),
            float(np.mean(crest)),
            float(np.mean(temp)),
            float(np.mean(current)),
            _std(current),
            acc_range / (abs(mean_acc) + 1e-6),
        ],
        dtype=float,
    )


def build_feature_matrix(
    samples: Sequence[Mapping[str, float]],
    window_size: int,
) -> np.ndarray:
    if not samples:
        return np.empty((0, len(FEATURE_ORDER)))

    if window_size <= 1:
        window_size = 2

    if len(samples) < window_size:
        windows = [samples]
    else:
        step = max(1, window_size // 2)
        windows = [
            samples[start : start + window_size]
            for start in range(0, len(samples) - window_size + 1, step)
        ]

    feature_rows = [extract_feature_vector(window) for window in windows if window]
    if not feature_rows:
        return np.empty((0, len(FEATURE_ORDER)))
    return np.vstack(feature_rows)


def train_isolation_forest(
    feature_matrix: np.ndarray,
    contamination: float,
    model_path: str | Path,
) -> dict:
    """Train a full IsolationForest on the backend and persist it to disk.

    Scoring runs on the PC, so there is no reason to distill the forest into a
    linear surrogate: the Ridge approximation was fit on nearly constant
    training data and extrapolated in the wrong direction (higher vibration
    produced a *lower* anomaly score). The forest itself is scale-free and
    flags out-of-range windows even when training saw nothing like them.
    """
    if feature_matrix.shape[0] < 8:
        raise ValueError("Need at least 8 windows for calibration.")

    forest = IsolationForest(
        n_estimators=300,
        contamination=contamination,
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    forest.fit(feature_matrix)

    train_scores = -forest.decision_function(feature_matrix)
    out_path = Path(model_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(forest, out_path, compress=3)

    stds = np.std(feature_matrix, axis=0)
    return {
        "model_type": "isolation_forest",
        "model_path": str(out_path),
        "feature_order": FEATURE_ORDER,
        "feature_means": np.mean(feature_matrix, axis=0).tolist(),
        "feature_stds": np.where(stds < 1e-6, 1.0, stds).tolist(),
        "contamination": float(contamination),
        "window_count": int(feature_matrix.shape[0]),
        "train_score_mean": float(np.mean(train_scores)),
        "train_score_p95": float(np.percentile(train_scores, 95)),
        # score = -decision_function, so 0 is the forest's own boundary.
        "decision_threshold": 0.0,
        "hysteresis_high": 0.0,
        "hysteresis_low": 0.0,
    }


_MODEL_CACHE: dict[str, tuple[float, IsolationForest]] = {}


def load_forest(model_path: str | Path) -> IsolationForest | None:
    """Load a persisted forest, reusing it while the file is unchanged."""
    path = Path(model_path)
    try:
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
        cached = _MODEL_CACHE.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1]
        forest = joblib.load(path)
        _MODEL_CACHE[str(path)] = (mtime, forest)
        return forest
    except Exception as exc:  # corrupt file / sklearn version drift
        print(f"[ML] Could not load model {path}: {exc}")
        return None


def score_with_forest(
    feature_vector: np.ndarray,
    model_path: str | Path,
) -> float | None:
    """Return an anomaly score where higher means more anomalous."""
    forest = load_forest(model_path)
    if forest is None:
        return None
    vector = np.asarray(feature_vector, dtype=float).reshape(1, -1)
    try:
        return float(-forest.decision_function(vector)[0])
    except Exception as exc:
        print(f"[ML] Forest scoring failed: {exc}")
        return None


def train_isolation_forest_distilled(
    feature_matrix: np.ndarray,
    contamination: float,
) -> dict:
    if feature_matrix.shape[0] < 8:
        raise ValueError("Need at least 8 windows for calibration.")

    feature_means = np.mean(feature_matrix, axis=0)
    feature_stds = np.std(feature_matrix, axis=0)
    feature_stds = np.where(feature_stds < 1e-6, 1.0, feature_stds)

    normalized = (feature_matrix - feature_means) / feature_stds

    iso = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=120,
    )
    iso.fit(feature_matrix)
    iso_scores = -iso.score_samples(feature_matrix)

    distill = Ridge(alpha=1.0)
    distill.fit(normalized, iso_scores)
    distilled_scores = distill.predict(normalized)

    high = float(np.percentile(distilled_scores, 95))
    low = float(np.percentile(distilled_scores, 90))

    if np.std(iso_scores) < 1e-8 or np.std(distilled_scores) < 1e-8:
        quality = 0.0
    else:
        quality = float(np.corrcoef(iso_scores, distilled_scores)[0, 1])

    return {
        "feature_means": feature_means.tolist(),
        "feature_stds": feature_stds.tolist(),
        "weights": distill.coef_.tolist(),
        "bias": float(distill.intercept_),
        "decision_threshold": high,
        "hysteresis_high": high,
        "hysteresis_low": low,
        "quality_correlation": quality,
        "window_count": int(feature_matrix.shape[0]),
    }


def train_oneclass_svm_distilled(
    feature_matrix: np.ndarray,
    contamination: float,
) -> dict:
    if feature_matrix.shape[0] < 8:
        raise ValueError("Need at least 8 windows for calibration.")

    feature_means = np.mean(feature_matrix, axis=0)
    feature_stds = np.std(feature_matrix, axis=0)
    feature_stds = np.where(feature_stds < 1e-6, 1.0, feature_stds)

    normalized = (feature_matrix - feature_means) / feature_stds

    ocsvm = OneClassSVM(
        kernel="rbf",
        nu=float(max(0.01, min(0.40, contamination))),
        gamma="scale",
    )
    ocsvm.fit(normalized)
    ocsvm_scores = -ocsvm.decision_function(normalized).reshape(-1)

    distill = Ridge(alpha=1.0)
    distill.fit(normalized, ocsvm_scores)
    distilled_scores = distill.predict(normalized)

    high = float(np.percentile(distilled_scores, 95))
    low = float(np.percentile(distilled_scores, 90))

    if np.std(ocsvm_scores) < 1e-8 or np.std(distilled_scores) < 1e-8:
        quality = 0.0
    else:
        quality = float(np.corrcoef(ocsvm_scores, distilled_scores)[0, 1])

    return {
        "feature_means": feature_means.tolist(),
        "feature_stds": feature_stds.tolist(),
        "weights": distill.coef_.tolist(),
        "bias": float(distill.intercept_),
        "decision_threshold": high,
        "hysteresis_high": high,
        "hysteresis_low": low,
        "quality_correlation": quality,
        "window_count": int(feature_matrix.shape[0]),
    }


def score_feature_vector(feature_vector: np.ndarray, package: Mapping[str, object]) -> float:
    means = np.array(package["feature_means"], dtype=float)
    stds = np.array(package["feature_stds"], dtype=float)
    stds = np.where(stds < 1e-6, 1.0, stds)
    weights = np.array(package["weights"], dtype=float)
    bias = float(package["bias"])

    z = (feature_vector - means) / stds
    return float(np.dot(weights, z) + bias)


def latest_feature_vector(
    samples: Sequence[Mapping[str, float]],
    window_size: int,
) -> np.ndarray | None:
    if not samples:
        return None
    subset = samples[-window_size:] if len(samples) >= window_size else samples
    if not subset:
        return None
    return extract_feature_vector(subset)


def acc_threshold_stats(samples: Sequence[Mapping[str, float]]) -> dict:
    acc = np.array([float(sample.get("acc_mag", 0.0)) for sample in samples], dtype=float)
    mean_acc = float(np.mean(acc))
    std_acc = float(np.std(acc))
    threshold = float(mean_acc + (3.0 * std_acc))
    return {
        "mean_acc": mean_acc,
        "std_acc": std_acc,
        "threshold_mean_3sigma": threshold,
    }


def build_checksum(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
