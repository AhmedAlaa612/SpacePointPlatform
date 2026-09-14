"""Ground Station real-time transport — WebSocket + Redis pub/sub, same
pattern as Live Games (`services/games/realtime.py`), reusing its
`get_realtime_redis()` directly rather than duplicating the connection
factory: it's already generic (any pub/sub channel name), not games-specific
in implementation.
"""

import json
import logging
from typing import Literal

import redis.asyncio as redis

from app.services.games.realtime import get_realtime_redis  # noqa: F401 — re-exported for routers

logger = logging.getLogger(__name__)

MessageType = Literal["telemetry_frame", "command_queued", "command_ack", "device_status", "photo_added"]


def device_channel(device_id: str) -> str:
    return f"ground-station:device:{device_id}"


def _connections_key(device_id: str) -> str:
    return f"ground-station:device:{device_id}:connections"


async def incr_active_connections(client: redis.Redis, device_id: str) -> None:
    await client.incr(_connections_key(device_id))


async def decr_active_connections(client: redis.Redis, device_id: str) -> None:
    remaining = await client.decr(_connections_key(device_id))
    if remaining <= 0:
        await client.delete(_connections_key(device_id))


async def active_connection_count(client: redis.Redis | None, device_id: str) -> int:
    """Live-viewer count — legacy's `active_connections` in `/api/stats`,
    scoped per device here since Live Games' Redis pool already gives every
    WS connection its own subscriber; this reuses the same connection for a
    simple counter rather than tracking sockets in-process (which wouldn't
    span multiple API workers)."""
    if client is None:
        return 0
    raw = await client.get(_connections_key(device_id))
    return int(raw) if raw else 0


async def publish_to_device(client: redis.Redis, device_id: str, type: MessageType, payload: dict) -> None:
    await client.publish(device_channel(device_id), json.dumps({"type": type, "payload": payload}))


async def safe_publish_to_device(client: redis.Redis | None, device_id: str, type: MessageType, payload: dict) -> None:
    """Never raises — a dropped broadcast must not undo the DB/queue state
    change that triggered it (same posture as Live Games' safe_publish_to_run)."""
    if client is None:
        logger.warning("Ground Station: no Redis connection, dropped %r broadcast for device %s", type, device_id)
        return
    try:
        await publish_to_device(client, device_id, type, payload)
    except Exception:
        logger.warning("Ground Station: broadcast failed for device %s", device_id, exc_info=True)
