"""Cohort curriculum resolution + reconciliation (P4-1/P4-2, LMS Phase 2
Stage 4, 2026-08-10).

`resolve_cohort_curriculum` is the one place that reads both
`cohort_curriculum` and `program_curriculum` and applies the override —
nothing else should query `program_curriculum` directly to figure out what
a specific cohort teaches.

`reconcile_cohort_enrollments` exists because `enroll_in_cohort_curriculum`
(below) only ever ran once, at registration time — a course added to a
curriculum *after* students already registered reached nobody, silently.
Three triggers call this: a cohort's own curriculum changing, a program's
curriculum changing (fanned out to every cohort that inherits it — has no
override of its own), and a manual "reconcile now" admin action. A brand
new registration does NOT need this — `sync_registration_lms` already
enrolls that one student via `enroll_in_cohort_curriculum`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms import CohortCurriculum, Enrollment, ProgramCurriculum
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.user import User
from app.services.lms import enroll
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES


async def resolve_cohort_curriculum(db: AsyncSession, cohort_id: uuid.UUID) -> list[uuid.UUID]:
    """Course ids in position order for this cohort. A `cohort_curriculum`
    row for this cohort, if any exist, wins outright over the program's own
    curriculum — never merged, same idiom `session_materials` already uses
    (a cohort with its own rows does not inherit the program's; that is
    what "override" means here)."""
    override = (await db.execute(
        select(CohortCurriculum.course_id)
        .where(CohortCurriculum.cohort_id == cohort_id)
        .order_by(CohortCurriculum.position)
    )).scalars().all()
    if override:
        return list(override)

    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return []
    return list((await db.execute(
        select(ProgramCurriculum.course_id)
        .where(ProgramCurriculum.program_id == cohort.program_id)
        .order_by(ProgramCurriculum.position)
    )).scalars().all())


async def enroll_in_cohort_curriculum(
    db: AsyncSession, *, user_id: uuid.UUID, cohort_id: uuid.UUID, registration_id: uuid.UUID,
) -> list[Enrollment]:
    """The per-registration path — called once, at registration time, by
    `sync_registration_lms`. Renamed from `enroll_in_program_curriculum`
    (P4-1): resolution is cohort-aware now, but `program_id` is still
    recorded on the enrollment for provenance, same as before."""
    cohort = await db.get(Cohort, cohort_id)
    course_ids = await resolve_cohort_curriculum(db, cohort_id)
    return [
        await enroll(
            db, user_id=user_id, course_id=course_id, source="registration",
            program_id=cohort.program_id if cohort else None, registration_id=registration_id,
        )
        for course_id in course_ids
    ]


async def reconcile_cohort_enrollments(db: AsyncSession, cohort_id: uuid.UUID) -> int:
    """Re-run curriculum enrollment for every currently-registered student
    in this cohort, not just the one who just registered — the fix for
    "adding a course to a curriculum reaches everyone already registered,
    silently" (P4-2's done-when). Idempotent per (user, course) via a
    pre-check plus `enroll()`'s own idempotency; safe to call as often as
    needed. Returns the number of NEW enrollments created."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return 0
    course_ids = await resolve_cohort_curriculum(db, cohort_id)
    if not course_ids:
        return 0

    registrations = (await db.execute(
        select(Registration).where(
            Registration.cohort_id == cohort_id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )).scalars().all()

    created = 0
    for registration in registrations:
        user = (await db.execute(
            select(User).where(User.contact_id == registration.contact_id).order_by(User.created_at)
        )).scalars().first()
        if user is None:
            continue
        for course_id in course_ids:
            existing = (await db.execute(
                select(Enrollment.id).where(Enrollment.user_id == user.id, Enrollment.course_id == course_id)
            )).first()
            if existing is not None:
                continue
            await enroll(
                db, user_id=user.id, course_id=course_id, source="registration",
                program_id=cohort.program_id, registration_id=registration.id,
            )
            created += 1
    return created


async def reconcile_cohorts_inheriting_program(db: AsyncSession, program_id: uuid.UUID) -> int:
    """Fan-out for a `program_curriculum` edit: every cohort of this
    program that has NO `cohort_curriculum` rows of its own inherits the
    program's curriculum (resolve_cohort_curriculum's override rule), so a
    program-level change reaches all of them. A cohort with its own
    override is deliberately skipped — its curriculum didn't change."""
    cohort_ids = (await db.execute(
        select(Cohort.id).where(Cohort.program_id == program_id)
    )).scalars().all()
    total = 0
    for cohort_id in cohort_ids:
        has_override = (await db.execute(
            select(CohortCurriculum.id).where(CohortCurriculum.cohort_id == cohort_id).limit(1)
        )).first()
        if has_override:
            continue
        total += await reconcile_cohort_enrollments(db, cohort_id)
    return total
