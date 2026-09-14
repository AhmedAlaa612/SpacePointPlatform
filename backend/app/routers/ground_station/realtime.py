"""Ground Station live WS — `/ws/ground-station/{device_id}`, structured
exactly like `routers/games/realtime.py::game_run_socket`. Any logged-in
user may connect — this is a tool, not a graded/gated mission."""

import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError

from app.core.dependencies import get_ws_user
from app.models.user import User
from app.services.ground_station.realtime import decr_active_connections, device_channel, get_realtime_redis, incr_active_connections

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws/ground-station", tags=["ground-station-realtime"])


async def _forward_redis_to_ws(pubsub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        await websocket.send_text(message["data"])


async def _drain_client_messages(websocket: WebSocket) -> None:
    while True:
        await websocket.receive_text()


@router.websocket("/{device_id}")
async def ground_station_socket(websocket: WebSocket, device_id: str, user: User | None = Depends(get_ws_user)):
    if user is None:
        await websocket.close(code=1008)
        return

    redis_client = get_realtime_redis()
    pubsub = redis_client.pubsub()
    try:
        await pubsub.subscribe(device_channel(device_id))
    except RedisError:
        logger.warning("Ground Station: Redis unreachable, closing device %s socket", device_id, exc_info=True)
        await websocket.close(code=1011)
        await redis_client.aclose()
        return

    await websocket.accept()
    await incr_active_connections(redis_client, device_id)
    forward_task = asyncio.create_task(_forward_redis_to_ws(pubsub, websocket))
    drain_task = asyncio.create_task(_drain_client_messages(websocket))
    try:
        await asyncio.wait([forward_task, drain_task], return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        drain_task.cancel()
        await pubsub.unsubscribe()
        await pubsub.aclose()
        await decr_active_connections(redis_client, device_id)
        await redis_client.aclose()
