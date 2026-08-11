"""Operate mission schemas (Phase 2B, Stage 7B-3) — `/missions/operate/*`.

One `GET .../attempts/{attempt_id}` returns everything the live console
needs: current telemetry, the full command log, and the anomaly/score
state — same "one fetch drives the whole page" shape the design mission's
`DesignStateOut` already uses.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TelemetryOut(BaseModel):
    pitch: float
    roll: float
    yaw: float
    battery_voltage: float
    battery_current: float
    battery_percentage: int
    panel_temp: float
    system_temp: float
    solar_current: float
    imu_x: float
    imu_y: float
    imu_z: float
    reaction_wheel_speed: float
    signal_strength: float
    humidity: float
    light: float


class CommandEventOut(BaseModel):
    seq: int
    command: str
    issued_by: UUID
    success: bool
    message: str
    at: datetime


class AnomalyStateOut(BaseModel):
    index: int
    subsystem: str
    triggered: bool
    resolved: bool
    # correct_command is deliberately omitted — the fix is the puzzle,
    # same answer-leakage posture as every other verifier's student view.


class OperateStateOut(BaseModel):
    attempt_id: UUID
    mission_id: UUID
    variant_id: UUID
    variant_label: str
    attempt_status: str
    elapsed_seconds: float
    telemetry: TelemetryOut
    events: list[CommandEventOut]
    anomalies: list[AnomalyStateOut]
    score: float
    triggered_count: int
    resolved_count: int
    pass_threshold: float


class IssueCommandIn(BaseModel):
    command: str


class IssueCommandOut(BaseModel):
    event: CommandEventOut
    state: OperateStateOut


class FinishOperationOut(BaseModel):
    passed: bool
    score: float
    state: OperateStateOut
