"""LMS redesign (2026-08-06) — my_courses_dashboard: stats aggregation and
the resume pointer (never-touched vs. last-touched vs. module-just-finished).
"""

import uuid

import pytest

from app.models.lms import Course, CourseModule, ModuleItem
from app.models.user import User
from app.services.lms import enroll, item_progress
from app.services.lms.dashboard import my_courses_dashboard, recent_activity


async def _author(db) -> User:
    author = User(
        id=uuid.uuid4(), full_name="Author", email=f"author-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(author)
    await db.flush()
    return author


async def _student(db) -> User:
    student = User(
        id=uuid.uuid4(), full_name="Student", email=f"student-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(student)
    await db.flush()
    return student


async def _course_with_two_modules(db, *, author) -> tuple[Course, CourseModule, CourseModule, list[ModuleItem]]:
    course = Course(id=uuid.uuid4(), title="Orbital Mechanics", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    m1 = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    m2 = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M2", position=2)
    db.add(m1)
    db.add(m2)
    await db.flush()
    i1 = ModuleItem(id=uuid.uuid4(), module_id=m1.id, position=1, kind="text", content={"body": "a"})
    i2 = ModuleItem(id=uuid.uuid4(), module_id=m1.id, position=2, kind="text", content={"body": "b"})
    i3 = ModuleItem(id=uuid.uuid4(), module_id=m2.id, position=1, kind="text", content={"body": "c"})
    db.add_all([i1, i2, i3])
    await db.flush()
    return course, m1, m2, [i1, i2, i3]


@pytest.mark.asyncio
async def test_no_enrollments_returns_empty_dashboard(db):
    student = await _student(db)
    await db.commit()

    result = await my_courses_dashboard(db, user_id=student.id)
    assert result["stats"] == {"in_progress": 0, "total_enrolled": 0, "modules_done": 0}
    assert result["resume"] is None
    assert result["courses"] == []


@pytest.mark.asyncio
async def test_expired_enrollment_excluded_from_my_courses(db):
    """P1-3: My Courses must stop listing a course once its enrollment has
    expired — the same predicate the access-check gate reads."""
    from datetime import datetime, timedelta, timezone

    author = await _author(db)
    course, _m1, _m2, _items = await _course_with_two_modules(db, author=author)
    student = await _student(db)
    enrollment = await enroll(db, user_id=student.id, course_id=course.id)
    enrollment.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()

    result = await my_courses_dashboard(db, user_id=student.id)
    assert result["courses"] == []
    assert result["stats"]["total_enrolled"] == 0


@pytest.mark.asyncio
async def test_resume_points_at_first_item_when_never_touched(db):
    author = await _author(db)
    student = await _student(db)
    course, m1, _m2, items = await _course_with_two_modules(db, author=author)
    await db.commit()
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    result = await my_courses_dashboard(db, user_id=student.id)
    assert result["stats"]["total_enrolled"] == 1
    assert result["courses"][0]["status"] == "not_started"
    assert result["resume"]["course_id"] == course.id
    assert result["resume"]["module_id"] == m1.id
    assert result["resume"]["next_item_id"] == items[0].id


@pytest.mark.asyncio
async def test_resume_advances_to_next_item_after_progress(db):
    author = await _author(db)
    student = await _student(db)
    course, m1, _m2, items = await _course_with_two_modules(db, author=author)
    await db.commit()
    await enroll(db, user_id=student.id, course_id=course.id)
    await item_progress(db, user_id=student.id, item_id=items[0].id, action="text-viewed")
    await db.commit()

    result = await my_courses_dashboard(db, user_id=student.id)
    assert result["courses"][0]["status"] == "in_progress"
    assert result["stats"]["in_progress"] == 1
    assert result["resume"]["module_id"] == m1.id
    assert result["resume"]["next_item_id"] == items[1].id  # second item in m1, not yet done


@pytest.mark.asyncio
async def test_resume_moves_to_next_module_once_current_is_done(db):
    author = await _author(db)
    student = await _student(db)
    course, m1, m2, items = await _course_with_two_modules(db, author=author)
    await db.commit()
    await enroll(db, user_id=student.id, course_id=course.id)
    await item_progress(db, user_id=student.id, item_id=items[0].id, action="text-viewed")
    await item_progress(db, user_id=student.id, item_id=items[1].id, action="text-viewed")
    await db.commit()

    result = await my_courses_dashboard(db, user_id=student.id)
    assert result["resume"]["module_id"] == m2.id
    assert result["resume"]["next_item_id"] == items[2].id


@pytest.mark.asyncio
async def test_completed_course_excluded_from_resume_candidates(db):
    author = await _author(db)
    student = await _student(db)
    course, _m1, _m2, items = await _course_with_two_modules(db, author=author)
    await db.commit()
    await enroll(db, user_id=student.id, course_id=course.id)
    for item in items:
        await item_progress(db, user_id=student.id, item_id=item.id, action="text-viewed")
    await db.commit()

    result = await my_courses_dashboard(db, user_id=student.id)
    assert result["courses"][0]["status"] == "completed"
    assert result["stats"]["modules_done"] == 2
    assert result["resume"] is None


@pytest.mark.asyncio
async def test_recent_activity_lists_completed_items_newest_first(db):
    author = await _author(db)
    student = await _student(db)
    course, _m1, _m2, items = await _course_with_two_modules(db, author=author)
    await db.commit()
    await enroll(db, user_id=student.id, course_id=course.id)
    await item_progress(db, user_id=student.id, item_id=items[0].id, action="text-viewed")
    await item_progress(db, user_id=student.id, item_id=items[1].id, action="text-viewed")
    await db.commit()

    result = await recent_activity(db, user_id=student.id)
    assert [row["item_id"] for row in result] == [items[1].id, items[0].id]
    assert all(row["course_id"] == course.id for row in result)


@pytest.mark.asyncio
async def test_recent_activity_empty_for_untouched_student(db):
    student = await _student(db)
    await db.commit()

    assert await recent_activity(db, user_id=student.id) == []
