"""P2-5 (LMS Phase 2 Stage 2, 2026-08-10) — backfilling point_events for
quiz passes that predate the points ledger.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.lms.course import Course, CourseModule, ModuleItem
from app.models.lms.enrollment import ItemProgress
from app.models.lms.points import PointEvent
from app.models.user import User
from app.services.lms.points import QUIZ_PASS_POINTS
from scripts.lms_backfill_points import backfill_quiz_points


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Backfill Student", email=f"backfill-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _quiz_item(db) -> ModuleItem:
    author = await _user(db)
    course = Course(id=uuid.uuid4(), title="Course", created_by=author.id)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="quiz", content={})
    db.add(item)
    await db.flush()
    return item


@pytest.mark.asyncio
async def test_backfills_a_pre_existing_passed_quiz(db):
    student = await _user(db)
    quiz = await _quiz_item(db)
    row = ItemProgress(
        id=uuid.uuid4(), user_id=student.id, item_id=quiz.id, status="completed",
        quiz_attempts=1, best_score=Decimal("100"), completed_at=datetime.now(timezone.utc),
        first_score=None,  # the pre-P2-3 marker
    )
    db.add(row)
    await db.commit()

    awarded = await backfill_quiz_points(db)
    assert awarded == 1

    await db.refresh(row)
    assert row.first_score == Decimal("100")
    assert row.first_scored_at is not None

    events = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert len(events) == 1
    assert events[0].source == "migration"
    assert events[0].points == QUIZ_PASS_POINTS


@pytest.mark.asyncio
async def test_skips_a_quiz_the_live_code_already_scored(db):
    """first_score already set means this row postdates P2-3 — the live
    submit_quiz path already handled its award; backfilling it again would
    double-count (a different source, but the same underlying event)."""
    student = await _user(db)
    quiz = await _quiz_item(db)
    row = ItemProgress(
        id=uuid.uuid4(), user_id=student.id, item_id=quiz.id, status="completed",
        quiz_attempts=1, best_score=Decimal("100"), completed_at=datetime.now(timezone.utc),
        first_score=Decimal("100"), first_scored_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()

    awarded = await backfill_quiz_points(db)
    assert awarded == 0


@pytest.mark.asyncio
async def test_skips_an_incomplete_quiz(db):
    student = await _user(db)
    quiz = await _quiz_item(db)
    row = ItemProgress(
        id=uuid.uuid4(), user_id=student.id, item_id=quiz.id, status="in_progress",
        quiz_attempts=1, best_score=Decimal("40"), first_score=None,
    )
    db.add(row)
    await db.commit()

    assert await backfill_quiz_points(db) == 0


@pytest.mark.asyncio
async def test_rerunning_is_a_noop(db):
    student = await _user(db)
    quiz = await _quiz_item(db)
    row = ItemProgress(
        id=uuid.uuid4(), user_id=student.id, item_id=quiz.id, status="completed",
        quiz_attempts=1, best_score=Decimal("100"), completed_at=datetime.now(timezone.utc), first_score=None,
    )
    db.add(row)
    await db.commit()

    first_run = await backfill_quiz_points(db)
    await db.commit()
    second_run = await backfill_quiz_points(db)

    assert first_run == 1
    assert second_run == 0  # first_score is no longer NULL

    events = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert len(events) == 1
