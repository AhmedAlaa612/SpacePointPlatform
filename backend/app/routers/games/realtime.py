"""Live games — the real-time WebSocket endpoint (Live Games Phase 2C,
8-5, D7): `/ws/games/runs/{run_id}`.

This endpoint's job stops at "authenticate, subscribe, forward" — it has
no game-state opinions. Later tasks (8-6 scoring, 8-7 instructor console,
8-8 student flow, 8-9 reversal) call `publish_to_run`/`publish_to_participant`
(`services/games/realtime.py`) from their own HTTP handlers or service
code the moment something happens; every open connection for that run —
instructor and every student, regardless of which API process accepted
their handshake — receives it over Redis pub/sub, not polling.

Incoming client messages aren't dispatched into game logic yet (no
`GameRun`/`GameParticipant` schema exists until 8-6) — the receive loop
exists to detect disconnects and keep the connection's two directions
running concurrently; 8-7/8-8 replace the discard with real handling
(answer submission, instructor actions) once there's a run to act on.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError

from app.core.dependencies import get_ws_user
from app.models.user import User
from app.services.games.realtime import get_realtime_redis, participant_channel, run_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws/games", tags=["games-realtime"])


async def _forward_redis_to_ws(pubsub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        await websocket.send_text(message["data"])


async def _drain_client_messages(websocket: WebSocket) -> None:
    while True:
        await websocket.receive_text()


@router.websocket("/runs/{run_id}")
async def game_run_socket(websocket: WebSocket, run_id: str, user: User | None = Depends(get_ws_user)):
    if user is None:
        await websocket.close(code=1008)
        return

    redis_client = get_realtime_redis()
    pubsub = redis_client.pubsub()
    try:
        await pubsub.subscribe(run_channel(run_id), participant_channel(run_id, str(user.id)))
    except RedisError:
        logger.warning("Live games: Redis unreachable, closing run %s socket", run_id, exc_info=True)
        await websocket.close(code=1011)
        await redis_client.close()
        return

    await websocket.accept()
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
        await redis_client.aclose()
