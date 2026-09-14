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
