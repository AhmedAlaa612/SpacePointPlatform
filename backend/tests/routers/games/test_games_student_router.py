"""Live Games Phase 2C, 8-8 — student join/play flow: `/games/play/*`
(D9, D10, D18). Redis-free (uses the `client` fixture) except the one
test that verifies the private answer_ack broadcast.
"""

import uuid
from datetime import date

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.games.game import Game
from app.models.games.run import GameRun
from app.models.games.session_assignment import GameSessionAssignment, GameSessionQuestion
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.games.realtime import participant_channel, run_channel
from app.services.games.runs import create_run, join_run, start_run


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _student_with_registration(db, *, cohort_id=None, nickname=None) -> User:
    contact = Contact(id=uuid.uuid4(), full_name="Play Test Student")
    db.add(contact)
    await db.flush()
    if cohort_id is not None:
        registration = Registration(
            id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort_id, status="registered",
            ticket_token=uuid.uuid4().hex, registered_via="desk",
        )
        db.add(registration)
    student = User(
        id=uuid.uuid4(), full_name="Play Test Student", email=f"play-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id, nickname=nickname,
    )
    db.add(student)
    await db.flush()
    return student


async def _assignment_with_questions(db, *, count=2, floor_pct=25, time_limit=20, blackout_count=1):
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
    return assignment, cohort


@pytest.mark.asyncio
async def test_joinable_lists_only_runs_for_the_students_own_cohort(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=1)
    student = await _student_with_registration(db, cohort_id=cohort.id)
    outsider = await _student_with_registration(db)  # no registration anywhere
    await db.flush()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await db.commit()

    mine = await client.get("/games/play/joinable", headers=_headers(student))
    assert mine.status_code == 200, mine.text
    assert any(r["run_id"] == str(run.id) for r in mine.json())

    theirs = await client.get("/games/play/joinable", headers=_headers(outsider))
    assert theirs.json() == []


@pytest.mark.asyncio
async def test_join_then_answer_awards_points_matching_the_formula(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=1, floor_pct=25, time_limit=20)
    student = await _student_with_registration(db, cohort_id=cohort.id, nickname="PlayerOne1")
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await start_run(db, run=run)
    await db.commit()

    joined = await client.post(f"/games/play/runs/{run.id}/join", headers=_headers(student), json={})
    assert joined.status_code == 201, joined.text
    assert joined.json()["nickname"] == "PlayerOne1"

    q = await client.get(f"/games/play/runs/{run.id}/question", headers=_headers(student))
    assert q.status_code == 200, q.text
    assert all("is_correct" not in o for o in q.json()["options"])  # never leaked to the student

    ans = await client.post(
        f"/games/play/runs/{run.id}/answer", headers=_headers(student),
        json={"selected_option_index": 0, "elapsed_seconds": 0},
    )
    assert ans.status_code == 200, ans.text
    body = ans.json()
    assert body["is_correct"] is True
    assert body["points_awarded"] == 100  # normal, instant
    assert body["base_points"] == 25
    assert body["speed_bonus"] == 75
    assert body["streak"] == 1

    score = await client.get(f"/games/play/runs/{run.id}/my-score", headers=_headers(student))
    assert score.json() == {"score": 100, "streak": 1}


@pytest.mark.asyncio
async def test_must_join_before_answering(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=1)
    student = await _student_with_registration(db, cohort_id=cohort.id)
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await start_run(db, run=run)
    await db.commit()

    forbidden = await client.post(
        f"/games/play/runs/{run.id}/answer", headers=_headers(student),
        json={"selected_option_index": 0, "elapsed_seconds": 1},
    )
    assert forbidden.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_leaderboard_is_redacted_to_own_score_only_during_blackout(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=1, blackout_count=1)  # instantly in blackout
    alice = await _student_with_registration(db, cohort_id=cohort.id, nickname="Alice1")
    bob = await _student_with_registration(db, cohort_id=cohort.id, nickname="Bob2")
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=alice.id)
    await join_run(db, run=run, user=alice)
    await join_run(db, run=run, user=bob)
    await start_run(db, run=run)
    await db.commit()

    board = await client.get(f"/games/play/runs/{run.id}/leaderboard", headers=_headers(alice))
    assert board.status_code == 200, board.text
    rows = board.json()
    assert len(rows) == 1
    assert rows[0]["is_me"] is True
    assert rows[0]["nickname"] == "Alice1"


@pytest.mark.asyncio
async def test_leaderboard_unlocks_fully_once_the_run_ends_even_after_a_blackout(db, client):
    """8-8b's podium relies on this: is_blackout_active requires a live
    current question, so ending the run (current_question_position ->
    None) clears the redaction automatically — the same endpoint that
    hid everyone else during blackout now returns the full board."""
    assignment, cohort = await _assignment_with_questions(db, count=1, blackout_count=1)
    alice = await _student_with_registration(db, cohort_id=cohort.id, nickname="Alice1")
    bob = await _student_with_registration(db, cohort_id=cohort.id, nickname="Bob2")
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=alice.id)
    await join_run(db, run=run, user=alice)
    await join_run(db, run=run, user=bob)
    await start_run(db, run=run)
    await db.commit()

    from app.services.games.runs import end_run
    await end_run(db, run=run)
    await db.commit()

    board = await client.get(f"/games/play/runs/{run.id}/leaderboard", headers=_headers(alice))
    assert board.status_code == 200, board.text
    nicknames = {row["nickname"] for row in board.json()}
    assert nicknames == {"Alice1", "Bob2"}


