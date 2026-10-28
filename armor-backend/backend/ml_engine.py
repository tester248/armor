from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.linear_model import Ridge

FEATURE_ORDER = [
    # ── 1. Vibration (ADXL345) ──
    "mean_acc_mag",
    "std_acc_mag",
    "max_acc_mag",
    "crest_factor",
    # ── 2. Current (INA219) ──
    "mean_current_ma",
    "std_current_ma",
    "max_current_ma",
    # ── 3. Voltage & Power (INA219) ──
    "mean_voltage_v",
    "std_voltage_v",
    "mean_power_mw",
    # ── 4. Temperature (DS18B20) ──
    "mean_temp_c",
    "max_temp_c",
]


def _values(
    window: Sequence[Mapping[str, Any]],
    key: str,
    *fallback_keys: str,
    default: float = 0.0,
) -> np.ndarray:
    out: list[float] = []
    keys = (key,) + fallback_keys
    for sample in window:
        val = None
        for k in keys:
            if k in sample and sample[k] is not None:
                val = sample[k]
                break
        try:
            val_f = float(val) if val is not None else default
            out.append(default if (np.isnan(val_f) or np.isinf(val_f)) else val_f)
        except (TypeError, ValueError):
            out.append(default)
    return np.array(out, dtype=float)


def _std(values: np.ndarray) -> float:
    if values.size <= 1:
        return 0.0
    return float(np.std(values))


def extract_feature_vector(window: Sequence[Mapping[str, Any]]) -> np.ndarray:
    """Build the multi-modal 12-feature vector scored by the server-side model.

    Trains and scores across ALL 4 sensor telemetry channels:
      1. Vibration (ADXL345): mean magnitude, std/jitter, peak impact, crest factor
      2. Current (INA219): mean current, ripple std, peak current
      3. Voltage & Power (INA219): mean voltage, voltage std, mean power
      4. Temperature (DS18B20): mean temperature, peak temperature
    """
    if not window:
        raise ValueError("Cannot extract features from an empty window.")

    acc = _values(window, "acc_mag", "rms")
    crest = _values(window, "crest_factor")
    curr = _values(window, "current_ma", "current")
    volt = _values(window, "voltage_v", "voltage")
    pwr = _values(window, "power_mw", "power")
    temp = _values(window, "temperature_c", "temp_c", "temperature")

    # If power is missing or zero but voltage & current are present, derive power
    if np.all(pwr == 0.0) and not np.all(volt == 0.0) and not np.all(curr == 0.0):
        pwr = volt * curr

    mean_acc = float(np.mean(acc)) if acc.size else 0.0
    std_acc = _std(acc)
    max_acc = float(np.max(acc)) if acc.size else 0.0
    mean_crest = float(np.mean(crest)) if crest.size else 0.0

    mean_curr = float(np.mean(curr)) if curr.size else 0.0
    std_curr = _std(curr)
    max_curr = float(np.max(curr)) if curr.size else 0.0

    mean_volt = float(np.mean(volt)) if volt.size else 0.0
    std_volt = _std(volt)
    mean_pwr = float(np.mean(pwr)) if pwr.size else 0.0

    mean_temp = float(np.mean(temp)) if temp.size else 0.0
    max_temp = float(np.max(temp)) if temp.size else 0.0

    return np.array(
        [
            mean_acc,
            std_acc,
            max_acc,
            mean_crest,
            mean_curr,
            std_curr,
            max_curr,
            mean_volt,
            std_volt,
            mean_pwr,
            mean_temp,
            max_temp,
        ],
        dtype=float,
    )


