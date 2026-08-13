"""Operate mission schemas (Operate v2, Stage 7C) — `/missions/operate/*`.

Three payload shapes, one per surface:

* `OperateStateOut` — the live console. One `GET` drives the whole page, the
  same "one fetch, one render" posture `DesignStateOut` already uses.
* `BriefingOut` — read before you fly. Served without an attempt existing,
  so opening it never burns a retry.
* `DebriefOut` — the replay. Served from the frozen trace once the flight
  is decided.

`telemetry` is deliberately an open dict rather than a fixed model. The
channel list is authored in `services/missions/operate/telemetry.py:CHANNELS`
alongside its nominal ranges, and pinning every channel a second time here
would mean a new readout could only be added by editing two files that must
agree — exactly the kind of drift the v1 port shipped (its `TelemetryOut`
declared `solar_current`, which the simulator never actually set).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class CommandEventOut(BaseModel):
    seq: int
    command: str
    arg: str = ""
    sim_t: float = 0.0
    issued_by: UUID
    success: bool
    message: str
    at: datetime


class SpacecraftLogOut(BaseModel):
    """An event the *spacecraft* reported on its own — eclipse entry, AOS,
    a fault detection firing. Distinct from the command transcript above,
    and the student's primary alert channel. This is SatKit's `mission_logs`
    surface, which the v1 port dropped entirely."""

    t: float
    level: str  # INFO | WARNING | ERROR
    message: str


class OrbitPhaseOut(BaseModel):
    orbit_number: int
    orbit_fraction: float
    label: str
    sunlit: bool
    in_pass: bool
    in_saa: bool
    elevation_deg: float
    seconds_to_next_aos: float
    seconds_to_los: float
    seconds_to_eclipse: float
    seconds_to_sunrise: float


class SubsystemRowOut(BaseModel):
    key: str
    label: str
    value: Any
    unit: str
    status: str  # nominal | warn | alarm


class SubsystemCardOut(BaseModel):
    subsystem: str
    title: str
    status: str  # nominal | warning | critical | off
    rows: list[SubsystemRowOut]


class AnomalyStateOut(BaseModel):
    key: str
    title: str
    subsystem: str
    origin: str  # injected | emergent
    raised_t: float
    cleared_t: float | None = None
    outcome: str
    # `action` and the correct command are deliberately omitted while the
    # flight is live — the Ops Handbook is where a student looks up a
    # response, and how much it tells them is the variant's difficulty
    # setting. The debrief returns everything.


class ObjectiveOut(BaseModel):
    key: str
    label: str
    detail: str
    target: float
    actual: float
    fraction: float
    met: bool


class CrewMemberOut(BaseModel):
    user_id: UUID
    name: str
    role: str | None = None


class OperateStateOut(BaseModel):
    attempt_id: UUID
    mission_id: UUID
    variant_id: UUID
    variant_label: str
    attempt_status: str

    # flight clock
    sim_t: float
    session_seconds: float
    time_compression: float
    expired: bool
    phase: OrbitPhaseOut
    orbit: dict

    telemetry: dict
    subsystems: list[SubsystemCardOut]
    events: list[CommandEventOut]
    spacecraft_log: list[SpacecraftLogOut]
    anomalies: list[AnomalyStateOut]

    objectives: list[ObjectiveOut]
    score: float
    objectives_score: float
    performance_score: float
    penalty_points: float
    pass_threshold: float

    is_team: bool = False
    crew: dict[str, str] = {}
    roster: list[CrewMemberOut] = []

    # Stage 7C-9 — non-empty when this flight's vehicle came from the
    # student's own passed design attempt. One line per parameter that
    # their design decided, so they can see what they're living with.
    spacecraft_source: list[str] = []


class BriefingOut(BaseModel):
    mission_id: UUID
    mission_title: str
    mission_summary: str | None = None
    variant_id: UUID
    variant_label: str
    points: int
    pass_threshold: float
    orbit: dict
    spacecraft: dict
    objectives: list[dict]
    flight_rules: list[dict]
    commands: list[dict]
    handbook: list[dict]
    crew_roles: list[dict]
    assumptions: list[str]


class HandbookOut(BaseModel):
    """Fetched once when the console mounts, not on every 2-second poll —
    it's static for the life of the attempt."""

    disclosure: str
    entries: list[dict]
    commands: list[dict]
    flight_rules: list[dict]
    crew_roles: list[dict]
    assumptions: list[str]


class DebriefOut(BaseModel):
    attempt_id: UUID
    mission_id: UUID
    variant_label: str
    attempt_status: str
    passed: bool
    score: float
    pass_threshold: float
    objectives_score: float
    performance_score: float
    penalty_points: float
    objectives: list[ObjectiveOut]
    penalties: list[dict]
    timeline: dict
    trace: list[dict]
    command_markers: list[dict]
    anomaly_windows: list[dict]
    report: dict
    events: list[CommandEventOut]
    spacecraft_log: list[SpacecraftLogOut]


class AssignCrewRoleIn(BaseModel):
    role: str | None = None  # None clears whatever role the caller holds


class IssueCommandIn(BaseModel):
    command: str


class IssueCommandOut(BaseModel):
    event: CommandEventOut
    state: OperateStateOut


class FinishOperationOut(BaseModel):
    passed: bool
    score: float
    state: OperateStateOut
