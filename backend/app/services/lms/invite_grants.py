"""Invite-code course/path/program grants (2026-08-21, program added
2026-09-15) — see `models/lms/invite_grant.py` for the shape and why this
isn't a generic groups table. Two entry points: `grant_invite_code_access`
(ops attaches a course/path/program to a code — applies immediately to
everyone who's ever used it) and `apply_invite_code_grants_to_new_user` (a
fresh signup on that code gets the same courses/paths/program on the spot).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.learning_path import LearningPathStep
from app.models.sessions.cohort import Cohort
from app.models.user import User
from app.services.lms.enrollment import enroll
from app.services.lms.ops_integration import sync_registration_lms
from app.services.sessions.registration import register

logger = logging.getLogger(__name__)


async def _grant_course_ids(db: AsyncSession, grant: InvitationCodeGrant) -> list[uuid.UUID]:
    if grant.product_type == "course":
        return [grant.course_id]
    return list((await db.execute(
        select(LearningPathStep.course_id).where(LearningPathStep.learning_path_id == grant.learning_path_id)
    )).scalars().all())


async def _register_into_cohort(db: AsyncSession, *, user: User, cohort_id: uuid.UUID) -> None:
    """A "program" grant is the *full* experience of registering into that
    cohort, not just the checklist — a real Registration row (roster,
    attendance-eligible, the onboarding email), not only an
    LmsProgramAssignment. Reuses the exact `register()` ->
    `sync_registration_lms()` chain desk_register/registration_import/
    team_management already go through, so this behaves identically to a
    human registering them, minus the human.

    `payment_status="waived"` always, regardless of the program's own
    pricing model — the whole point of an invite-code grant is "this
    batch gets it free," same posture the course/path grants already
    have (no Stripe checkout involved).

    Never raises: a full cohort, a contact with no email (so no LMS
    account gets linked), or any other hiccup here must not break
    invite-code signup or a retroactive batch apply for every other
    holder — same "log it, don't raise" discipline `sync_registration_lms`
    itself already follows for the exact same reason."""
    if user.contact_id is None:
        logger.warning("invite-code program grant: user %s has no linked contact, skipping", user.id)
        return
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return
    try:
        registration = await register(
            db, contact_id=user.contact_id, cohort_id=cohort_id,
            registered_via="invite_code", payment_status="waived",
        )
        await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=True)
    except HTTPException:
        logger.exception("invite-code program grant: couldn't register user %s into cohort %s", user.id, cohort_id)


async def _apply_grant(db: AsyncSession, *, user_id: uuid.UUID, grant: InvitationCodeGrant) -> None:
    if grant.product_type == "lms_program":
        user = await db.get(User, user_id)
        if user is not None:
            await _register_into_cohort(db, user=user, cohort_id=grant.cohort_id)
        return
    for course_id in await _grant_course_ids(db, grant):
        await enroll(db, user_id=user_id, course_id=course_id, source="invite_code")


async def apply_invite_code_grants_to_new_user(db: AsyncSession, *, user_id: uuid.UUID, invitation_code_id: uuid.UUID) -> None:
    """Called right where `routers/auth.py::student_signup` bumps
    `invitation.used_count` — enrols the brand-new account in everything the
    code carries, same as it would if they'd signed up yesterday and the
    grant already existed."""
    grants = (await db.execute(
        select(InvitationCodeGrant).where(InvitationCodeGrant.invitation_code_id == invitation_code_id)
    )).scalars().all()
    for grant in grants:
        await _apply_grant(db, user_id=user_id, grant=grant)


async def grant_invite_code_access(
    db: AsyncSession, *, invitation_code: InvitationCode,
    course_id: uuid.UUID | None = None, learning_path_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
) -> tuple[InvitationCodeGrant, int]:
    """Creates the standing grant row, then immediately applies it to every
    account that has ever used this code (`users.invitation_code_used`, the
    same string-match the invite-codes admin screen already filters
    students by). Returns (grant, accounts_touched) — `enroll()` is
    idempotent and `register()` reinstates rather than duplicates, so this
    counts users touched, not new rows created. Caller (the router)
    already enforces exactly one of course_id/learning_path_id/cohort_id."""
    product_type = "course" if course_id is not None else "learning_path" if learning_path_id is not None else "lms_program"
    grant = InvitationCodeGrant(
        id=uuid.uuid4(), invitation_code_id=invitation_code.id,
        product_type=product_type,
        course_id=course_id, learning_path_id=learning_path_id, cohort_id=cohort_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(grant)
    await db.flush()

    user_ids = list((await db.execute(
        select(User.id).where(User.invitation_code_used == invitation_code.code)
    )).scalars().all())
    for user_id in user_ids:
        await _apply_grant(db, user_id=user_id, grant=grant)

    return grant, len(user_ids)
