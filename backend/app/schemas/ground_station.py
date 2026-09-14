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

    model_config = {"from_attributes": True}


class DeviceRegisterIn(BaseModel):
    label: str


class DeviceRegisterOut(BaseModel):
    device: DeviceOut
    # Shown once, at registration/rotation time only — goes into the agent's
    # local .env, never stored or logged in plaintext again.
    secret: str


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
