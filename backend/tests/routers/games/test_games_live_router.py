"""Live Games Phase 2C, 8-7 — instructor live console: `/games/live/*`
(D9, D10, D13's mid-game half, D15, D16, D17, D19). Most tests use the
Redis-free `client` fixture; a few specifically verify what actually
goes out over the wire and use `realtime_client` + `realtime_redis`.
"""

import json
import uuid
from datetime import date

import pytest
from fastapi import status as http_status

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.games.game import Game
from app.models.games.run import GameRun
from app.models.games.session_assignment import GameSessionAssignment, GameSessionQuestion
from app.models.lms.points import PointEvent
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.services.games.realtime import run_channel
from app.services.games.runs import get_current_question, join_run, start_run, submit_answer


async def _user(db, *, roles=None, nickname=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Real Name Person", email=f"live-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["instructor"], status="active", nickname=nickname,
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _assignment_with_questions(db, *, count=2, floor_pct=25, time_limit=20, blackout_count=1) -> GameSessionAssignment:
    ops = User(
        id=uuid.uuid4(), full_name="Ops", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(ops)
    await db.flush()
    game = Game(id=uuid.uuid4(), title="Transfer Orbits", created_by=ops.id)
    db.add(game)
    await db.flush()
    program = Program(id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="P", program_type="workshop", pricing_model="free", active=True)
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(session)
    await db.flush()
    assignment = GameSessionAssignment(
        id=uuid.uuid4(), session_id=session.id, game_id=game.id,
        time_limit_seconds=time_limit, floor_pct=floor_pct, blackout_count=blackout_count, assigned_by=ops.id,
    )
    db.add(assignment)
    await db.flush()
    for i in range(1, count + 1):
        db.add(GameSessionQuestion(
            id=uuid.uuid4(), assignment_id=assignment.id, position=i, prompt=f"Q{i}",
            options=[{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}],
        ))
    await db.flush()
    return assignment


@pytest.mark.asyncio
async def test_full_lifecycle_open_start_reveal_next_end(db, client):
    instructor = await _user(db)
    assignment = await _assignment_with_questions(db, count=2)
    await db.commit()

    opened = await client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    assert opened.status_code == 201, opened.text
    run_id = opened.json()["id"]
    assert opened.json()["status"] == "lobby"
    assert opened.json()["total_questions"] == 2

    started = await client.post(f"/games/live/runs/{run_id}/start", headers=_headers(instructor))
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "live"
    assert started.json()["current_question_position"] == 1

    full_q = await client.get(f"/games/live/runs/{run_id}/question", headers=_headers(instructor))
    assert full_q.status_code == 200
    assert any(o["is_correct"] for o in full_q.json()["options"])  # staff sees the answer key

    revealed = await client.post(f"/games/live/runs/{run_id}/reveal", headers=_headers(instructor))
    assert revealed.status_code == 200, revealed.text
    assert revealed.json()[0]["is_correct"] is True

    nxt = await client.post(f"/games/live/runs/{run_id}/next", headers=_headers(instructor))
    assert nxt.status_code == 200
    assert nxt.json()["current_question_position"] == 2

    await client.post(f"/games/live/runs/{run_id}/reveal", headers=_headers(instructor))
    ended = await client.post(f"/games/live/runs/{run_id}/next", headers=_headers(instructor))
    assert ended.json()["status"] == "ended"
    assert ended.json()["current_question_position"] is None


@pytest.mark.asyncio
async def test_end_button_ends_the_run_explicitly(db, client):
    instructor = await _user(db)
    assignment = await _assignment_with_questions(db, count=3)
    await db.commit()

    opened = await client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    run_id = opened.json()["id"]
    await client.post(f"/games/live/runs/{run_id}/start", headers=_headers(instructor))

    ended = await client.post(f"/games/live/runs/{run_id}/end", headers=_headers(instructor))
    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "ended"


@pytest.mark.asyncio
async def test_only_delivery_roles_may_run_a_game(db, client):
    instructor = await _user(db, roles=["instructor"])
    student = await _user(db, roles=["student"])
    assignment = await _assignment_with_questions(db, count=1)
    await db.commit()

    forbidden = await client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(student))
    assert forbidden.status_code == http_status.HTTP_403_FORBIDDEN

    ok = await client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_roster_shows_who_has_answered_the_current_question(db, client):
    instructor = await _user(db)
    alice = await _user(db, roles=["student"], nickname="AliceNick")
    bob = await _user(db, roles=["student"], nickname="BobNick")
    assignment = await _assignment_with_questions(db, count=1)
    await db.commit()

    run = await db.get(GameRun, uuid.UUID((
        await client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    ).json()["id"]))
    p_alice = await join_run(db, run=run, user=alice)
    await join_run(db, run=run, user=bob)
    await start_run(db, run=run)
    question = await get_current_question(db, run)
    await submit_answer(db, run=run, participant=p_alice, question=question, selected_option_index=0, elapsed_seconds=1)
    await db.commit()

    roster = await client.get(f"/games/live/runs/{run.id}/roster", headers=_headers(instructor))
    assert roster.status_code == 200, roster.text
    by_nick = {r["nickname"]: r["has_answered_current"] for r in roster.json()}
    assert by_nick["AliceNick"] is True
    assert by_nick["BobNick"] is False


@pytest.mark.asyncio
async def test_reveal_name_returns_the_real_name_never_broadcast(db, client):
    instructor = await _user(db)
    student = await _user(db, roles=["student"], nickname="SpaceOtter77")
    assignment = await _assignment_with_questions(db, count=1)
    await db.commit()

    run_resp = await client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    run = await db.get(GameRun, uuid.UUID(run_resp.json()["id"]))
    participant = await join_run(db, run=run, user=student)
    await db.commit()

    revealed = await client.get(
        f"/games/live/runs/{run.id}/participants/{participant.id}/reveal", headers=_headers(instructor),
    )
    assert revealed.status_code == 200, revealed.text
    assert revealed.json()["real_name"] == "Real Name Person"


@pytest.mark.asyncio
async def test_editing_or_reordering_a_question_is_blocked_while_live_but_add_delete_still_work(db, client):
    instructor = await _user(db)
    assignment = await _assignment_with_questions(db, count=2)
    await db.commit()

    opened = await client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    run_id = opened.json()["id"]

    questions = await client.get(f"/games/sessions/assignments/{assignment.id}", headers=_headers(instructor))
    q_ids = [q["id"] for q in questions.json()["questions"]]

    # Not live yet (lobby) — edit/reorder still allowed.
    still_lobby_edit = await client.patch(f"/games/sessions/questions/{q_ids[0]}", headers=_headers(instructor), json={"prompt": "Edited pre-start"})
    assert still_lobby_edit.status_code == 200, still_lobby_edit.text

    await client.post(f"/games/live/runs/{run_id}/start", headers=_headers(instructor))

    blocked_edit = await client.patch(f"/games/sessions/questions/{q_ids[0]}", headers=_headers(instructor), json={"prompt": "Nope"})
    assert blocked_edit.status_code == http_status.HTTP_409_CONFLICT

    blocked_reorder = await client.post(
        f"/games/sessions/assignments/{assignment.id}/questions/reorder", headers=_headers(instructor),
        json={"question_ids": list(reversed(q_ids))},
    )
    assert blocked_reorder.status_code == http_status.HTTP_409_CONFLICT

    added = await client.post(
        f"/games/sessions/assignments/{assignment.id}/questions", headers=_headers(instructor),
        json={"prompt": "Bonus Q", "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]},
    )
    assert added.status_code == 201, added.text  # add is still allowed live


@pytest.mark.asyncio
async def test_deleting_an_answered_question_mid_game_reverses_its_points(db, client):
    instructor = await _user(db)
    student = await _user(db, roles=["student"])
    assignment = await _assignment_with_questions(db, count=1)
    await db.commit()

    run_resp = await client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    run = await db.get(GameRun, uuid.UUID(run_resp.json()["id"]))
    participant = await join_run(db, run=run, user=student)
    await start_run(db, run=run)
    question = await get_current_question(db, run)
    answer = await submit_answer(db, run=run, participant=participant, question=question, selected_option_index=0, elapsed_seconds=0)
    await db.commit()
    assert answer.points_awarded == 100

    events_before = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert sum(e.points for e in events_before) == 100

    deleted = await client.delete(f"/games/sessions/questions/{question.id}", headers=_headers(instructor))
    assert deleted.status_code == http_status.HTTP_204_NO_CONTENT

    events_after = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert sum(e.points for e in events_after) == 0  # award + offsetting reversal net to zero
    assert len(events_after) == 2  # original row untouched, a new offsetting row added


@pytest.mark.asyncio
async def test_restart_reverses_all_points_and_starts_a_fresh_run(db, client):
    instructor = await _user(db)
    student = await _user(db, roles=["student"])
    assignment = await _assignment_with_questions(db, count=1)
    await db.commit()

    run_resp = await client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    run = await db.get(GameRun, uuid.UUID(run_resp.json()["id"]))
    participant = await join_run(db, run=run, user=student)
    await start_run(db, run=run)
    question = await get_current_question(db, run)
    await submit_answer(db, run=run, participant=participant, question=question, selected_option_index=0, elapsed_seconds=0)
    await db.commit()

    restarted = await client.post(f"/games/live/runs/{run.id}/restart", headers=_headers(instructor))
    assert restarted.status_code == 200, restarted.text
    new_run_id = restarted.json()["id"]
    assert new_run_id != str(run.id)
    assert restarted.json()["run_no"] == 2
    assert restarted.json()["status"] == "lobby"

    events = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert sum(e.points for e in events) == 0  # fully reversed


@pytest.mark.asyncio
async def test_question_started_broadcast_never_reveals_the_answer_key(db, realtime_client, realtime_redis):
    instructor = await _user(db)
    assignment = await _assignment_with_questions(db, count=1)
    await db.commit()

    opened = await realtime_client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    run_id = opened.json()["id"]

    pubsub = realtime_redis.pubsub()
    await pubsub.subscribe(run_channel(run_id))
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)  # drain subscribe ack, if any

    await realtime_client.post(f"/games/live/runs/{run_id}/start", headers=_headers(instructor))

    msg = None
    for _ in range(5):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        if msg is not None:
            break
    assert msg is not None, "expected a question_started broadcast"
    body = json.loads(msg["data"])
    assert body["type"] == "question_started"
    for opt in body["payload"]["options"]:
        assert "is_correct" not in opt
    await pubsub.aclose()


@pytest.mark.asyncio
async def test_leaderboard_broadcast_is_redacted_during_blackout(db, realtime_client, realtime_redis):
    instructor = await _user(db)
    assignment = await _assignment_with_questions(db, count=1, blackout_count=1)  # 1 question, 1 blackout -> instantly in blackout
    await db.commit()

    opened = await realtime_client.post(f"/games/live/assignments/{assignment.id}/runs", headers=_headers(instructor))
    run_id = opened.json()["id"]
    await realtime_client.post(f"/games/live/runs/{run_id}/start", headers=_headers(instructor))

    pubsub = realtime_redis.pubsub()
    await pubsub.subscribe(run_channel(run_id))
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)

    await realtime_client.post(f"/games/live/runs/{run_id}/reveal", headers=_headers(instructor))

    msg = None
    for _ in range(5):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        if msg is not None:
            break
    assert msg is not None
    body = json.loads(msg["data"])
    assert body["type"] == "leaderboard_update"
    assert body["payload"]["blackout"] is True
    assert "leaderboard" not in body["payload"]
    await pubsub.aclose()

    # Staff's own leaderboard fetch is unaffected by blackout.
    staff_board = await realtime_client.get(f"/games/live/runs/{run_id}/leaderboard", headers=_headers(instructor))
    assert staff_board.status_code == 200
