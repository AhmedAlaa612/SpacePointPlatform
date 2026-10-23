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
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.enrollment import Enrollment
from app.models.lms.invite_grant import InvitationCodeGrant, UserInvitationCode
from app.models.lms.learning_path import LearningPathStep
from app.models.lms.program import LmsProgramAssignment
from app.models.sessions.cohort import Cohort
from app.models.user import User
from app.services.invitations import resolve_invite_code
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


async def _register_into_cohort(
    db: AsyncSession, *, user: User, cohort_id: uuid.UUID, expires_at: datetime | None = None
) -> None:
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
    itself already follows for the exact same reason.

    Observer mode (2026-10): a user holding the `observer` role registers
    into the same cohort but with a `mode="observer"` assignment —
    identical engine, partitioned from official data."""
    if user.contact_id is None:
        logger.warning("invite-code program grant: user %s has no linked contact, skipping", user.id)
        return
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return
    mode = "observer" if "observer" in (user.role_values or []) else "participant"
    try:
        registration = await register(
            db, contact_id=user.contact_id, cohort_id=cohort_id,
            registered_via="invite_code", payment_status="waived",
        )
        await sync_registration_lms(
            db, registration=registration, cohort=cohort, create_account=True, mode=mode,
            expires_at=expires_at,
        )
    except HTTPException:
        logger.exception("invite-code program grant: couldn't register user %s into cohort %s", user.id, cohort_id)


async def _apply_grant(
    db: AsyncSession, *, user_id: uuid.UUID, grant: InvitationCodeGrant, expires_at: datetime | None = None
) -> None:
    if grant.product_type == "lms_program":
        user = await db.get(User, user_id)
        if user is not None:
            await _register_into_cohort(db, user=user, cohort_id=grant.cohort_id, expires_at=expires_at)
        return
    for course_id in await _grant_course_ids(db, grant):
        await enroll(db, user_id=user_id, course_id=course_id, source="invite_code", expires_at=expires_at)


async def apply_invite_code_grants_to_new_user(
    db: AsyncSession, *, user_id: uuid.UUID, invitation_code_id: uuid.UUID
) -> None:
    """Called right where `routers/auth.py::student_signup` bumps
    `invitation.used_count` — enrols the brand-new account in everything the
    code carries, same as it would if they'd signed up yesterday and the
    grant already existed."""
    invitation = await db.get(InvitationCode, invitation_code_id)
    expires_at = invitation.expires_at if invitation else None
    grants = (await db.execute(
        select(InvitationCodeGrant).where(InvitationCodeGrant.invitation_code_id == invitation_code_id)
    )).scalars().all()
    for grant in grants:
        await _apply_grant(db, user_id=user_id, grant=grant, expires_at=expires_at)


async def redeem_invite_code(
    db: AsyncSession,
    *,
    user: User,
    code_str: str,
    allow_ambassador: bool = False,
) -> tuple[InvitationCode | None, User | None, bool]:
    """Validates and redeems `code_str` for `user`.
    Returns `(invitation, ambassador, already_redeemed)`.
    - If `invitation.kind == 'observer'`, transitions the learner from
      `student` to `observer` (`user.roles` replaces `student` with
      `observer`, and any existing `LmsProgramAssignment` rows for `user`
      flip to `mode='observer'`).
    - Inserts `UserInvitationCode` inside a SAVEPOINT so concurrent requests
      are idempotent. Only increments `invitation.used_count` on a fresh
      redemption.
    - Always runs `apply_invite_code_grants_to_new_user` (which is idempotent)
      so any attached courses, learning paths, or cohort programs are granted.
    """
    invitation, ambassador = await resolve_invite_code(db, code_str, kind="student")
    if invitation is None:
        if not allow_ambassador:
            raise HTTPException(
                status_code=400, detail="Invalid or inactive invite code"
            )
        # Ambassador referral (only used at initial signup)
        user.invitation_code_used = code_str.strip().upper()
        user.invited_by_id = ambassador.id if ambassador else None
        return None, ambassador, False

    # 1. Observer role transition rule: redeeming an observer code turns a
    # student account into an observer (not a student anymore).
    if invitation.kind == "observer":
        current_roles = [r for r in (user.role_values or []) if r != "student"]
        if "observer" not in current_roles:
            current_roles.append("observer")
        user.roles = [UserRole(r) for r in current_roles]
        await db.execute(
            update(LmsProgramAssignment)
            .where(LmsProgramAssignment.user_id == user.id)
            .values(mode="observer")
        )

    # 2. Check / insert UserInvitationCode redemption record
    existing = (
        await db.execute(
            select(UserInvitationCode).where(
                UserInvitationCode.user_id == user.id,
                UserInvitationCode.invitation_code_id == invitation.id,
            )
        )
    ).scalars().first()

    already_redeemed = existing is not None
    if not already_redeemed:
        async with db.begin_nested():
            db.add(
                UserInvitationCode(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    invitation_code_id=invitation.id,
                    code=invitation.code,
                    redeemed_at=datetime.now(timezone.utc),
                )
            )
            await db.flush()
        invitation.used_count += 1

    # Keep legacy scalar column updated with the latest redeemed code
    user.invitation_code_used = invitation.code

    # 3. Apply all course / path / cohort-program grants on this code
    await apply_invite_code_grants_to_new_user(
        db, user_id=user.id, invitation_code_id=invitation.id
    )
    return invitation, None, already_redeemed


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

    user_ids = list(
        set(
            (
                await db.execute(
                    select(User.id)
                    .outerjoin(
                        UserInvitationCode,
                        UserInvitationCode.user_id == User.id,
                    )
                    .where(
                        or_(
                            UserInvitationCode.invitation_code_id == invitation_code.id,
                            User.invitation_code_used == invitation_code.code,
                        )
                    )
                )
            ).scalars().all()
        )
    )
    for user_id in user_ids:
        await _apply_grant(db, user_id=user_id, grant=grant, expires_at=invitation_code.expires_at)

    return grant, len(user_ids)


async def sync_invite_code_enrollments_expiry(
    db: AsyncSession, *, invitation_code: InvitationCode
) -> int:
    """When an invite code's expires_at changes, synchronize expires_at on all
    Enrollment rows granted through this code to its users.
    If the code has expired, enrollments expire immediately so learners lose access.
    If the code's expiry was extended or removed, enrollment expiry is updated accordingly."""
    from app.services.lms.program import resolve_cohort_program_course_ids

    # 1. All users of this code
    user_ids = list(
        set(
            (
                await db.execute(
                    select(User.id)
                    .outerjoin(
                        UserInvitationCode,
                        UserInvitationCode.user_id == User.id,
                    )
                    .where(
                        or_(
                            UserInvitationCode.invitation_code_id == invitation_code.id,
                            User.invitation_code_used == invitation_code.code,
                        )
                    )
                )
            ).scalars().all()
        )
    )
    if not user_ids:
        return 0

    # 2. All grants on this code
    grants = (await db.execute(
        select(InvitationCodeGrant).where(InvitationCodeGrant.invitation_code_id == invitation_code.id)
    )).scalars().all()
    if not grants:
        return 0

    all_course_ids: set[uuid.UUID] = set()
    for grant in grants:
        if grant.product_type == "lms_program" and grant.cohort_id:
            cohort_courses = await resolve_cohort_program_course_ids(db, grant.cohort_id)
            all_course_ids.update(cohort_courses)
        else:
            courses = await _grant_course_ids(db, grant)
            all_course_ids.update(courses)

    if not all_course_ids:
        return 0

    # 3. Find enrollments for these users and courses that were granted (not independent purchases)
    enrollments = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id.in_(user_ids),
            Enrollment.course_id.in_(all_course_ids),
            Enrollment.source != "purchase",
        )
    )).scalars().all()

    updated = 0
    for row in enrollments:
        row.expires_at = invitation_code.expires_at
        updated += 1

    await db.flush()
    return updated


