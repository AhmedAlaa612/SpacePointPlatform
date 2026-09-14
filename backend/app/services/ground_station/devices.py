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
import secrets
import uuid
from datetime import datetime, timezone

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.models.ground_station.device import GroundStationDevice

_PENDING_KEY_PREFIX = "ground-station:device:"
_PENDING_KEY_SUFFIX = ":commands:pending"


def _pending_key(device_id: str) -> str:
    return f"{_PENDING_KEY_PREFIX}{device_id}{_PENDING_KEY_SUFFIX}"


async def get_device(db: AsyncSession, device_id: uuid.UUID) -> GroundStationDevice | None:
    return (await db.execute(
        select(GroundStationDevice).where(GroundStationDevice.id == device_id)
    )).scalars().first()


async def register_device(db: AsyncSession, *, label: str) -> tuple[GroundStationDevice, str]:
    """Returns (device, plaintext secret) — the plaintext is shown once and
    never recoverable again, same posture as any other credential issuance
    in this codebase."""
    secret = secrets.token_urlsafe(32)
    device = GroundStationDevice(
        id=uuid.uuid4(), label=label, secret_hash=get_password_hash(secret), status="offline",
    )
    db.add(device)
    await db.flush()
    return device, secret


async def rotate_secret(db: AsyncSession, device: GroundStationDevice) -> str:
    secret = secrets.token_urlsafe(32)
    device.secret_hash = get_password_hash(secret)
    await db.flush()
    return secret


def verify_device_secret(device: GroundStationDevice, secret: str) -> bool:
    return verify_password(secret, device.secret_hash)


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
