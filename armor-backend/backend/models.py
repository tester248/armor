"""
ARMOR – Pydantic Data Models
----------------------------
Defines strict schemas for all payloads per:
ARMOR_System_Architecture_and_Implementation_Plan.md (Section 5)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional, Union
from pydantic import BaseModel, Field, field_validator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# 5.1 Telemetry Models
# ─────────────────────────────────────────────────────────────────────────────
class VibrationPayload(BaseModel):
    accel_x: Optional[float] = Field(default=None, description="ADXL345 X-axis acceleration (g)")
    accel_y: Optional[float] = Field(default=None, description="ADXL345 Y-axis acceleration (g)")
    accel_z: Optional[float] = Field(default=None, description="ADXL345 Z-axis acceleration (g)")
    rms: Optional[float] = Field(default=None, description="Root Mean Square vibration magnitude")
    crest_factor: Optional[float] = Field(default=None, description="Peak / RMS ratio")


class PowerPayload(BaseModel):
    voltage_v: Optional[float] = Field(default=None, description="INA219 bus voltage (V)")
    current_ma: Optional[float] = Field(default=None, description="INA219 armature current (mA)")
    power_mw: Optional[float] = Field(default=None, description="INA219 power consumption (mW)")


class TelemetryIngestRequest(BaseModel):
    """
    Topic: armor/{device_id}/telemetry
    HTTP:  POST /api/v1/telemetry
    """
    device_id: str = Field(default="machino_node_01", description="Identifier of the machine ESP32")
    timestamp: Union[datetime, int, float, str] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    motor_state: str = Field(default="RUNNING", description="RUNNING | IDLE | LOCKED | ANOMALY")
    vibration: Optional[VibrationPayload] = None
    power: Optional[PowerPayload] = None
    temperature_c: Optional[float] = Field(default=None, description="DS18B20 surface temperature (°C)")

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Union[datetime, int, float, str]) -> datetime:
        if isinstance(v, datetime):
            return v
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc)
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                return datetime.fromtimestamp(float(v), tz=timezone.utc)
        return datetime.now(timezone.utc)

    def flat_acc_mag(self) -> float:
        """Compute acceleration magnitude sqrt(x^2 + y^2 + z^2) if RMS is absent."""
        if self.vibration:
            x = self.vibration.accel_x or 0.0
            y = self.vibration.accel_y or 0.0
            z = self.vibration.accel_z or 0.0
            return math.sqrt(x * x + y * y + z * z)
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 5.2 Proximity Breach Event Model
# ─────────────────────────────────────────────────────────────────────────────
class ProximityBreachEvent(BaseModel):
    """
    Topic: armor/gateway/breach
    HTTP:  POST /api/v1/breach
    Triggered when worker enters the 1.5m danger perimeter.
    """
    device_id: str = Field(default="machino_node_01", description="Machine cell breached")
    worker_id: str = Field(..., description="ID broadcast by ESP32 badge")
    badge_mac: str = Field(..., description="MAC address of ESP32 badge")
    rssi_raw: Optional[float] = Field(default=None, description="Raw RSSI signal strength")
    rssi_smoothed: Optional[float] = Field(default=None, description="EMA-filtered RSSI")
    distance_est_m: Optional[float] = Field(default=1.2, description="Estimated distance in meters")
    timestamp: Union[datetime, int, float, str, None] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5.3 Emergency Interlock Command Model
# ─────────────────────────────────────────────────────────────────────────────
class InterlockCommand(BaseModel):
    """
    Topic: armor/{device_id}/interlock
    HTTP:  POST /api/v1/interlock
    Payload sent to machine ESP32 to actuate L298N Enable pin.
    """
    command: str = Field(..., description="LOCKOUT | RESET")
    source: str = Field(default="VISION_AI_PIPELINE", description="Source triggering action")
    reason: Optional[str] = Field(default=None, description="Explanation for interlock actuation")
    worker_id: Optional[str] = Field(default=None, description="Worker associated with breach")
    issued_by: Optional[str] = Field(default="system", description="User or service issuing command")
    timestamp: Union[datetime, int, float, str, None] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Worker Badge Registry Model
# ─────────────────────────────────────────────────────────────────────────────
class WorkerBadge(BaseModel):
    """
    HTTP: POST /api/v1/workers
    Registration record for an authorized ESP32 Smart Badge.
    """
    badge_mac: str = Field(..., description="ESP32 hardware MAC address (e.g. 24:6F:28:AB:C1:02)")
    worker_id: str = Field(..., description="Assigned badge ID (e.g. WORKER_EMP_402)")
    worker_name: Optional[str] = Field(default=None, description="Full name of worker")
    department: Optional[str] = Field(default="Fabrication", description="Department / Zone")
    active: bool = Field(default=True, description="Whether badge is currently active")
