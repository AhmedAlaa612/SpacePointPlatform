"""7B-7 (Missions Phase 2B, 2026-08-12) — mission_stats: rolls up every
attempt at one mission per student, mission-wide (not cohort-scoped), using
the shared best_attempt rule. Redis-free, HTTP-free.
"""

import uuid

import pytest

from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember, MissionVariant
from app.models.missions.team import MissionTeam
from app.models.user import User
from app.services.missions.stats import mission_stats


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Stats User", email=f"stats-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _mission(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Stats Mission", slug=f"stats-mission-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=20)
    db.add(variant)
    await db.flush()
    return mission, variant


@pytest.mark.asyncio
async def test_mission_stats_is_empty_with_no_attempts(db):
    author = await _user(db, roles=["operations"])
    mission, _ = await _mission(db, author=author)
    stats = await mission_stats(db, mission_id=mission.id)
    assert stats == {
        "mission_id": mission.id, "total_attempts": 0, "total_students": 0,
        "passed_students": 0, "pass_rate": 0, "rows": [],
    }


@pytest.mark.asyncio
async def test_mission_stats_rolls_up_solo_and_team_attempts_with_pass_rate(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission(db, author=author)

    solo_student = await _user(db)
    db.add(MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=solo_student.id,
        attempt_no=1, status="failed", payload={},
    ))
    db.add(MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=solo_student.id,
        attempt_no=2, status="passed", score=95, payload={},
    ))

    team_member = await _user(db)
    team = MissionTeam(id=uuid.uuid4(), name="Stats Team")
    db.add(team)
    await db.flush()
    team_attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, mission_team_id=team.id,
        attempt_no=1, status="submitted", payload={},
    )
    db.add(team_attempt)
    await db.flush()
    db.add(MissionAttemptMember(attempt_id=team_attempt.id, user_id=team_member.id))
    await db.flush()

    stats = await mission_stats(db, mission_id=mission.id)
    assert stats["total_attempts"] == 3
    assert stats["total_students"] == 2
    assert stats["passed_students"] == 1
    assert stats["pass_rate"] == 50

    rows_by_user = {r["user_id"]: r for r in stats["rows"]}
    assert rows_by_user[solo_student.id]["status"] == "passed"
    assert rows_by_user[solo_student.id]["attempt_no"] == 2
    assert rows_by_user[team_member.id]["status"] == "submitted"
