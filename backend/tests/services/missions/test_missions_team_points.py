"""P6-3 (LMS Phase 2 Stage 6, 2026-08-11) — per-member point awards and
team-aware embedded-item completion. Redis-free, HTTP-free.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.lms import Course, CourseModule, Enrollment, ItemProgress, ModuleItem, PointEvent
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User
from app.services.missions import decide_attempt, start_attempt
from app.services.teams import create_team


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Team Points User", email=f"tp-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _mission_with_variant(db, *, author, points=40) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Team Points Mission", slug=f"team-points-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy="team",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=points)
    db.add(variant)
    await db.flush()
    return mission, variant


async def _points_total(db, user_id) -> int:
    rows = (await db.execute(select(PointEvent.points).where(PointEvent.user_id == user_id))).scalars().all()
    return sum(rows)


@pytest.mark.asyncio
async def test_passing_team_attempt_awards_every_member_individually(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author, points=30)
    alice = await _user(db)
    bob = await _user(db)
    team = await create_team(db, name="Points Team", created_by=alice.id, member_ids=[bob.id])

    attempt = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)

    assert await _points_total(db, alice.id) == 30
    assert await _points_total(db, bob.id) == 30


@pytest.mark.asyncio
async def test_team_point_events_carry_the_team_id_in_ref(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author)
    alice = await _user(db)
    team = await create_team(db, name="Ref Team", created_by=alice.id)

    attempt = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)

    event = (await db.execute(select(PointEvent).where(PointEvent.user_id == alice.id))).scalars().first()
    assert event.ref["team_id"] == str(team.id)
    assert event.ref["attempt_id"] == str(attempt.id)


@pytest.mark.asyncio
async def test_a_member_on_two_teams_only_earns_the_same_variant_once(db):
    """Idempotency is per (user, mission, variant) regardless of which team
    earned it — the same rule that stops a solo student double-farming a
    replayed variant applies across teams too."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author, points=25)
    alice = await _user(db)
    bob = await _user(db)
    carol = await _user(db)
    team_1 = await create_team(db, name="Team One", created_by=alice.id, member_ids=[bob.id])
    team_2 = await create_team(db, name="Team Two", created_by=alice.id, member_ids=[carol.id])

    attempt_1 = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team_1.id)
    await decide_attempt(db, attempt=attempt_1, passed=True, score=90)
    attempt_2 = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team_2.id)
    await decide_attempt(db, attempt=attempt_2, passed=True, score=90)

    assert await _points_total(db, alice.id) == 25  # on both teams, only earned once
    assert await _points_total(db, bob.id) == 25
    assert await _points_total(db, carol.id) == 25


@pytest.mark.asyncio
async def test_failing_a_team_attempt_awards_no_one(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author)
    alice = await _user(db)
    bob = await _user(db)
    team = await create_team(db, name="Failing Team", created_by=alice.id, member_ids=[bob.id])

    attempt = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)
    await decide_attempt(db, attempt=attempt, passed=False)

    assert await _points_total(db, alice.id) == 0
    assert await _points_total(db, bob.id) == 0


# ── team-aware embedding (the P6-2 edge case) ───────────────────────────────

async def _course_with_mission_item(db, *, author, mission_id) -> tuple[Course, ModuleItem]:
    course = Course(id=uuid.uuid4(), title="Team Embedding Course", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(
        id=uuid.uuid4(), module_id=module.id, position=1, kind="mission",
        content={"mission_id": str(mission_id)},
    )
    db.add(item)
    await db.flush()
    return course, item


@pytest.mark.asyncio
async def test_team_mission_completes_the_item_only_for_enrolled_members(db):
    """MISSIONS_REPORT.md P6-2 edge case: a team mission embedded in a
    course completes for N students at once, but a member may not be
    enrolled in the embedding course — write ItemProgress only for members
    with an active enrollment; the others still get their attempt and points."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author)
    course, item = await _course_with_mission_item(db, author=author, mission_id=mission.id)
    alice = await _user(db)
    bob = await _user(db)  # never enrolled in `course`
    db.add(Enrollment(id=uuid.uuid4(), user_id=alice.id, course_id=course.id, source="self"))
    await db.flush()
    team = await create_team(db, name="Embedding Team", created_by=alice.id, member_ids=[bob.id])

    attempt = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)

    alice_row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == alice.id, ItemProgress.item_id == item.id)
    )).scalars().first()
    bob_row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == bob.id, ItemProgress.item_id == item.id)
    )).scalars().first()

    assert alice_row is not None and alice_row.status == "completed"
    assert bob_row is None  # never enrolled — no ItemProgress row at all

    # Bob still keeps his attempt record and his points.
    assert await _points_total(db, bob.id) == variant.points
