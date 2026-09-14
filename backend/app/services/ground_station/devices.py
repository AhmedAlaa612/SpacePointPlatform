"""Device registry + the Redis-backed pending-command queue.

No new `ground_station_commands` table: a queued command is just a JSON blob
pushed onto a per-device Redis list until the on-site agent pops it — one
more instance of "an ordered list of events" that doesn't need its own
schema (see models/ground_station/__init__.py). If Redis is unreachable the
command never gets queued and the caller gets a 503, rather than silently
losing it as a fire-and-forget broadcast would (unlike telemetry, a lost
command is a real operational miss, not just a stale UI).
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ground_station.device import GroundStationDevice


@dataclass
class GroundStationAttemptRow:
    attempt_id: uuid.UUID
    user_id: uuid.UUID | None
    team_id: uuid.UUID | None
    status: str
    started_at: datetime | None
    owner_label: str
    device_id: uuid.UUID | None
    device_status: str | None
    device_last_seen_at: datetime | None

_PENDING_KEY_PREFIX = "ground-station:device:"
_PENDING_KEY_SUFFIX = ":commands:pending"


def _pending_key(device_id: str) -> str:
    return f"{_PENDING_KEY_PREFIX}{device_id}{_PENDING_KEY_SUFFIX}"


async def get_device(db: AsyncSession, device_id: uuid.UUID) -> GroundStationDevice | None:
    return (await db.execute(
        select(GroundStationDevice).where(GroundStationDevice.id == device_id)
    )).scalars().first()


async def get_or_create_device_for_attempt(
    db: AsyncSession, *, mission_attempt_id: uuid.UUID, label: str,
) -> GroundStationDevice:
    """One rig per mission attempt — created lazily the first time the
    student opens their console, not at attempt-start, so starting the
    mission never fails even if this insert briefly races another request
    for the same attempt (unique constraint on mission_attempt_id makes a
    duplicate insert a clean re-fetch, not a 500)."""
    existing = (await db.execute(
        select(GroundStationDevice).where(GroundStationDevice.mission_attempt_id == mission_attempt_id)
    )).scalars().first()
    if existing is not None:
        return existing
    device = GroundStationDevice(id=uuid.uuid4(), label=label, mission_attempt_id=mission_attempt_id, status="offline")
    db.add(device)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return (await db.execute(
            select(GroundStationDevice).where(GroundStationDevice.mission_attempt_id == mission_attempt_id)
        )).scalars().one()
    return device


async def register_device(db: AsyncSession, *, label: str) -> GroundStationDevice:
    """Staff-only, for a shared/orphan rig with no student owner (a demo
    booth kit, say) — most devices are provisioned automatically per
    mission attempt instead (`get_or_create_device_for_attempt`)."""
    device = GroundStationDevice(id=uuid.uuid4(), label=label, status="offline")
    db.add(device)
    await db.flush()
    return device


async def touch_last_seen(db: AsyncSession, device: GroundStationDevice) -> None:
    device.status = "online"
    device.last_seen_at = datetime.now(timezone.utc)
    await db.flush()


async def queue_command(client: redis.Redis, device_id: str, *, command_id: str, name: str, arg: str | None) -> None:
    payload = {
        "id": command_id, "name": name, "arg": arg,
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    await client.rpush(_pending_key(device_id), json.dumps(payload))


async def pop_pending_commands(client: redis.Redis, device_id: str, *, limit: int = 20) -> list[dict]:
    """The agent's poll target — drains up to `limit` queued commands in
    the order they were sent."""
    out: list[dict] = []
    for _ in range(limit):
        raw = await client.lpop(_pending_key(device_id))
        if raw is None:
            break
        out.append(json.loads(raw))
    return out


async def list_ground_station_attempts(db: AsyncSession) -> list["GroundStationAttemptRow"]:
    """The ops monitoring list — every ground_station mission attempt with
    its owner (solo student or team) and rig status, newest first."""
    from app.models.missions.mission import Mission, MissionAttempt
    from app.models.team import Team
    from app.models.user import User

    rows = (await db.execute(
        select(
            MissionAttempt.id, MissionAttempt.user_id, MissionAttempt.team_id,
            MissionAttempt.status, MissionAttempt.started_at,
            User.full_name, Team.name,
            GroundStationDevice.id, GroundStationDevice.status, GroundStationDevice.last_seen_at,
        )
        .select_from(MissionAttempt)
        .join(Mission, Mission.id == MissionAttempt.mission_id)
        .outerjoin(User, User.id == MissionAttempt.user_id)
        .outerjoin(Team, Team.id == MissionAttempt.team_id)
        .outerjoin(GroundStationDevice, GroundStationDevice.mission_attempt_id == MissionAttempt.id)
        .where(Mission.kind == "ground_station")
        .order_by(MissionAttempt.started_at.desc())
    )).all()
    return [
        GroundStationAttemptRow(
            attempt_id=r[0], user_id=r[1], team_id=r[2], status=r[3], started_at=r[4],
            owner_label=r[6] or r[5] or "Unknown",
            device_id=r[7], device_status=r[8], device_last_seen_at=r[9],
        )
        for r in rows
    ]