async def is_user_cohort_grant_expired(
    db: AsyncSession, *, user_id: uuid.UUID, cohort_id: uuid.UUID | None
) -> bool:
    """Checks if a user's access to a cohort program checklist was granted
    via invite code(s) that are now expired. If any granting invite code is still
    active and unexpired (or has no expiry), returns False (access is still valid).
    Returns True only if the cohort was granted via invite code(s) and ALL of
    those invite codes are currently expired or inactive."""
    if cohort_id is None:
        return False

    codes = (await db.execute(
        select(InvitationCode)
        .join(InvitationCodeGrant, InvitationCodeGrant.invitation_code_id == InvitationCode.id)
        .join(UserInvitationCode, UserInvitationCode.invitation_code_id == InvitationCode.id)
        .where(
            UserInvitationCode.user_id == user_id,
            InvitationCodeGrant.product_type == "lms_program",
            InvitationCodeGrant.cohort_id == cohort_id,
        )
    )).scalars().all()

    if not codes:
        user = await db.get(User, user_id)
        if user and user.invitation_code_used:
            legacy_codes = (await db.execute(
                select(InvitationCode)
                .join(InvitationCodeGrant, InvitationCodeGrant.invitation_code_id == InvitationCode.id)
                .where(
                    InvitationCode.code == user.invitation_code_used,
                    InvitationCodeGrant.product_type == "lms_program",
                    InvitationCodeGrant.cohort_id == cohort_id,
                )
            )).scalars().all()
            codes = list(legacy_codes)

    if not codes:
        return False

    now = datetime.now(timezone.utc)
    for code in codes:
        if code.is_active and (code.expires_at is None or code.expires_at > now):
            return False

    return True
