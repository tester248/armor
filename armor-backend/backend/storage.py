"""
ARMOR – SQLite storage layer.
Tables (per ARMOR spec):
  - telemetry       : ADXL345 / INA219 / DS18B20 time-series
  - machine_state   : current per-device state (motor, interlock, anomaly)
  - incidents       : safety violation log
  - worker_badges   : registered ESP32 smart badge registry
  - breach_events   : raw ESP-NOW proximity breach log
  - interlock_log   : history of every LOCKOUT / RESET command
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArmorStore:
    """Thread-safe SQLite store for the ARMOR system."""

    def __init__(self, db_path: str = "data/armor.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._create_tables()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #
    def _create_tables(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                -- ADXL345 / INA219 / DS18B20 telemetry time-series
                CREATE TABLE IF NOT EXISTS telemetry (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id    TEXT    NOT NULL,
                    ts           TEXT    NOT NULL,
                    motor_state  TEXT    DEFAULT 'RUNNING',
                    accel_x      REAL,
                    accel_y      REAL,
                    accel_z      REAL,
                    rms          REAL,
                    crest_factor REAL,
                    voltage_v    REAL,
                    current_ma   REAL,
                    power_mw     REAL,
                    temperature_c REAL,
                    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_device_ts
                    ON telemetry (device_id, ts DESC);

                -- Per-device live state (upserted on every telemetry / event)
                CREATE TABLE IF NOT EXISTS machine_state (
                    device_id               TEXT PRIMARY KEY,
                    motor_state             TEXT    DEFAULT 'IDLE',
                    interlock_active        INTEGER DEFAULT 0,
                    last_telemetry_at       TEXT,
                    is_anomaly              INTEGER DEFAULT 0,
                    active_worker_id        TEXT,
                    proximity_breach_active INTEGER DEFAULT 0,
                    health_score            REAL,
                    current_rms             REAL,
                    current_voltage_v       REAL,
                    current_ma              REAL,
                    current_temp_c          REAL,
                    updated_at              TEXT    DEFAULT CURRENT_TIMESTAMP
                );

                -- Safety incident log (one row per violation event)
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id          TEXT PRIMARY KEY,
                    device_id            TEXT    NOT NULL,
                    worker_id            TEXT,
                    badge_mac            TEXT,
                    violation_type       TEXT    DEFAULT 'MISSING_HELMET',
                    compliance_ratio     REAL,
                    snapshot_path        TEXT,
                    interlock_issued     INTEGER DEFAULT 0,
                    interlock_reset_at   TEXT,
                    interlock_reset_by   TEXT,
                    resolved             INTEGER DEFAULT 0,
                    created_at           TEXT    DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_incidents_device
                    ON incidents (device_id, created_at DESC);

                -- ESP32 Smart Badge registry
                CREATE TABLE IF NOT EXISTS worker_badges (
                    badge_mac      TEXT PRIMARY KEY,
                    worker_id      TEXT    NOT NULL,
                    worker_name    TEXT,
                    department     TEXT,
                    active         INTEGER DEFAULT 1,
                    registered_at  TEXT    DEFAULT CURRENT_TIMESTAMP
                );

                -- Raw ESP-NOW proximity breach event log
                CREATE TABLE IF NOT EXISTS breach_events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id       TEXT    NOT NULL,
                    worker_id       TEXT,
                    badge_mac       TEXT,
                    rssi_raw        INTEGER,
                    rssi_smoothed   REAL,
                    distance_est_m  REAL,
                    ts              TEXT    NOT NULL,
                    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_breach_device
                    ON breach_events (device_id, ts DESC);

                -- History of every LOCKOUT / RESET command issued
                CREATE TABLE IF NOT EXISTS interlock_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id   TEXT    NOT NULL,
                    command     TEXT    NOT NULL,
                    source      TEXT,
                    reason      TEXT,
                    worker_id   TEXT,
                    issued_by   TEXT    DEFAULT 'system',
                    ts          TEXT    NOT NULL,
                    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
                );

                -- ML calibration results and model packages
                CREATE TABLE IF NOT EXISTS calibrations (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_id      TEXT    NOT NULL,
                    device_id       TEXT    NOT NULL,
                    model_package   TEXT    NOT NULL,
                    baseline_stats  TEXT,
                    quality         REAL,
                    window_count    INTEGER,
                    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_cal_machine_device
                    ON calibrations (machine_id, device_id, created_at DESC);

                -- Anomaly event log
                CREATE TABLE IF NOT EXISTS anomaly_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_id  TEXT    NOT NULL,
                    device_id   TEXT    NOT NULL,
                    score       REAL,
                    threshold   REAL,
                    is_anomaly  INTEGER DEFAULT 0,
                    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_anomaly_machine_device
                    ON anomaly_log (machine_id, device_id, created_at DESC);
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return dict(row)

    def _rows_to_list(self, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Telemetry
    # ------------------------------------------------------------------ #
    def insert_telemetry(self, data: dict[str, Any]) -> None:
        """Persist one telemetry record and update machine_state live values."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO telemetry
                    (device_id, ts, motor_state,
                     accel_x, accel_y, accel_z, rms, crest_factor,
                     voltage_v, current_ma, power_mw, temperature_c)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    data.get("device_id", "unknown"),
                    data.get("timestamp", _utc_now()),
                    data.get("motor_state", "UNKNOWN"),
                    data.get("accel_x"),
                    data.get("accel_y"),
                    data.get("accel_z"),
                    data.get("rms"),
                    data.get("crest_factor"),
                    data.get("voltage_v"),
                    data.get("current_ma"),
                    data.get("power_mw"),
                    data.get("temperature_c"),
                ),
            )
            # Upsert live state
            self._conn.execute(
                """
                INSERT INTO machine_state
                    (device_id, motor_state, last_telemetry_at,
                     current_rms, current_voltage_v, current_ma, current_temp_c, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(device_id) DO UPDATE SET
                    motor_state         = excluded.motor_state,
                    last_telemetry_at   = excluded.last_telemetry_at,
                    current_rms         = excluded.current_rms,
                    current_voltage_v   = excluded.current_voltage_v,
                    current_ma          = excluded.current_ma,
                    current_temp_c      = excluded.current_temp_c,
                    updated_at          = excluded.updated_at
                """,
                (
                    data.get("device_id", "unknown"),
                    data.get("motor_state", "UNKNOWN"),
                    data.get("timestamp", _utc_now()),
                    data.get("rms"),
                    data.get("voltage_v"),
                    data.get("current_ma"),
                    data.get("temperature_c"),
                    _utc_now(),
                ),
            )
            self._conn.commit()

    def get_recent_telemetry(
        self,
        device_id: str,
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM telemetry
                WHERE device_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return list(reversed(self._rows_to_list(rows)))

    def get_recent_samples_for_ml(
        self, device_id: str, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Map telemetry rows to the feature keys expected by ml_engine.

        ARMOR uses an ADXL345 (accelerometer only), so the gyro fields from
        MachinoCare 1.0 are reported as zero. The acceleration magnitude is
        derived from the 3 axes when available, otherwise the measured RMS.
        """
        rows = self.get_recent_telemetry(device_id, limit=limit)
        samples: list[dict[str, Any]] = []
        for row in rows:
            ax = row.get("accel_x")
            ay = row.get("accel_y")
            az = row.get("accel_z")
            if ax is not None and ay is not None and az is not None:
                acc_mag = (float(ax) ** 2 + float(ay) ** 2 + float(az) ** 2) ** 0.5
            else:
                acc_mag = float(row.get("rms") or 0.0)
            samples.append(
                {
                    "acc_mag": acc_mag,
                    "gyro_mag": 0.0,
                    "gx": 0.0,
                    "gy": 0.0,
                    "gz": 0.0,
                }
            )
        return samples

    # ------------------------------------------------------------------ #
    # Machine State
    # ------------------------------------------------------------------ #
    def get_machine_state(self, device_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM machine_state WHERE device_id = ?", (device_id,)
            ).fetchone()
        return self._row_to_dict(row) or {"device_id": device_id}

    def set_machine_state(self, device_id: str, updates: dict[str, Any]) -> None:
        state = self.get_machine_state(device_id)
        state.update(updates)
        state["updated_at"] = _utc_now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO machine_state
                    (device_id, motor_state, interlock_active, last_telemetry_at,
                     is_anomaly, active_worker_id, proximity_breach_active,
                     health_score, current_rms, current_voltage_v, current_ma,
                     current_temp_c, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(device_id) DO UPDATE SET
                    motor_state             = excluded.motor_state,
                    interlock_active        = excluded.interlock_active,
                    last_telemetry_at       = excluded.last_telemetry_at,
                    is_anomaly              = excluded.is_anomaly,
                    active_worker_id        = excluded.active_worker_id,
                    proximity_breach_active = excluded.proximity_breach_active,
                    health_score            = excluded.health_score,
                    current_rms             = excluded.current_rms,
                    current_voltage_v       = excluded.current_voltage_v,
                    current_ma              = excluded.current_ma,
                    current_temp_c          = excluded.current_temp_c,
                    updated_at              = excluded.updated_at
                """,
                (
                    device_id,
                    state.get("motor_state", "IDLE"),
                    int(state.get("interlock_active", 0)),
                    state.get("last_telemetry_at"),
                    int(state.get("is_anomaly", 0)),
                    state.get("active_worker_id"),
                    int(state.get("proximity_breach_active", 0)),
                    state.get("health_score"),
                    state.get("current_rms"),
                    state.get("current_voltage_v"),
                    state.get("current_ma"),
                    state.get("current_temp_c"),
                    state.get("updated_at", _utc_now()),
                ),
            )
            self._conn.commit()

    def list_all_devices(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT device_id FROM machine_state"
            ).fetchall()
        return [r["device_id"] for r in rows]

    # ------------------------------------------------------------------ #
    # Incidents
    # ------------------------------------------------------------------ #
    def create_incident(self, data: dict[str, Any]) -> str:
        incident_id = data.get("incident_id") or str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO incidents
                    (incident_id, device_id, worker_id, badge_mac,
                     violation_type, compliance_ratio, snapshot_path,
                     interlock_issued, resolved, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    incident_id,
                    data.get("device_id", "unknown"),
                    data.get("worker_id"),
                    data.get("badge_mac"),
                    data.get("violation_type", "MISSING_HELMET"),
                    data.get("compliance_ratio"),
                    data.get("snapshot_path"),
                    int(data.get("interlock_issued", False)),
                    0,
                    data.get("created_at", _utc_now()),
                ),
            )
            self._conn.commit()
        return incident_id

    def resolve_incident(
        self,
        incident_id: str,
        reset_by: str = "manager",
    ) -> bool:
        now = _utc_now()
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE incidents
                SET resolved = 1,
                    interlock_reset_at = ?,
                    interlock_reset_by = ?
                WHERE incident_id = ?
                """,
                (now, reset_by, incident_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def list_incidents(
        self,
        device_id: str | None = None,
        resolved: bool | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM incidents WHERE 1=1"
        params: list[Any] = []
        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)
        if resolved is not None:
            query += " AND resolved = ?"
            params.append(int(resolved))
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return self._rows_to_list(rows)

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        return self._row_to_dict(row)

    def mark_incident_interlock_issued(self, incident_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET interlock_issued = 1 WHERE incident_id = ?",
                (incident_id,),
            )
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Worker Badges
    # ------------------------------------------------------------------ #
    def upsert_worker_badge(self, data: dict[str, Any]) -> dict[str, Any]:
        badge_mac = data["badge_mac"]
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO worker_badges
                    (badge_mac, worker_id, worker_name, department, active, registered_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(badge_mac) DO UPDATE SET
                    worker_id   = excluded.worker_id,
                    worker_name = excluded.worker_name,
                    department  = excluded.department,
                    active      = excluded.active
                """,
                (
                    badge_mac,
                    data["worker_id"],
                    data.get("worker_name"),
                    data.get("department"),
                    int(data.get("active", True)),
                    _utc_now(),
                ),
            )
            self._conn.commit()
        return self.get_worker_badge(badge_mac) or data

    def get_worker_badge(self, badge_mac: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM worker_badges WHERE badge_mac = ?", (badge_mac,)
            ).fetchone()
        return self._row_to_dict(row)

    def list_worker_badges(self, active_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM worker_badges"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY registered_at DESC"
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return self._rows_to_list(rows)

    # ------------------------------------------------------------------ #
    # Breach Events
    # ------------------------------------------------------------------ #
    def insert_breach_event(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO breach_events
                    (device_id, worker_id, badge_mac, rssi_raw, rssi_smoothed,
                     distance_est_m, ts)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    data.get("device_id", "unknown"),
                    data.get("worker_id"),
                    data.get("badge_mac"),
                    data.get("rssi_raw"),
                    data.get("rssi_smoothed"),
                    data.get("distance_est_m"),
                    data.get("timestamp", _utc_now()),
                ),
            )
            self._conn.commit()

    def get_recent_breaches(
        self,
        device_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM breach_events
                WHERE device_id = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return self._rows_to_list(rows)

    # ------------------------------------------------------------------ #
    # Interlock Log
    # ------------------------------------------------------------------ #
    def log_interlock(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO interlock_log
                    (device_id, command, source, reason, worker_id, issued_by, ts)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    data.get("device_id", "unknown"),
                    data.get("command", "LOCKOUT"),
                    data.get("source"),
                    data.get("reason"),
                    data.get("worker_id"),
                    data.get("issued_by", "system"),
                    data.get("timestamp", _utc_now()),
                ),
            )
            self._conn.commit()

    def get_interlock_history(
        self,
        device_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM interlock_log
                WHERE device_id = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return self._rows_to_list(rows)

    # ------------------------------------------------------------------ #
    # ML Calibration / Model Package
    # ------------------------------------------------------------------ #
    def get_model_package(
        self,
        machine_id: str,
        device_id: str,
    ) -> dict[str, Any] | None:
        """Return the latest calibrated model package for a device."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM calibrations
                WHERE machine_id = ? AND device_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (machine_id, device_id),
            ).fetchone()
        return self._row_to_dict(row)

    def save_model_package(
        self,
        machine_id: str,
        device_id: str,
        package: dict[str, Any],
        baseline_stats: dict[str, Any] | None = None,
        quality: float | None = None,
        window_count: int | None = None,
    ) -> None:
        """Persist a trained model package (IsolationForest-distilled)."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO calibrations
                    (machine_id, device_id, model_package, baseline_stats,
                     quality, window_count, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    machine_id,
                    device_id,
                    json.dumps(package),
                    json.dumps(baseline_stats) if baseline_stats else None,
                    quality,
                    window_count,
                    _utc_now(),
                ),
            )
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Anomaly Log
    # ------------------------------------------------------------------ #
    def record_anomaly(
        self,
        machine_id: str,
        device_id: str,
        score: float,
        threshold: float,
        is_anomaly: bool,
    ) -> None:
        """Record one ML anomaly scoring result."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO anomaly_log
                    (machine_id, device_id, score, threshold, is_anomaly, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    machine_id,
                    device_id,
                    float(score),
                    float(threshold),
                    int(bool(is_anomaly)),
                    _utc_now(),
                ),
            )
            self._conn.commit()

    def get_recent_anomalies(
        self,
        machine_id: str,
        device_id: str,
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return recent anomaly records for a device within a time window."""
        since = _utc_now()  # placeholder; we filter by id DESC instead of time
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM anomaly_log
                WHERE machine_id = ? AND device_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (machine_id, device_id, limit),
            ).fetchall()
        return self._rows_to_list(rows)
