"""Live games — real-time transport (Live Games Phase 2C, 8-5, D7).

WebSocket + Redis pub/sub, not an in-process broadcast dict: the app runs
a single API process today, but building the fan-out on Redis from day
one avoids a transport rewrite the moment that stops being true (D7,
confirmed via a startup/deployment check — Redis is already deployed,
backing the existing ARQ queue). Every connection for a run (the
instructor's, every student's) subscribes to the same Redis channel,
regardless of which API process handled their WS handshake.

Publishing is call-and-forget from here — this file has no game-state
opinions of its own. `publish_to_run`/`publish_to_participant` are what
every later task calls the moment something happens: 8-6 scoring, 8-7's
instructor console (start/restart/end), 8-8's student flow, 8-9's
reversal mechanics.

Message envelope: `{"type": ..., "payload": {...}}`. `MessageType` is
the seven types this stage's endpoint contract commits to (all
server → client): `question_started`, `answer_ack` (private — see
`participant_channel`), `leaderboard_update`, `question_added`,
`question_deleted`, `game_restarted`, `game_ended`.

Uses a dedicated `redis.asyncio.Redis` connection, not `app.state.arq_redis`
— `.pubsub()` puts a connection into subscriber mode, and the ARQ pool is
tuned/timed-out for job-queue traffic, not held open per WS connection.
"""

import json
from typing import Literal

import redis.asyncio as redis

from app.core.config import settings

MessageType = Literal[
    "question_started", "answer_ack", "leaderboard_update",
    "question_added", "question_deleted", "game_restarted", "game_ended",
]


def run_channel(run_id: str) -> str:
    return f"games:run:{run_id}"


def participant_channel(run_id: str, user_id: str) -> str:
    """answer_ack is one student's own result — published here, never to
    the shared run channel every other connection is subscribed to."""
    return f"games:run:{run_id}:user:{user_id}"


def get_realtime_redis(url: str | None = None) -> redis.Redis:
    return redis.from_url(url or settings.REDIS_URL, decode_responses=True)


async def publish_to_run(client: redis.Redis, run_id: str, type: MessageType, payload: dict) -> None:
    await client.publish(run_channel(run_id), json.dumps({"type": type, "payload": payload}))


async def publish_to_participant(client: redis.Redis, run_id: str, user_id: str, type: MessageType, payload: dict) -> None:
    await client.publish(participant_channel(run_id, user_id), json.dumps({"type": type, "payload": payload}))
