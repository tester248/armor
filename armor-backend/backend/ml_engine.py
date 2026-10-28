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
            "mean_crest": 1.41,
            "std_crest": 0.2,
            "mean_current": 0.0,
            "std_current": 0.0,
            "mean_voltage": 12.0,
            "std_voltage": 0.0,
            "mean_power": 0.0,
            "std_power": 0.0,
            "mean_temp": 30.0,
            "std_temp": 0.0,
            "sample_count": 0,
            "modalities": ["vibration", "current", "voltage", "temperature"],
        }

    acc = np.array([float(s.get("acc_mag", s.get("rms", 0.0)) or 0.0) for s in samples], dtype=float)
    crest = np.array([float(s.get("crest_factor", 1.41) or 1.41) for s in samples], dtype=float)
    curr = np.array([float(s.get("current_ma", 0.0) or 0.0) for s in samples], dtype=float)
    volt = np.array([float(s.get("voltage_v", 12.0) or 12.0) for s in samples], dtype=float)
    pwr = np.array([float(s.get("power_mw", 0.0) or (float(s.get("voltage_v", 12.0) or 12.0) * float(s.get("current_ma", 0.0) or 0.0))) for s in samples], dtype=float)
    temp = np.array([float(s.get("temperature_c", 30.0) or 30.0) for s in samples], dtype=float)

    return {
        "mean_acc": round(float(np.mean(acc)), 4),
        "std_acc": round(float(np.std(acc)), 4),
        "mean_crest": round(float(np.mean(crest)), 2),
        "std_crest": round(float(np.std(crest)), 2),
        "mean_current": round(float(np.mean(curr)), 2),
        "std_current": round(float(np.std(curr)), 2),
        "mean_voltage": round(float(np.mean(volt)), 2),
        "std_voltage": round(float(np.std(volt)), 2),
        "mean_power": round(float(np.mean(pwr)), 2),
        "std_power": round(float(np.std(pwr)), 2),
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
    latest_sample: Mapping[str, Any] | None = None,
    raw_score: float | None = None,
) -> dict[str, Any]:
    """Decomposes telemetry into:
      1. Calibrated Anomaly Percentage (0% to 100%)
      2. Per-parameter deviation (sigma) from learned baseline (vibration, current, voltage, temp)
      3. Sensor Modality Weightages summing to 100%
      4. Single-parameter spike anomaly detection (triggers if ANY single parameter spikes!)
      5. Top contributing failure mode
    """
    fv = np.asarray(feature_vector, dtype=float).reshape(-1)
    means = np.asarray(package.get("feature_means", []), dtype=float)
    stds = np.asarray(package.get("feature_stds", []), dtype=float)
    stds = np.where(stds < 1e-6, 1.0, stds)
    threshold = float(package.get("hysteresis_high", package.get("decision_threshold", 0.0)))

    # Parse baseline_stats if stored in package
    baseline = package.get("baseline_stats")
    if isinstance(baseline, str):
        try:
            baseline = json.loads(baseline)
        except Exception:
            baseline = {}
    if not isinstance(baseline, dict):
        baseline = {}

    import math

    # 1. Vibration (ADXL345)
    vib_cur = float(latest_sample.get("rms", latest_sample.get("acc_mag", fv[0] if len(fv) > 0 else 0.0))) if latest_sample else float(fv[0] if len(fv) > 0 else 0.0)
    vib_peak = float(fv[2] if len(fv) > 2 else vib_cur)
    vib_cf = float(latest_sample.get("crest_factor", fv[3] if len(fv) > 3 else 1.41)) if latest_sample else float(fv[3] if len(fv) > 3 else 1.41)
    vib_mean = float(baseline.get("mean_acc", means[0] if len(means) > 0 else 0.035))
    vib_std = float(baseline.get("std_acc", stds[0] if len(stds) > 0 else 0.015))
    vib_floor = min(max(vib_std, 0.015), 0.04)
    
    # Directional deviation: vibration only triggers on excess surge
    z_vib_cur = (vib_cur - vib_mean) / vib_floor if vib_cur > vib_mean else 0.0
    z_vib_peak = (vib_peak - vib_mean) / vib_floor if vib_peak > vib_mean else 0.0
    z_vib_mag = max(z_vib_cur, z_vib_peak)
    if vib_cur >= 0.15:
        z_vib_mag = max(z_vib_mag, 3.0 + (vib_cur - 0.15) / 0.05)
    z_cf = (vib_cf - float(baseline.get("mean_crest", 1.8))) / max(float(baseline.get("std_crest", 0.4)), 0.4) if vib_cf > float(baseline.get("mean_crest", 1.8)) else 0.0
    z_vib = max(z_vib_mag, z_cf * 0.7)

    # 2. Current (INA219) - handles extra power load immediately
    curr_cur = float(latest_sample.get("current_ma", fv[4] if len(fv) > 4 else 0.0)) if latest_sample else float(fv[4] if len(fv) > 4 else 0.0)
    curr_peak = float(fv[6] if len(fv) > 6 else curr_cur)
    curr_mean = float(baseline.get("mean_current", means[4] if len(means) > 4 else 0.0))
    curr_std = float(baseline.get("std_current", stds[4] if len(stds) > 4 else 10.0))
    curr_floor = min(max(curr_std, 20.0), 40.0)
    
    # Directional deviation: current only triggers on excess draw (idle 0mA is NOT an anomaly!)
    z_curr_cur = (curr_cur - curr_mean) / curr_floor if curr_cur > curr_mean else 0.0
    z_curr_peak = (curr_peak - curr_mean) / curr_floor if curr_peak > curr_mean else 0.0
    z_curr_base = max(z_curr_cur, z_curr_peak)
    if curr_cur >= 280.0:
        z_curr_base = max(z_curr_base, 3.5 + (curr_cur - 280.0) / 25.0)

    # 3. Voltage & Power (INA219)
    volt_cur = float(latest_sample.get("voltage_v", fv[7] if len(fv) > 7 else 12.0)) if latest_sample else float(fv[7] if len(fv) > 7 else 12.0)
    z_volt = (10.5 - volt_cur) / 0.5 if volt_cur < 10.5 else ((volt_cur - 13.8) / 0.5 if volt_cur > 13.8 else 0.0)

    pwr_cur = float(latest_sample.get("power_mw", fv[9] if len(fv) > 9 else (volt_cur * curr_cur))) if latest_sample else float(fv[9] if len(fv) > 9 else 0.0)
    pwr_mean = float(baseline.get("mean_power", means[9] if len(means) > 9 else (12.0 * curr_mean)))
    pwr_std = float(baseline.get("std_power", stds[9] if len(stds) > 9 else 250.0))
    pwr_floor = min(max(pwr_std, 500.0), 800.0)
    z_pwr = (pwr_cur - pwr_mean) / pwr_floor if pwr_cur > pwr_mean else 0.0
    
    # Motor power surge is driven by current draw:
    z_curr = max(z_curr_base, z_pwr)
    z_volt_pwr = max(z_volt, z_pwr * 0.5)

    # 4. Temperature (DS18B20)
    temp_cur = float(latest_sample.get("temperature_c", fv[10] if len(fv) > 10 else 30.0)) if latest_sample else float(fv[10] if len(fv) > 10 else 30.0)
    temp_mean = float(baseline.get("mean_temp", means[10] if len(means) > 10 else 30.0))
    temp_std = float(baseline.get("std_temp", stds[10] if len(stds) > 10 else 0.5))
    temp_floor = min(max(temp_std, 1.5), 3.5)
    z_temp = (temp_cur - temp_mean) / temp_floor if temp_cur > temp_mean else 0.0
    if temp_cur >= 50.0:
        z_temp = max(z_temp, 3.5 + (temp_cur - 50.0) / 2.0)

    # Per-Parameter Spike Detection:
    # If ANY single parameter spikes >= 2.5 sigma, anomaly is IMMEDIATELY detected!
    z_max = max(z_curr, z_vib, z_volt_pwr, z_temp)
    is_spike_anomaly = bool(z_max >= 2.5)

    if is_spike_anomaly:
        spike_score = round(0.04 + (z_max - 2.5) * 0.025, 4)
        if z_max >= 4.0:
            spike_pct = min(99.0, round(75.0 + (z_max - 4.0) * 4.0, 1))
        else:
            spike_pct = round(55.0 + (z_max - 2.5) * 13.0, 1)
    elif z_max >= 1.8:
        spike_score = round((z_max - 2.5) * 0.015, 4)
        spike_pct = round(30.0 + (z_max - 1.8) * 35.0, 1)
    else:
        spike_score = round(-0.06 - (1.8 - z_max) * 0.04, 4)
        spike_pct = max(1.0, round(z_max * 14.0, 1))

    # Evaluate Forest Score if available and valid
    if raw_score is None and package:
        model_path = package.get("model_path")
        if model_path:
            raw_score = score_with_forest(fv, model_path)

    if raw_score is not None:
        final_score = round(max(float(raw_score), spike_score), 4)
        is_anomaly = bool(is_spike_anomaly or raw_score >= threshold)
    else:
        final_score = spike_score
        is_anomaly = is_spike_anomaly

    anomaly_pct = spike_pct if not is_anomaly else max(spike_pct, 55.0)
    anomaly_pct = round(max(1.0, min(99.9, anomaly_pct)), 1)

    # Sub-scores per modality
    def _to_subscore(z: float) -> tuple[float, str]:
        sub = 100.0 / (1.0 + math.exp(-1.5 * (z - 2.5)))
        sub = round(max(2.0, min(99.0, sub)), 1)
        if z >= 2.5:
            st = "ANOMALOUS"
        elif z >= 1.8:
            st = "ELEVATED"
        else:
            st = "NOMINAL"
        return sub, st

    vib_sub, vib_status = _to_subscore(z_vib)
    curr_sub, curr_status = _to_subscore(z_curr)
    volt_sub, volt_status = _to_subscore(z_volt_pwr)
    temp_sub, temp_status = _to_subscore(z_temp)

    # Modality weightages summing to 100%
    total_z = z_vib + z_curr + z_volt_pwr + z_temp + 1e-4
    vib_w = round((z_vib / total_z) * 100.0, 1)
    curr_w = round((z_curr / total_z) * 100.0, 1)
    volt_w = round((z_volt_pwr / total_z) * 100.0, 1)
    temp_w = max(0.0, round(100.0 - (vib_w + curr_w + volt_w), 1))

    # Primary failure driver
    z_dict = {
        "Motor Current (INA219)": z_curr,
        "Vibration (ADXL345)": z_vib,
        "Voltage & Power (INA219)": z_volt_pwr,
        "Temperature (DS18B20)": z_temp,
    }
    top_contributor = max(z_dict, key=z_dict.get)
    if z_max < 1.8 and not is_anomaly:
        top_contributor = "Multi-Modal Sensor Array (Nominal)"

    modalities = {
        "vibration": {
            "name": "Vibration (ADXL345)",
            "weight_pct": vib_w,
            "sub_score_pct": vib_sub,
            "status": vib_status,
            "channels": {
                "rms_g": {
                    "value": round(vib_cur, 4),
                    "nominal_mean": round(vib_mean, 4),
                    "nominal_std": round(vib_std, 4),
                    "deviation_sigma": round(z_vib_mag, 2),
                },
                "crest_factor": {
                    "value": round(vib_cf, 2),
                    "nominal_mean": round(float(baseline.get("mean_crest", 1.8)), 2),
                    "nominal_std": round(float(baseline.get("std_crest", 0.4)), 2),
                    "deviation_sigma": round(z_cf, 2),
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
                    "value": round(curr_cur, 1),
                    "nominal_mean": round(curr_mean, 1),
                    "nominal_std": round(curr_std, 1),
                    "deviation_sigma": round(z_curr, 2),
                },
                "peak_current_ma": {
                    "value": round(curr_peak, 1),
                    "nominal_mean": round(curr_mean, 1),
                    "nominal_std": round(curr_std, 1),
                    "deviation_sigma": round(z_curr, 2),
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
                    "value": round(volt_cur, 2),
                    "nominal_mean": round(float(baseline.get("mean_voltage", 12.0)), 2),
                    "nominal_std": round(float(baseline.get("std_voltage", 0.1)), 2),
                    "deviation_sigma": round(z_volt, 2),
                },
                "power_mw": {
                    "value": round(pwr_cur, 1),
                    "nominal_mean": round(pwr_mean, 1),
                    "nominal_std": round(pwr_std, 1),
                    "deviation_sigma": round(z_pwr, 2),
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
                    "value": round(temp_cur, 1),
                    "nominal_mean": round(temp_mean, 1),
                    "nominal_std": round(temp_std, 1),
                    "deviation_sigma": round(z_temp, 2),
                },
            },
        },
    }

    return {
        "anomaly_score": round(float(final_score), 4),
        "decision_threshold": round(float(threshold), 4),
        "is_anomaly": is_anomaly,
        "anomaly_percentage": anomaly_pct,
        "top_contributor": top_contributor,
        "modalities": modalities,
    }