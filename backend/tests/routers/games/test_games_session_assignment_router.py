"""Live Games Phase 2C, 8-4 — per-session assignment + snapshot copy
(D11, D12): `/games/sessions/*`. Redis-free (uses the `client` fixture).
"""

import uuid
from datetime import date

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.games.game import Game, GameQuestion
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Games Session User", email=f"gs-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _session(db) -> Session:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="P",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(session)
    await db.flush()
    return session


async def _game_with_questions(db, *, author, count=2) -> Game:
    game = Game(id=uuid.uuid4(), title="Transfer Orbits", created_by=author.id)
    db.add(game)
    await db.flush()
    for i in range(1, count + 1):
        db.add(GameQuestion(
            id=uuid.uuid4(), game_id=game.id, position=i, prompt=f"Q{i}",
            points_mode="double" if i == 1 else "normal",
            options=[{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}],
        ))
    await db.flush()
    return game


@pytest.mark.asyncio
async def test_assigning_a_game_snapshots_its_questions(db, client):
    ops = await _user(db)
    session = await _session(db)
    game = await _game_with_questions(db, author=ops, count=2)
    await db.commit()

    resp = await client.post(
        f"/games/sessions/{session.id}/assignments", headers=_headers(ops),
        json={"game_id": str(game.id), "instructor_note": "Run after the orbits module"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["game_title"] == "Transfer Orbits"
    assert body["instructor_note"] == "Run after the orbits module"
    assert body["time_limit_seconds"] == 20
    assert body["floor_pct"] == 25
    assert body["blackout_count"] == 3
    assert body["question_count"] == 2
    assert [q["prompt"] for q in body["questions"]] == ["Q1", "Q2"]
    assert body["questions"][0]["max_points"] == 200  # double
    assert body["questions"][1]["max_points"] == 100  # normal


@pytest.mark.asyncio
async def test_editing_the_snapshot_never_touches_the_template(db, client):
    ops = await _user(db)
    session = await _session(db)
    game = await _game_with_questions(db, author=ops, count=1)
    await db.commit()

    created = await client.post(
        f"/games/sessions/{session.id}/assignments", headers=_headers(ops),
        json={"game_id": str(game.id)},
    )
    assignment_id = created.json()["id"]
    snapshot_question_id = created.json()["questions"][0]["id"]

    # Edit the assignment's own copy.
    edited = await client.patch(
        f"/games/sessions/questions/{snapshot_question_id}", headers=_headers(ops),
        json={"prompt": "Edited in this session only"},
    )
    assert edited.status_code == 200, edited.text

    # Template's own question is untouched.
    template = await client.get(f"/games/admin/{game.id}", headers=_headers(ops))
    assert template.json()["questions"][0]["prompt"] == "Q1"

    # Assignment's copy reflects the edit.
    refreshed = await client.get(f"/games/sessions/assignments/{assignment_id}", headers=_headers(ops))
    assert refreshed.json()["questions"][0]["prompt"] == "Edited in this session only"


@pytest.mark.asyncio
async def test_one_session_can_hold_multiple_assignments(db, client):
    ops = await _user(db)
    session = await _session(db)
    game_a = await _game_with_questions(db, author=ops, count=1)
    game_b = await _game_with_questions(db, author=ops, count=1)
    await db.commit()

    await client.post(f"/games/sessions/{session.id}/assignments", headers=_headers(ops), json={"game_id": str(game_a.id)})
    await client.post(f"/games/sessions/{session.id}/assignments", headers=_headers(ops), json={"game_id": str(game_b.id)})

    listed = await client.get(f"/games/sessions/{session.id}/assignments", headers=_headers(ops))
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 2

    # The template can still be assigned to another session too.
    other_session = await _session(db)
    await db.commit()
    again = await client.post(
        f"/games/sessions/{other_session.id}/assignments", headers=_headers(ops), json={"game_id": str(game_a.id)},
    )
    assert again.status_code == 201, again.text


@pytest.mark.asyncio
async def test_assignment_config_is_independently_editable(db, client):
    ops = await _user(db)
    session = await _session(db)
    game = await _game_with_questions(db, author=ops, count=1)
    await db.commit()

    created = await client.post(f"/games/sessions/{session.id}/assignments", headers=_headers(ops), json={"game_id": str(game.id)})
    assignment_id = created.json()["id"]

    updated = await client.patch(
        f"/games/sessions/assignments/{assignment_id}", headers=_headers(ops),
        json={"time_limit_seconds": 45, "blackout_count": 1},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["time_limit_seconds"] == 45
    assert updated.json()["blackout_count"] == 1
    assert updated.json()["floor_pct"] == 25  # untouched field stays put

    # Game's own defaults are unaffected.
    template = await client.get(f"/games/admin/{game.id}", headers=_headers(ops))
    assert template.json()["default_time_limit_seconds"] == 20


@pytest.mark.asyncio
async def test_add_and_delete_question_on_the_snapshot(db, client):
    ops = await _user(db)
    session = await _session(db)
    game = await _game_with_questions(db, author=ops, count=1)
    await db.commit()

    created = await client.post(f"/games/sessions/{session.id}/assignments", headers=_headers(ops), json={"game_id": str(game.id)})
    assignment_id = created.json()["id"]

    added = await client.post(
        f"/games/sessions/assignments/{assignment_id}/questions", headers=_headers(ops),
        json={"prompt": "Extra question", "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]},
    )
    assert added.status_code == 201, added.text
    assert added.json()["position"] == 2

    detail = await client.get(f"/games/sessions/assignments/{assignment_id}", headers=_headers(ops))
    assert detail.json()["question_count"] == 2

    deleted = await client.delete(f"/games/sessions/questions/{added.json()['id']}", headers=_headers(ops))
    assert deleted.status_code == http_status.HTTP_204_NO_CONTENT

    after = await client.get(f"/games/sessions/assignments/{assignment_id}", headers=_headers(ops))
    assert after.json()["question_count"] == 1


@pytest.mark.asyncio
async def test_deleting_the_assignment_leaves_the_template_intact(db, client):
    ops = await _user(db)
    session = await _session(db)
    game = await _game_with_questions(db, author=ops, count=1)
    await db.commit()

    created = await client.post(f"/games/sessions/{session.id}/assignments", headers=_headers(ops), json={"game_id": str(game.id)})
    assignment_id = created.json()["id"]

    deleted = await client.delete(f"/games/sessions/assignments/{assignment_id}", headers=_headers(ops))
    assert deleted.status_code == http_status.HTTP_204_NO_CONTENT

    gone = await client.get(f"/games/sessions/assignments/{assignment_id}", headers=_headers(ops))
    assert gone.status_code == http_status.HTTP_404_NOT_FOUND

    template_still_there = await client.get(f"/games/admin/{game.id}", headers=_headers(ops))
    assert template_still_there.status_code == 200


@pytest.mark.asyncio
async def test_assignment_routes_require_content_role(db, client):
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    session = await _session(db)
    await db.commit()

    forbidden = await client.get(f"/games/sessions/{session.id}/assignments", headers=_headers(student))
    assert forbidden.status_code == http_status.HTTP_403_FORBIDDEN

    ok = await client.get(f"/games/sessions/{session.id}/assignments", headers=_headers(ops))
    assert ok.status_code == 200
