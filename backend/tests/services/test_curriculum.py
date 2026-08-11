"""7B-2 (Missions Phase 2B, 2026-08-12) — unified course/mission prerequisite
DAG: evaluation (`prerequisite_status`/`is_unlocked`) and authoring
(`add_prerequisite`/`remove_prerequisite`). Supersedes the mission-only
`tests/services/missions/test_missions_prerequisites.py` — every scenario
there is covered here too, plus the course-involving edges D2 added.
Redis-free, HTTP-free.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.models.lms.course import Course, CourseModule, ModuleItem
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember, MissionVariant
from app.models.missions.team import MissionTeam
from app.models.user import User
from app.services.curriculum import add_prerequisite, is_unlocked, prerequisite_status, remove_prerequisite
from app.services.lms import item_progress
from app.services.missions import decide_attempt, start_attempt


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Curriculum User", email=f"cur-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _mission(db, *, author, title="Mission") -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title=title, slug=f"{title.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=20)
    db.add(variant)
    await db.flush()
    return mission, variant


async def _one_item_course(db, *, author, title="Course") -> tuple[Course, ModuleItem]:
    """A course with exactly one mandatory item — completing it completes
    the course, the simplest fixture that makes `course_completion` true."""
    course = Course(id=uuid.uuid4(), title=title, created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="text", content={"body": "x"})
    db.add(item)
    await db.flush()
    return course, item


# ── evaluation: mission-mission (mirrors the old mission-only test suite) ──

@pytest.mark.asyncio
async def test_a_mission_with_no_prerequisites_is_always_unlocked(db):
    author = await _user(db, roles=["operations"])
    mission, _ = await _mission(db, author=author)
    student = await _user(db)
    assert await is_unlocked(db, item_type="mission", item_id=mission.id, user_id=student.id) is True
    assert await prerequisite_status(db, item_type="mission", item_id=mission.id, user_id=student.id) == []


@pytest.mark.asyncio
async def test_mission_locked_until_prerequisite_mission_is_passed(db):
    author = await _user(db, roles=["operations"])
    basic, basic_variant = await _mission(db, author=author, title="Basic Radio")
    advanced, _ = await _mission(db, author=author, title="Advanced Radio")
    await add_prerequisite(db, item_type="mission", item_id=advanced.id, requires_type="mission", requires_id=basic.id)
    await db.flush()
    student = await _user(db)

    assert await is_unlocked(db, item_type="mission", item_id=advanced.id, user_id=student.id) is False
    status = await prerequisite_status(db, item_type="mission", item_id=advanced.id, user_id=student.id)
    assert status == [{"item_type": "mission", "item_id": basic.id, "title": "Basic Radio", "satisfied": False}]

    attempt = await start_attempt(db, user_id=student.id, mission_id=basic.id, variant_id=basic_variant.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)

    assert await is_unlocked(db, item_type="mission", item_id=advanced.id, user_id=student.id) is True
    status_after = await prerequisite_status(db, item_type="mission", item_id=advanced.id, user_id=student.id)
    assert status_after == [{"item_type": "mission", "item_id": basic.id, "title": "Basic Radio", "satisfied": True}]


@pytest.mark.asyncio
async def test_failing_the_prerequisite_does_not_unlock(db):
    author = await _user(db, roles=["operations"])
    basic, basic_variant = await _mission(db, author=author, title="Basic Wiring")
    advanced, _ = await _mission(db, author=author, title="Advanced Wiring")
    await add_prerequisite(db, item_type="mission", item_id=advanced.id, requires_type="mission", requires_id=basic.id)
    await db.flush()
    student = await _user(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=basic.id, variant_id=basic_variant.id)
    await decide_attempt(db, attempt=attempt, passed=False)

    assert await is_unlocked(db, item_type="mission", item_id=advanced.id, user_id=student.id) is False


@pytest.mark.asyncio
async def test_multiple_prerequisites_all_must_be_satisfied(db):
    author = await _user(db, roles=["operations"])
    a, a_variant = await _mission(db, author=author, title="Mission A")
    b, b_variant = await _mission(db, author=author, title="Mission B")
    c, _ = await _mission(db, author=author, title="Mission C")
    await add_prerequisite(db, item_type="mission", item_id=c.id, requires_type="mission", requires_id=a.id)
    await add_prerequisite(db, item_type="mission", item_id=c.id, requires_type="mission", requires_id=b.id)
    await db.flush()
    student = await _user(db)

    attempt_a = await start_attempt(db, user_id=student.id, mission_id=a.id, variant_id=a_variant.id)
    await decide_attempt(db, attempt=attempt_a, passed=True, score=90)
    assert await is_unlocked(db, item_type="mission", item_id=c.id, user_id=student.id) is False  # B still missing

    attempt_b = await start_attempt(db, user_id=student.id, mission_id=b.id, variant_id=b_variant.id)
    await decide_attempt(db, attempt=attempt_b, passed=True, score=90)
    assert await is_unlocked(db, item_type="mission", item_id=c.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_passing_any_variant_satisfies_the_prerequisite(db):
    author = await _user(db, roles=["operations"])
    basic, basic_variant = await _mission(db, author=author, title="Either Variant Basic")
    db.add(MissionVariant(id=uuid.uuid4(), mission_id=basic.id, label="Hard", position=2, points=50))
    advanced, _ = await _mission(db, author=author, title="Either Variant Advanced")
    await add_prerequisite(db, item_type="mission", item_id=advanced.id, requires_type="mission", requires_id=basic.id)
    await db.flush()
    student = await _user(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=basic.id, variant_id=basic_variant.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)

    assert await is_unlocked(db, item_type="mission", item_id=advanced.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_a_passing_team_attempt_satisfies_the_prerequisite_for_every_member(db):
    """A gap the old mission-only evaluator had: `passed_mission_ids` only
    checked `MissionAttempt.user_id`, so a mission passed as part of a team
    never unlocked anything for its members. Fixed while unifying (7B-2)."""
    author = await _user(db, roles=["operations"])
    basic, basic_variant = await _mission(db, author=author, title="Team Basic")
    advanced, _ = await _mission(db, author=author, title="Team Advanced")
    await add_prerequisite(db, item_type="mission", item_id=advanced.id, requires_type="mission", requires_id=basic.id)
    await db.flush()
    member = await _user(db)
    team = MissionTeam(id=uuid.uuid4(), name="Team Prereq")
    db.add(team)
    await db.flush()
    team_attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=basic.id, variant_id=basic_variant.id, mission_team_id=team.id,
        attempt_no=1, status="passed", score=90, payload={},
    )
    db.add(team_attempt)
    await db.flush()
    db.add(MissionAttemptMember(attempt_id=team_attempt.id, user_id=member.id))
    await db.flush()

    assert await is_unlocked(db, item_type="mission", item_id=advanced.id, user_id=member.id) is True


# ── evaluation: courses, and cross-type edges (D2) ──────────────────────────

@pytest.mark.asyncio
async def test_a_course_with_no_prerequisites_is_always_unlocked(db):
    author = await _user(db, roles=["operations"])
    course, _ = await _one_item_course(db, author=author)
    student = await _user(db)
    assert await is_unlocked(db, item_type="course", item_id=course.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_course_locked_until_prerequisite_course_is_completed(db):
    author = await _user(db, roles=["operations"])
    basic, basic_item = await _one_item_course(db, author=author, title="Basic Course")
    advanced, _ = await _one_item_course(db, author=author, title="Advanced Course")
    await add_prerequisite(db, item_type="course", item_id=advanced.id, requires_type="course", requires_id=basic.id)
    await db.flush()
    student = await _user(db)

    assert await is_unlocked(db, item_type="course", item_id=advanced.id, user_id=student.id) is False

    await item_progress(db, user_id=student.id, item_id=basic_item.id, action="text-viewed")

    assert await is_unlocked(db, item_type="course", item_id=advanced.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_mission_can_require_a_course_be_completed(db):
    author = await _user(db, roles=["operations"])
    course, item = await _one_item_course(db, author=author, title="Ground School")
    mission, _ = await _mission(db, author=author, title="Flight Test")
    await add_prerequisite(db, item_type="mission", item_id=mission.id, requires_type="course", requires_id=course.id)
    await db.flush()
    student = await _user(db)

    assert await is_unlocked(db, item_type="mission", item_id=mission.id, user_id=student.id) is False
    await item_progress(db, user_id=student.id, item_id=item.id, action="text-viewed")
    assert await is_unlocked(db, item_type="mission", item_id=mission.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_course_can_require_a_mission_be_passed(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission(db, author=author, title="Qualifier")
    course, _ = await _one_item_course(db, author=author, title="Advanced Track")
    await add_prerequisite(db, item_type="course", item_id=course.id, requires_type="mission", requires_id=mission.id)
    await db.flush()
    student = await _user(db)

    assert await is_unlocked(db, item_type="course", item_id=course.id, user_id=student.id) is False
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=100)
    assert await is_unlocked(db, item_type="course", item_id=course.id, user_id=student.id) is True


# ── authoring ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_prerequisite_rejects_self_reference(db):
    author = await _user(db, roles=["operations"])
    mission, _ = await _mission(db, author=author)
    with pytest.raises(HTTPException) as e:
        await add_prerequisite(db, item_type="mission", item_id=mission.id, requires_type="mission", requires_id=mission.id)
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_add_prerequisite_rejects_missing_item_or_requirement(db):
    author = await _user(db, roles=["operations"])
    mission, _ = await _mission(db, author=author)
    with pytest.raises(HTTPException) as e:
        await add_prerequisite(db, item_type="mission", item_id=uuid.uuid4(), requires_type="mission", requires_id=mission.id)
    assert e.value.status_code == 404

    with pytest.raises(HTTPException) as e:
        await add_prerequisite(db, item_type="mission", item_id=mission.id, requires_type="course", requires_id=uuid.uuid4())
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_add_prerequisite_rejects_duplicate(db):
    author = await _user(db, roles=["operations"])
    a, _ = await _mission(db, author=author, title="Dup A")
    b, _ = await _mission(db, author=author, title="Dup B")
    await add_prerequisite(db, item_type="mission", item_id=a.id, requires_type="mission", requires_id=b.id)
    await db.flush()
    with pytest.raises(HTTPException) as e:
        await add_prerequisite(db, item_type="mission", item_id=a.id, requires_type="mission", requires_id=b.id)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_remove_prerequisite_404s_when_no_such_edge(db):
    author = await _user(db, roles=["operations"])
    a, _ = await _mission(db, author=author)
    with pytest.raises(HTTPException) as e:
        await remove_prerequisite(db, item_type="mission", item_id=a.id, requires_type="mission", requires_id=uuid.uuid4())
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_add_then_remove_roundtrip_unlocks_again(db):
    author = await _user(db, roles=["operations"])
    a, _ = await _mission(db, author=author, title="Roundtrip A")
    b, _ = await _mission(db, author=author, title="Roundtrip B")
    await add_prerequisite(db, item_type="mission", item_id=a.id, requires_type="mission", requires_id=b.id)
    await db.flush()
    student = await _user(db)
    assert await is_unlocked(db, item_type="mission", item_id=a.id, user_id=student.id) is False

    await remove_prerequisite(db, item_type="mission", item_id=a.id, requires_type="mission", requires_id=b.id)
    await db.flush()
    assert await is_unlocked(db, item_type="mission", item_id=a.id, user_id=student.id) is True
