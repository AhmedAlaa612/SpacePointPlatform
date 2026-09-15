"""Ground Station — request/response shapes for `/ground-station/*`."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

DeviceStatus = Literal["online", "offline"]


class DeviceOut(BaseModel):
    id: UUID
    label: str
    status: DeviceStatus
    last_seen_at: datetime | None
    mission_attempt_id: UUID | None = None

    model_config = {"from_attributes": True}


class DeviceRegisterIn(BaseModel):
    label: str


class AttemptDeviceOut(BaseModel):
    """A ground_station mission attempt's own rig — team/solo view, with
    the plain device id being the whole "credential" now (no auth on
    ingest, see routers/ground_station/deps.py)."""
    device: DeviceOut
    ingest_base_url: str


class AttemptCompleteOut(BaseModel):
    attempt_id: UUID
    status: str
    decided_at: datetime | None


class GroundStationAttemptSummary(BaseModel):
    """The ops monitoring list — every ground_station attempt with its
    owner and rig status, one row per team/solo run."""
    attempt_id: UUID
    owner_label: str
    team_id: UUID | None
    user_id: UUID | None
    status: str
    started_at: datetime | None
    device_id: UUID | None
    device_status: DeviceStatus | None
    device_last_seen_at: datetime | None


class TelemetryFrameIn(BaseModel):
    """One reading from the rig. Shape intentionally loose (`data`) — this
    mirrors the legacy app's own telemetry payload, which varied by which
    subsystem sent it (CDHS housekeeping vs. ADCS attitude vs. GPS fix)."""
    data: dict[str, Any]
    recorded_at: datetime | None = None


class CommandIn(BaseModel):
    name: str
    arg: str | None = None


class CommandQueuedOut(BaseModel):
    id: str
    name: str
    arg: str | None
    queued_at: datetime


class PhotoOut(BaseModel):
    path: str
    url: str
    captured_at: datetime
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None


class TelemetryPointOut(BaseModel):
    recorded_at: datetime
    temp: float | None
    voltage: float | None
    current: float | None
    power: float | None
    rssi: float | None
    snr: float | None
    lat: float | None
    lon: float | None
    alt: float | None
    pitch: float | None
    roll: float | None
    yaw: float | None

    model_config = {"from_attributes": True}


class HistoryOut(BaseModel):
    device_id: UUID
    minutes: int
    count: int
    data: list[TelemetryPointOut]


class ThresholdsOut(BaseModel):
    device_id: UUID
    temp_max: float
    temp_min: float
    voltage_max: float
    voltage_min: float
    current_max: float
    power_max: float

    model_config = {"from_attributes": True}


class ThresholdsIn(BaseModel):
    temp_max: float | None = None
    temp_min: float | None = None
    voltage_max: float | None = None
    voltage_min: float | None = None
    current_max: float | None = None
    power_max: float | None = None


class AlertOut(BaseModel):
    id: UUID
    device_id: UUID
    occurred_at: datetime
    alert_type: str
    threshold: float
    current_value: float
    severity: str
    acknowledged: bool

    model_config = {"from_attributes": True}


class DeviceStatsOut(BaseModel):
    device_id: UUID
    packets_received: int
    first_seen: datetime | None
    last_seen: datetime | None
    active_connections: int
