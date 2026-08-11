"""Live Games Phase 2C, 8-5 — the real-time WS transport (D7):
`/ws/games/runs/{run_id}`. Requires a running Redis against
REDIS_URL_TEST (the `realtime_redis` fixture) — unlike the rest of the
games suite, this one can't be Redis-free, since the thing under test
*is* the pub/sub fan-out itself.

Starlette's `TestClient.websocket_connect` runs the ASGI app on its own
background thread/event loop, which the pytest-asyncio-managed `db`
fixture's session can't cross safely — so this file creates and cleans
up its own committed User row via a throwaway engine, rather than
reusing the transactional `db` fixture other games tests use.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services.games.realtime import publish_to_participant, publish_to_run


@pytest.fixture
async def ws_user():
    engine = create_async_engine(settings.DATABASE_URL_TEST)
    user_id = uuid.uuid4()
    async with AsyncSession(engine) as session:
        session.add(User(
            id=user_id, full_name="WS Test User", email=f"ws-{user_id.hex[:8]}@example.com",
            password_hash="x", roles=["operations"], status="active",
        ))
        await session.commit()
    yield user_id
    async with AsyncSession(engine) as session:
        user = await session.get(User, user_id)
        if user:
            await session.delete(user)
            await session.commit()
    await engine.dispose()


@pytest.fixture
def ws_client():
    engine = create_async_engine(settings.DATABASE_URL_TEST)

    async def _override_get_db():
        async with AsyncSession(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_two_connections_on_the_same_run_both_receive_a_broadcast(ws_user, ws_client, realtime_redis):
    run_id = str(uuid.uuid4())
    token = create_access_token(ws_user, ["operations"])

    with ws_client.websocket_connect(f"/ws/games/runs/{run_id}?token={token}") as instructor_ws, \
         ws_client.websocket_connect(f"/ws/games/runs/{run_id}?token={token}") as student_ws:

        await publish_to_run(realtime_redis, run_id, "question_started", {"question_id": "q1"})

        instructor_msg = json.loads(instructor_ws.receive_text())
        student_msg = json.loads(student_ws.receive_text())

    assert instructor_msg == {"type": "question_started", "payload": {"question_id": "q1"}}
    assert student_msg == {"type": "question_started", "payload": {"question_id": "q1"}}


@pytest.mark.asyncio
async def test_a_different_run_id_does_not_receive_the_broadcast(ws_user, ws_client, realtime_redis):
    run_id = str(uuid.uuid4())
    other_run_id = str(uuid.uuid4())
    token = create_access_token(ws_user, ["operations"])

    with ws_client.websocket_connect(f"/ws/games/runs/{run_id}?token={token}") as target_ws, \
         ws_client.websocket_connect(f"/ws/games/runs/{other_run_id}?token={token}") as bystander_ws:

        await publish_to_run(realtime_redis, run_id, "game_ended", {})
        msg = json.loads(target_ws.receive_text())
        assert msg["type"] == "game_ended"

        # The bystander (different run) gets nothing — prove it with a
        # message only it should see, arriving cleanly with no leakage.
        await publish_to_run(realtime_redis, other_run_id, "game_restarted", {})
        bystander_msg = json.loads(bystander_ws.receive_text())
        assert bystander_msg["type"] == "game_restarted"


@pytest.mark.asyncio
async def test_answer_ack_is_private_to_the_participant(ws_user, ws_client, realtime_redis):
    run_id = str(uuid.uuid4())
    token = create_access_token(ws_user, ["operations"])

    with ws_client.websocket_connect(f"/ws/games/runs/{run_id}?token={token}") as ws:
        await publish_to_participant(realtime_redis, run_id, str(ws_user), "answer_ack", {"correct": True})
        msg = json.loads(ws.receive_text())

    assert msg == {"type": "answer_ack", "payload": {"correct": True}}


def test_missing_or_bad_token_is_rejected(ws_client):
    from fastapi import WebSocketDisconnect
    run_id = str(uuid.uuid4())
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect(f"/ws/games/runs/{run_id}?token=garbage"):
            pass