def build_feature_matrix(
    samples: Sequence[Mapping[str, Any]],
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
    """Train a full IsolationForest on the backend and persist it to disk."""
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
        "modalities": ["vibration", "current", "voltage", "power", "temperature"],
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
        if hasattr(forest, "n_features_in_") and forest.n_features_in_ != vector.shape[1]:
            print(
                f"[ML] Model feature dimension mismatch (expected {forest.n_features_in_}, "
                f"got {vector.shape[1]}). Please recalibrate model."
            )
            return None
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
        "feature_order": FEATURE_ORDER,
        "feature_means": feature_means.tolist(),
        "feature_stds": feature_stds.tolist(),
        "weights": distill.coef_.tolist(),
        "bias": float(distill.intercept_),
        "decision_threshold": high,
        "hysteresis_high": high,
        "hysteresis_low": low,
        "quality_correlation": quality,
        "window_count": int(feature_matrix.shape[0]),
        "modalities": ["vibration", "current", "voltage", "power", "temperature"],
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
        "feature_order": FEATURE_ORDER,
        "feature_means": feature_means.tolist(),
        "feature_stds": feature_stds.tolist(),
        "weights": distill.coef_.tolist(),
        "bias": float(distill.intercept_),
        "decision_threshold": high,
        "hysteresis_high": high,
        "hysteresis_low": low,
        "quality_correlation": quality,
        "window_count": int(feature_matrix.shape[0]),
        "modalities": ["vibration", "current", "voltage", "power", "temperature"],
    }


def score_feature_vector(feature_vector: np.ndarray, package: Mapping[str, object]) -> float:
    means = np.array(package["feature_means"], dtype=float)
    stds = np.array(package["feature_stds"], dtype=float)
    stds = np.where(stds < 1e-6, 1.0, stds)
    weights = np.array(package["weights"], dtype=float)
    bias = float(package["bias"])

    if len(feature_vector) != len(weights):
        min_len = min(len(feature_vector), len(weights))
        z = (feature_vector[:min_len] - means[:min_len]) / stds[:min_len]
        return float(np.dot(weights[:min_len], z) + bias)

    z = (feature_vector - means) / stds
    return float(np.dot(weights, z) + bias)


def latest_feature_vector(
    samples: Sequence[Mapping[str, Any]],
    window_size: int,
) -> np.ndarray | None:
    if not samples:
        return None
    subset = samples[-window_size:] if len(samples) >= window_size else samples
    if not subset:
        return None
    return extract_feature_vector(subset)