@pytest.mark.asyncio
async def test_late_join_sees_current_question_no_catchup_score(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=2)
    late = await _student_with_registration(db, cohort_id=cohort.id, nickname="LateJoiner1")
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=late.id)
    await start_run(db, run=run)
    from app.services.games.runs import advance_run
    await advance_run(db, run=run)  # now on question 2, without this student ever answering Q1
    await db.commit()

    await client.post(f"/games/play/runs/{run.id}/join", headers=_headers(late), json={})
    q = await client.get(f"/games/play/runs/{run.id}/question", headers=_headers(late))
    assert q.json()["position"] == 2

    score = await client.get(f"/games/play/runs/{run.id}/my-score", headers=_headers(late))
    assert score.json()["score"] == 0  # nothing retroactive for the missed Q1


@pytest.mark.asyncio
async def test_answer_ack_broadcasts_privately_to_the_participant(db, realtime_client, realtime_redis):
    assignment, cohort = await _assignment_with_questions(db, count=1)
    student = await _student_with_registration(db, cohort_id=cohort.id)
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await start_run(db, run=run)
    await db.commit()
    await realtime_client.post(f"/games/play/runs/{run.id}/join", headers=_headers(student), json={})

    pubsub = realtime_redis.pubsub()
    await pubsub.subscribe(participant_channel(str(run.id), str(student.id)))
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)

    resp = await realtime_client.post(
        f"/games/play/runs/{run.id}/answer", headers=_headers(student),
        json={"selected_option_index": 0, "elapsed_seconds": 0},
    )
    assert resp.status_code == 200

    msg = None
    for _ in range(5):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        if msg is not None:
            break
    assert msg is not None
    import json
    body = json.loads(msg["data"])
    assert body["type"] == "answer_ack"
    assert body["payload"]["is_correct"] is True
    await pubsub.aclose()


@pytest.mark.asyncio
async def test_join_broadcasts_participant_joined_on_the_run_channel(db, realtime_client, realtime_redis):
    assignment, cohort = await _assignment_with_questions(db, count=1)
    student = await _student_with_registration(db, cohort_id=cohort.id, nickname="Joiner1")
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await db.commit()

    pubsub = realtime_redis.pubsub()
    await pubsub.subscribe(run_channel(str(run.id)))
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)

    resp = await realtime_client.post(f"/games/play/runs/{run.id}/join", headers=_headers(student), json={})
    assert resp.status_code == 201, resp.text

    import json
    msg = None
    for _ in range(5):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        if msg is not None:
            break
    assert msg is not None
    body = json.loads(msg["data"])
    assert body["type"] == "participant_joined"
    assert body["payload"]["nickname"] == "Joiner1"
    await pubsub.aclose()


@pytest.mark.asyncio
async def test_update_my_profile_changes_nickname_and_avatar_in_lobby(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=1)
    student = await _student_with_registration(db, cohort_id=cohort.id, nickname="Default1")
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await db.commit()
    await client.post(f"/games/play/runs/{run.id}/join", headers=_headers(student), json={})

    resp = await client.patch(
        f"/games/play/runs/{run.id}/me", headers=_headers(student),
        json={"nickname": "CustomCallsign", "avatar": "rocket"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["nickname"] == "CustomCallsign"
    assert resp.json()["avatar"] == "rocket"

    roster = await client.get(f"/games/play/runs/{run.id}/roster", headers=_headers(student))
    assert roster.status_code == 200, roster.text
    assert roster.json()[0]["nickname"] == "CustomCallsign"


@pytest.mark.asyncio
async def test_update_my_profile_rejects_unknown_avatar_preset(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=1)
    student = await _student_with_registration(db, cohort_id=cohort.id)
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await db.commit()
    await client.post(f"/games/play/runs/{run.id}/join", headers=_headers(student), json={})

    resp = await client.patch(
        f"/games/play/runs/{run.id}/me", headers=_headers(student),
        json={"nickname": "Whatever", "avatar": "not-a-real-preset"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_my_profile_locked_once_the_run_is_live(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=1)
    student = await _student_with_registration(db, cohort_id=cohort.id)
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await db.commit()
    await client.post(f"/games/play/runs/{run.id}/join", headers=_headers(student), json={})
    await start_run(db, run=run)
    await db.commit()

    resp = await client.patch(
        f"/games/play/runs/{run.id}/me", headers=_headers(student),
        json={"nickname": "TooLate", "avatar": None},
    )
    assert resp.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_student_roster_requires_having_joined(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=1)
    student = await _student_with_registration(db, cohort_id=cohort.id)
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await db.commit()

    resp = await client.get(f"/games/play/runs/{run.id}/roster", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_student_roster_lists_everyone_redacted(db, client):
    assignment, cohort = await _assignment_with_questions(db, count=1)
    alice = await _student_with_registration(db, cohort_id=cohort.id, nickname="Alice1")
    bob = await _student_with_registration(db, cohort_id=cohort.id, nickname="Bob2")
    await db.commit()
    run = await create_run(db, assignment=assignment, actor_id=alice.id)
    await db.commit()
    await client.post(f"/games/play/runs/{run.id}/join", headers=_headers(alice), json={})
    await client.post(f"/games/play/runs/{run.id}/join", headers=_headers(bob), json={})

    resp = await client.get(f"/games/play/runs/{run.id}/roster", headers=_headers(alice))
    assert resp.status_code == 200, resp.text
    nicknames = {row["nickname"] for row in resp.json()}
    assert nicknames == {"Alice1", "Bob2"}
    assert all("real_name" not in row for row in resp.json())
