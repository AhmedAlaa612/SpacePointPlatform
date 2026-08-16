"""P5-1/P5-2 (LMS Phase 2 Stage 5, 2026-08-11) — mission attempt lifecycle
and the submission verifier kind. Redis-free, HTTP-free.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.lms import PointEvent
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.user import User
from app.services.missions import decide_attempt, start_attempt
from app.services.missions.verifiers.submission import (
    review_submission_attempt,
    submit_submission_attempt,
)


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Mission User", email=f"mission-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _mission_with_variants(db, *, author, points=(30, 60)) -> tuple[Mission, list[MissionVariant]]:
    mission = Mission(
        id=uuid.uuid4(), title="Build a Radio", slug=f"radio-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    variants = []
    for i, pts in enumerate(points, start=1):
        variant = MissionVariant(
            id=uuid.uuid4(), mission_id=mission.id, label=f"V{i}", position=i, points=pts,
        )
        db.add(variant)
        variants.append(variant)
    await db.flush()
    return mission, variants


async def _points_total(db, user_id) -> int:
    rows = (await db.execute(select(PointEvent.points).where(PointEvent.user_id == user_id))).scalars().all()
    return sum(rows)


# ── start_attempt ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_attempt_creates_attempt_no_one(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    student = await _user(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    assert attempt.attempt_no == 1
    assert attempt.status == "in_progress"
    assert attempt.variant_id == variants[0].id


@pytest.mark.asyncio
async def test_start_attempt_resumes_an_in_progress_attempt_ignoring_variant(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    student = await _user(db)

    first = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    resumed = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[1].id)
    assert resumed.id == first.id
    assert resumed.variant_id == variants[0].id  # still the original variant


@pytest.mark.asyncio
async def test_start_attempt_force_new_bypasses_single_flight(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    student = await _user(db)

    first = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    second = await start_attempt(
        db, user_id=student.id, mission_id=mission.id, variant_id=variants[1].id, force_new=True,
    )
    assert second.id != first.id
    assert second.attempt_no == 2
    assert second.variant_id == variants[1].id
    assert first.status == "in_progress"
    assert second.status == "in_progress"  # both concurrently in progress


@pytest.mark.asyncio
async def test_start_attempt_increments_attempt_no_after_a_decision(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    student = await _user(db)

    first = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await decide_attempt(db, attempt=first, passed=False)

    second = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    assert second.id != first.id
    assert second.attempt_no == 2


# ── decide_attempt: points on pass, idempotent per (mission, variant) ──────

@pytest.mark.asyncio
async def test_decide_attempt_passed_awards_variant_points(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author, points=(30,))
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)

    decided = await decide_attempt(db, attempt=attempt, passed=True, score=90)
    assert decided.status == "passed"
    assert decided.decided_at is not None
    assert await _points_total(db, student.id) == 30


@pytest.mark.asyncio
async def test_decide_attempt_failed_awards_nothing(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author, points=(30,))
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)

    decided = await decide_attempt(db, attempt=attempt, passed=False, score=10)
    assert decided.status == "failed"
    assert await _points_total(db, student.id) == 0


@pytest.mark.asyncio
async def test_passing_the_same_variant_twice_does_not_double_award(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author, points=(30,))
    student = await _user(db)

    first = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await decide_attempt(db, attempt=first, passed=True, score=90)

    second = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await decide_attempt(db, attempt=second, passed=True, score=95)

    assert await _points_total(db, student.id) == 30  # not 60


@pytest.mark.asyncio
async def test_passing_a_harder_variant_awards_again(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author, points=(30, 60))
    student = await _user(db)

    easy = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await decide_attempt(db, attempt=easy, passed=True, score=90)
    await decide_attempt(db, attempt=await start_attempt(
        db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id
    ), passed=False)  # unrelated failed attempt shouldn't matter

    hard = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variants[1].id, user_id=student.id,
        attempt_no=3, status="in_progress",
    )
    db.add(hard)
    await db.flush()
    await decide_attempt(db, attempt=hard, passed=True, score=95)

    assert await _points_total(db, student.id) == 90  # 30 + 60


# ── submission verifier kind ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submission_flow_end_to_end_reviewer_passes(db):
    author = await _user(db, roles=["operations"])
    reviewer = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author, points=(40,))
    student = await _user(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    submitted = await submit_submission_attempt(
        db, attempt=attempt, artifact_url="https://example.com/my-radio", notes="built with a coil"
    )
    assert submitted.status == "submitted"
    assert submitted.payload["artifact_url"] == "https://example.com/my-radio"

    reviewed = await review_submission_attempt(
        db, attempt=submitted, reviewer_id=reviewer.id, passed=True, score=88, review_comment="Great work"
    )
    assert reviewed.status == "passed"
    assert reviewed.decided_by == reviewer.id
    assert reviewed.payload["review_comment"] == "Great work"
    assert await _points_total(db, student.id) == 40


@pytest.mark.asyncio
async def test_submission_flow_reviewer_fails_awards_nothing(db):
    author = await _user(db, roles=["operations"])
    reviewer = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author, points=(40,))
    student = await _user(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    submitted = await submit_submission_attempt(db, attempt=attempt, artifact_url="https://example.com/x")
    reviewed = await review_submission_attempt(
        db, attempt=submitted, reviewer_id=reviewer.id, passed=False, score=20, review_comment="Needs rework"
    )
    assert reviewed.status == "failed"
    assert await _points_total(db, student.id) == 0


@pytest.mark.asyncio
async def test_cannot_submit_an_attempt_that_is_not_in_progress(db):
    author = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    student = await _user(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)
    await submit_submission_attempt(db, attempt=attempt, artifact_url="https://example.com/x")

    with pytest.raises(Exception):
        await submit_submission_attempt(db, attempt=attempt, artifact_url="https://example.com/y")


@pytest.mark.asyncio
async def test_cannot_review_an_attempt_that_is_not_submitted(db):
    author = await _user(db, roles=["operations"])
    reviewer = await _user(db, roles=["operations"])
    mission, variants = await _mission_with_variants(db, author=author)
    student = await _user(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variants[0].id)

    with pytest.raises(Exception):
        await review_submission_attempt(db, attempt=attempt, reviewer_id=reviewer.id, passed=True)
