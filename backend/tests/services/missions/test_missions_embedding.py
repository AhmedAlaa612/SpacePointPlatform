"""P5-5 (LMS Phase 2 Stage 5, 2026-08-11) — module_items.kind='mission'
embedding. Rule ①: completion is never client-assertable, only
decide_attempt (via complete_embedded_items) can write the ItemProgress
row. Redis-free, HTTP-free.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.lms import Course, CourseModule, Enrollment, ItemProgress, ModuleItem
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User
from app.services.missions import decide_attempt, start_attempt
from app.services.missions.embedding import complete_embedded_items


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Embed User", email=f"embed-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _course_with_mission_item(db, *, author, mission_id, variant_id=None) -> tuple[Course, ModuleItem]:
    course = Course(id=uuid.uuid4(), title="Embedding Course", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    content = {"mission_id": str(mission_id)}
    if variant_id:
        content["variant_id"] = str(variant_id)
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="mission", content=content)
    db.add(item)
    await db.flush()
    return course, item


async def _mission_with_variants(db, *, author, points=(30, 60)) -> tuple[Mission, list[MissionVariant]]:
    mission = Mission(
        id=uuid.uuid4(), title="Embedded Mission", slug=f"embed-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    variants = []
    for i, pts in enumerate(points, start=1):
        v = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label=f"V{i}", position=i, points=pts)
        db.add(v)
        variants.append(v)
    await db.flush()
    return mission, variants


@pytest.mark.asyncio
async def test_passing_a_standalone_mission_touches_no_module_items(db):
    """The common case — a mission with no embedding anywhere is a no-op."""
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)  # must not raise


@pytest.mark.asyncio
async def test_passing_completes_the_embedded_item_for_an_enrolled_student(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    course, item = await _course_with_mission_item(db, author=author, mission_id=mission.id)
    student = await _user(db)
    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=course.id, source="self"))
    await db.flush()

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)

    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id, ItemProgress.item_id == item.id)
    )).scalars().first()
    assert row is not None
    assert row.status == "completed"
    assert row.completed_at is not None


@pytest.mark.asyncio
async def test_failing_does_not_complete_the_embedded_item(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    course, item = await _course_with_mission_item(db, author=author, mission_id=mission.id)
    student = await _user(db)
    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=course.id, source="self"))
    await db.flush()

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await decide_attempt(db, attempt=attempt, passed=False)

    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id, ItemProgress.item_id == item.id)
    )).scalars().first()
    assert row is None or row.status != "completed"


@pytest.mark.asyncio
async def test_not_enrolled_student_does_not_get_the_item_completed(db):
    """Passing a mission standalone must not silently grant course credit
    to a student who never enrolled in the course that happens to embed it."""
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    course, item = await _course_with_mission_item(db, author=author, mission_id=mission.id)
    student = await _user(db)  # deliberately not enrolled

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)

    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id, ItemProgress.item_id == item.id)
    )).scalars().first()
    assert row is None


@pytest.mark.asyncio
async def test_pinned_variant_only_completes_on_that_variants_pass(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author, points=(30, 60))
    course, item = await _course_with_mission_item(db, author=author, mission_id=mission.id, variant_id=variants[1].id)
    student = await _user(db)
    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=course.id, source="self"))
    await db.flush()

    easy = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await decide_attempt(db, attempt=easy, passed=True, score=90)
    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id, ItemProgress.item_id == item.id)
    )).scalars().first()
    assert row is None or row.status != "completed"

    hard = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[1].id)
    await decide_attempt(db, attempt=hard, passed=True, score=95)
    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id, ItemProgress.item_id == item.id)
    )).scalars().first()
    assert row is not None and row.status == "completed"


@pytest.mark.asyncio
async def test_complete_embedded_items_is_a_direct_service_call_not_reachable_via_progress_action(db):
    """Rule ① structural check: complete_embedded_items is not wired to any
    student-assertable action — services/lms/progress.py's _ACTION_KINDS has
    no entry mapping to a 'mission' item at all."""
    from app.services.lms.progress import _ACTION_KINDS
    for kinds in _ACTION_KINDS.values():
        assert "mission" not in kinds
