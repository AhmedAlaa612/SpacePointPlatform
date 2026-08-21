"""Invite-code course/path grants (2026-08-21) — see
`models/lms/invite_grant.py` for the shape and why this isn't a generic
groups table. Two entry points: `grant_invite_code_access` (ops attaches a
course/path to a code — applies immediately to everyone who's ever used it)
and `apply_invite_code_grants_to_new_user` (a fresh signup on that code gets
the same courses/paths on the spot).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.learning_path import LearningPathStep
from app.models.user import User
from app.services.lms.enrollment import enroll


async def _grant_course_ids(db: AsyncSession, grant: InvitationCodeGrant) -> list[uuid.UUID]:
    if grant.product_type == "course":
        return [grant.course_id]
    return list((await db.execute(
        select(LearningPathStep.course_id).where(LearningPathStep.learning_path_id == grant.learning_path_id)
    )).scalars().all())


async def _enroll_user_in_grant(db: AsyncSession, *, user_id: uuid.UUID, grant: InvitationCodeGrant) -> None:
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
        await _enroll_user_in_grant(db, user_id=user_id, grant=grant)


async def grant_invite_code_access(
    db: AsyncSession, *, invitation_code: InvitationCode,
    course_id: uuid.UUID | None = None, learning_path_id: uuid.UUID | None = None,
) -> tuple[InvitationCodeGrant, int]:
    """Creates the standing grant row, then immediately enrols every account
    that has ever used this code (`users.invitation_code_used`, the same
    string-match the invite-codes admin screen already filters students by).
    Returns (grant, accounts_enrolled) — `enroll()` is idempotent, so
    `accounts_enrolled` counts users touched, not new rows created."""
    grant = InvitationCodeGrant(
        id=uuid.uuid4(), invitation_code_id=invitation_code.id,
        product_type="course" if course_id is not None else "learning_path",
        course_id=course_id, learning_path_id=learning_path_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(grant)
    await db.flush()

    user_ids = list((await db.execute(
        select(User.id).where(User.invitation_code_used == invitation_code.code)
    )).scalars().all())
    for user_id in user_ids:
        await _enroll_user_in_grant(db, user_id=user_id, grant=grant)

    return grant, len(user_ids)