def compute_multimodal_baseline_stats(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute baseline nominal operating statistics across all 4 sensor modalities."""
    if not samples:
        return {
            "mean_acc": 0.0,
            "std_acc": 0.0,
            "mean_current": 0.0,
            "std_current": 0.0,
            "mean_voltage": 0.0,
            "std_voltage": 0.0,
            "mean_temp": 0.0,
            "std_temp": 0.0,
            "sample_count": 0,
            "modalities": ["vibration", "current", "voltage", "temperature"],
        }

    acc = np.array([float(s.get("acc_mag") or 0.0) for s in samples], dtype=float)
    curr = np.array([float(s.get("current_ma") or 0.0) for s in samples], dtype=float)
    volt = np.array([float(s.get("voltage_v") or 0.0) for s in samples], dtype=float)
    temp = np.array([float(s.get("temperature_c") or 0.0) for s in samples], dtype=float)

    return {
        "mean_acc": round(float(np.mean(acc)), 4),
        "std_acc": round(float(np.std(acc)), 4),
        "mean_current": round(float(np.mean(curr)), 2),
        "std_current": round(float(np.std(curr)), 2),
        "mean_voltage": round(float(np.mean(volt)), 2),
        "std_voltage": round(float(np.std(volt)), 2),
        "mean_temp": round(float(np.mean(temp)), 2),
        "std_temp": round(float(np.std(temp)), 2),
        "sample_count": len(samples),
        "modalities": ["vibration", "current", "voltage", "temperature"],
    }


def acc_threshold_stats(samples: Sequence[Mapping[str, Any]]) -> dict:
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



def decompose_anomaly(
    feature_vector: np.ndarray,
    package: Mapping[str, Any],
    raw_score: float | None = None,
) -> dict[str, Any]:
    """Decomposes the anomaly score into:
      1. Calibrated Anomaly Percentage (0% to 100%)
      2. Sensor Modality Weightages (Vibration, Current, Voltage/Power, Temperature)
      3. Parameter-level deviations (sigma), sub-scores, and status
      4. Top contributing failure mode
    """
    fv = np.asarray(feature_vector, dtype=float).reshape(-1)
    means = np.asarray(package.get("feature_means", []), dtype=float)
    stds = np.asarray(package.get("feature_stds", []), dtype=float)
    stds = np.where(stds < 1e-6, 1.0, stds)
    order = list(package.get("feature_order", FEATURE_ORDER))
    threshold = float(package.get("hysteresis_high", package.get("decision_threshold", 0.0)))

    # Compute raw score if not passed
    if raw_score is None:
        model_path = package.get("model_path")
        if model_path:
            raw_score = score_with_forest(fv, model_path) or 0.0
        elif "weights" in package and "bias" in package:
            raw_score = score_feature_vector(fv, package)
        else:
            raw_score = 0.0

    # 1. Calibrated Anomaly Percentage (0% to 100%)
    # Uses a logistic scaling centered around the decision threshold
    k = 14.0
    import math
    try:
        anomaly_pct = 100.0 / (1.0 + math.exp(-k * (raw_score - threshold)))
    except OverflowError:
        anomaly_pct = 100.0 if raw_score > threshold else 0.0
    anomaly_pct = round(max(1.0, min(99.9, anomaly_pct)), 1)
    is_anomaly = bool(raw_score >= threshold)

    # 2. Individual Feature Deviations (z-scores)
    n_feat = min(len(fv), len(means), len(stds), len(order))
    feat_z: dict[str, float] = {}
    feat_val: dict[str, float] = {}
    feat_mean: dict[str, float] = {}
    feat_std: dict[str, float] = {}

    for i in range(n_feat):
        name = order[i]
        val = float(fv[i])
        m = float(means[i])
        s = float(stds[i])
        z = abs(val - m) / s
        feat_z[name] = z
        feat_val[name] = val
        feat_mean[name] = m
        feat_std[name] = s

    # 3. Group by physical modalities
    # Modality 1: Vibration (ADXL345)
    vib_keys = ["mean_acc_mag", "std_acc_mag", "max_acc_mag", "crest_factor"]
    vib_z_sum = sum(feat_z.get(k, 0.0) for k in vib_keys)
    vib_z_max = max([feat_z.get(k, 0.0) for k in vib_keys] or [0.0])

    # Modality 2: Current (INA219)
    curr_keys = ["mean_current_ma", "std_current_ma", "max_current_ma"]
    curr_z_sum = sum(feat_z.get(k, 0.0) for k in curr_keys)
    curr_z_max = max([feat_z.get(k, 0.0) for k in curr_keys] or [0.0])

    # Modality 3: Voltage & Power (INA219)
    volt_keys = ["mean_voltage_v", "std_voltage_v", "mean_power_mw"]
    volt_z_sum = sum(feat_z.get(k, 0.0) for k in volt_keys)
    volt_z_max = max([feat_z.get(k, 0.0) for k in volt_keys] or [0.0])

    # Modality 4: Temperature (DS18B20)
    temp_keys = ["mean_temp_c", "max_temp_c"]
    temp_z_sum = sum(feat_z.get(k, 0.0) for k in temp_keys)
    temp_z_max = max([feat_z.get(k, 0.0) for k in temp_keys] or [0.0])

    total_z_sum = vib_z_sum + curr_z_sum + volt_z_sum + temp_z_sum
    if total_z_sum < 1e-4:
        vib_w = curr_w = volt_w = temp_w = 25.0
    else:
        vib_w = round((vib_z_sum / total_z_sum) * 100.0, 1)
        curr_w = round((curr_z_sum / total_z_sum) * 100.0, 1)
        volt_w = round((volt_z_sum / total_z_sum) * 100.0, 1)
        temp_w = round(max(0.0, 100.0 - (vib_w + curr_w + volt_w)), 1)

    def _z_to_subscore(z: float) -> tuple[float, str]:
        # Subscore %: maps z-deviation to 0-100%
        sub = 100.0 / (1.0 + math.exp(-1.5 * (z - 2.5)))
        sub = round(max(2.0, min(99.0, sub)), 1)
        if sub >= 70.0:
            status = "ANOMALOUS"
        elif sub >= 40.0:
            status = "ELEVATED"
        else:
            status = "NOMINAL"
        return sub, status

    vib_sub, vib_status = _z_to_subscore(vib_z_max)
    curr_sub, curr_status = _z_to_subscore(curr_z_max)
    volt_sub, volt_status = _z_to_subscore(volt_z_max)
    temp_sub, temp_status = _z_to_subscore(temp_z_max)

    # Determine top contributor
    z_map = {"Vibration": vib_z_sum, "Motor Current": curr_z_sum, "Voltage & Power": volt_z_sum, "Temperature": temp_z_sum}
    top_contributor = max(z_map, key=z_map.get)

    modalities = {
        "vibration": {
            "name": "Vibration (ADXL345)",
            "weight_pct": vib_w,
            "sub_score_pct": vib_sub,
            "status": vib_status,
            "channels": {
                "rms_g": {
                    "value": round(feat_val.get("mean_acc_mag", 0.0), 4),
                    "nominal_mean": round(feat_mean.get("mean_acc_mag", 0.0), 4),
                    "nominal_std": round(feat_std.get("mean_acc_mag", 0.0), 4),
                    "deviation_sigma": round(feat_z.get("mean_acc_mag", 0.0), 2),
                },
                "crest_factor": {
                    "value": round(feat_val.get("crest_factor", 0.0), 2),
                    "nominal_mean": round(feat_mean.get("crest_factor", 0.0), 2),
                    "nominal_std": round(feat_std.get("crest_factor", 0.0), 2),
                    "deviation_sigma": round(feat_z.get("crest_factor", 0.0), 2),
                },
            },
        },
        "current": {
            "name": "Motor Current (INA219)",
            "weight_pct": curr_w,
            "sub_score_pct": curr_sub,
            "status": curr_status,
            "channels": {
                "mean_current_ma": {
                    "value": round(feat_val.get("mean_current_ma", 0.0), 1),
                    "nominal_mean": round(feat_mean.get("mean_current_ma", 0.0), 1),
                    "nominal_std": round(feat_std.get("mean_current_ma", 0.0), 1),
                    "deviation_sigma": round(feat_z.get("mean_current_ma", 0.0), 2),
                },
                "peak_current_ma": {
                    "value": round(feat_val.get("max_current_ma", 0.0), 1),
                    "nominal_mean": round(feat_mean.get("max_current_ma", 0.0), 1),
                    "nominal_std": round(feat_std.get("max_current_ma", 0.0), 1),
                    "deviation_sigma": round(feat_z.get("max_current_ma", 0.0), 2),
                },
            },
        },
        "voltage_power": {
            "name": "Voltage & Power (INA219)",
            "weight_pct": volt_w,
            "sub_score_pct": volt_sub,
            "status": volt_status,
            "channels": {
                "voltage_v": {
                    "value": round(feat_val.get("mean_voltage_v", 0.0), 2),
                    "nominal_mean": round(feat_mean.get("mean_voltage_v", 0.0), 2),
                    "nominal_std": round(feat_std.get("mean_voltage_v", 0.0), 2),
                    "deviation_sigma": round(feat_z.get("mean_voltage_v", 0.0), 2),
                },
                "power_mw": {
                    "value": round(feat_val.get("mean_power_mw", 0.0), 1),
                    "nominal_mean": round(feat_mean.get("mean_power_mw", 0.0), 1),
                    "nominal_std": round(feat_std.get("mean_power_mw", 0.0), 1),
                    "deviation_sigma": round(feat_z.get("mean_power_mw", 0.0), 2),
                },
            },
        },
        "temperature": {
            "name": "Temperature (DS18B20)",
            "weight_pct": temp_w,
            "sub_score_pct": temp_sub,
            "status": temp_status,
            "channels": {
                "temperature_c": {
                    "value": round(feat_val.get("mean_temp_c", 0.0), 1),
                    "nominal_mean": round(feat_mean.get("mean_temp_c", 0.0), 1),
                    "nominal_std": round(feat_std.get("mean_temp_c", 0.0), 1),
                    "deviation_sigma": round(feat_z.get("mean_temp_c", 0.0), 2),
                },
            },
        },
    }

    return {
        "anomaly_score": round(float(raw_score), 4),
        "decision_threshold": round(float(threshold), 4),
        "is_anomaly": is_anomaly,
        "anomaly_percentage": anomaly_pct,
        "top_contributor": top_contributor,
        "modalities": modalities,
    }
