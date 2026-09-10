"""Manual team management (2026-08-26) — `/competitions/admin/cohorts/{id}/teams`
and `/competitions/admin/teams/{id}/*`: the ops-facing complement to Roster
import, for one-off corrections (a late signup, a team split, someone
switching teams) without re-uploading a whole sheet.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.competitions.judging import CompetitionScore
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.team import Team
from app.models.user import User
from app.services.competitions.judging import upsert_rubric
from app.services.teams import create_team


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Teams Test Ops", email=f"teamops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db, name="Existing Student") -> User:
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"teamstu-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _program_and_cohort(db) -> tuple[Program, Cohort]:
    program = Program(
        id=uuid.uuid4(), code=f"RUYA-{uuid.uuid4().hex[:8]}", name="Ru'ya Space Race",
        program_type="competition", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Qualifier", status="running")
    db.add(cohort)
    await db.flush()
    return program, cohort


@pytest.mark.asyncio
async def test_ops_creates_an_empty_team_and_is_not_a_member_of_it(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/teams", headers=_headers(ops), json={"name": "Falcon Eye"},
    )
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["name"] == "Falcon Eye"
    assert body["member_ids"] == []


@pytest.mark.asyncio
async def test_ops_adds_an_existing_user_and_registers_a_new_one(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    existing = await _student(db, "Amir Salem")
    await db.commit()

    team = await create_team(db, name="Silent Comet", created_by=ops.id, cohort_id=cohort.id, member_ids=[])
    await db.commit()
    # create_team always adds created_by too — undo that so this test starts
    # from a genuinely empty team, matching what the create-team endpoint gives.
    from app.services.teams import leave_team
    await leave_team(db, team_id=team.id, user_id=ops.id)
    await db.commit()

    added_existing = await client.post(
        f"/competitions/admin/teams/{team.id}/members", headers=_headers(ops), json={"user_id": str(existing.id)},
    )
    assert added_existing.status_code == 201, added_existing.text
    assert str(existing.id) in added_existing.json()["member_ids"]

    new_email = f"newmember-{uuid.uuid4().hex[:6]}@example.com"
    added_new = await client.post(
        f"/competitions/admin/teams/{team.id}/members", headers=_headers(ops),
        json={"full_name": "Lina Nasser", "email": new_email},
    )
    assert added_new.status_code == 201, added_new.text
    body = added_new.json()
    assert "Lina Nasser" in body["member_names"]
    assert len(body["member_ids"]) == 2

    new_user = (await db.execute(select(User).where(User.email == new_email))).scalars().first()
    assert new_user is not None and "student" in new_user.role_values


@pytest.mark.asyncio
async def test_ops_adding_a_new_member_enqueues_a_ticket_email(db, arq_client, arq_redis):
    """Manually adding a brand-new person to a competition team should send
    a ticket the same way registration does — one `send_ticket_email` job
    per newly-registered member, not zero."""
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    team = await create_team(db, name="Rogue One", created_by=ops.id, cohort_id=cohort.id, member_ids=[])
    await db.commit()
    from app.services.teams import leave_team
    await leave_team(db, team_id=team.id, user_id=ops.id)
    await db.commit()

    new_email = f"ticketmember-{uuid.uuid4().hex[:6]}@example.com"
    resp = await arq_client.post(
        f"/competitions/admin/teams/{team.id}/members", headers=_headers(ops),
        json={"full_name": "Noor Hadid", "email": new_email},
    )
    assert resp.status_code == 201, resp.text

    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 1


@pytest.mark.asyncio
async def test_ops_can_opt_a_new_member_out_of_the_ticket_and_welcome_emails(db, arq_client, arq_redis, monkeypatch):
    """`send_ticket_email: false` skips the queued job entirely, and
    `send_welcome_email: false` still creates the account (team membership
    needs a real user_id) but skips the "Your SpacePoint learning account"
    notification — same opt-out shape as desk registration's flags."""
    sent_welcome_emails = []

    async def _fake_send_set_password_email(user, *, purpose="welcome"):
        sent_welcome_emails.append(user.email)
        return True

    monkeypatch.setattr(
        "app.services.lms.ops_integration.send_set_password_email", _fake_send_set_password_email,
    )

    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    team = await create_team(db, name="Quiet Comet", created_by=ops.id, cohort_id=cohort.id, member_ids=[])
    await db.commit()
    from app.services.teams import leave_team
    await leave_team(db, team_id=team.id, user_id=ops.id)
    await db.commit()

    new_email = f"noemails-{uuid.uuid4().hex[:6]}@example.com"
    resp = await arq_client.post(
        f"/competitions/admin/teams/{team.id}/members", headers=_headers(ops),
        json={
            "full_name": "Sami Rasheed", "email": new_email,
            "send_ticket_email": False, "send_welcome_email": False,
        },
    )
    assert resp.status_code == 201, resp.text

    assert await arq_redis.zrange("arq:queue", 0, -1) == []
    assert sent_welcome_emails == []

    new_user = (await db.execute(select(User).where(User.email == new_email))).scalars().first()
    assert new_user is not None and "student" in new_user.role_values


@pytest.mark.asyncio
async def test_ops_renames_a_team_and_removes_a_member(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    student = await _student(db)
    await db.commit()
    team = await create_team(db, name="Old Name", created_by=student.id, cohort_id=cohort.id, member_ids=[student.id])
    await db.commit()

    renamed = await client.patch(
        f"/competitions/admin/teams/{team.id}", headers=_headers(ops), json={"name": "New Name"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "New Name"

    removed = await client.delete(
        f"/competitions/admin/teams/{team.id}/members/{student.id}", headers=_headers(ops),
    )
    assert removed.status_code == http_status.HTTP_204_NO_CONTENT

    remaining = await client.get(f"/competitions/admin/cohorts/{cohort.id}/teams", headers=_headers(ops))
    team_row = next(t for t in remaining.json() if t["id"] == str(team.id))
    assert team_row["member_ids"] == []


@pytest.mark.asyncio
async def test_ops_deletes_an_unscored_team_but_not_a_scored_one(db, client):
    ops = await _ops(db)
    program, cohort = await _program_and_cohort(db)
    student = await _student(db)
    scored_student = await _student(db, "Scored Student")
    await db.commit()

    rubric, _criteria = await upsert_rubric(
        db, program_id=program.id, name="Test Rubric",
        criteria=[{"key": "design", "label": "Design", "max_points": 10}],
    )
    await db.commit()

    empty_team = await create_team(db, name="Disposable", created_by=student.id, cohort_id=cohort.id, member_ids=[])
    scored_team = await create_team(
        db, name="Already Judged", created_by=scored_student.id, cohort_id=cohort.id, member_ids=[scored_student.id],
    )
    await db.commit()
    db.add(CompetitionScore(
        id=uuid.uuid4(), rubric_id=rubric.id, team_id=scored_team.id, judge_user_id=ops.id, cohort_id=cohort.id,
        criterion_scores={}, bonus_points=0, total_points=0,
    ))
    await db.commit()

    ok = await client.delete(f"/competitions/admin/teams/{empty_team.id}", headers=_headers(ops))
    assert ok.status_code == http_status.HTTP_204_NO_CONTENT

    blocked = await client.delete(f"/competitions/admin/teams/{scored_team.id}", headers=_headers(ops))
    assert blocked.status_code == http_status.HTTP_400_BAD_REQUEST

    still_there = (await db.execute(select(Team).where(Team.id == scored_team.id))).scalars().first()
    assert still_there is not None
