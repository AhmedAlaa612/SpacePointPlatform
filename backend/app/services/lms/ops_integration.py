"""LMS ops integration (LM1-7) — create-account-at-registration, curriculum
auto-enroll, and enrollment status following registration status (D4).

Deliberately NOT called from inside `registration.register()` or the
importer's `_process_row()` — both run inside the importer's dry-run
SAVEPOINT (services/sessions/importer.py), which gets rolled back, and a real
account + a real "set your password" email must never fire on a dry run.
This module is invoked only from call sites that know they're looking at a
committed registration: `desk_register` (immediate), and an ARQ job for the
bulk-import commit path — the same shape `send_import_batch_emails` already
uses for ticket emails.
"""

from __future__ import annotations

import logging
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_password_set_token, get_password_hash
from app.models.lms import Enrollment
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.documents.id_card import ensure_card_number
from app.services.email import try_send_email
from app.services.lms.program import assign_lms_program
from app.services.nicknames import assign_nickname

logger = logging.getLogger("services.lms.ops_integration")


async def get_or_create_student_account(db: AsyncSession, contact_id: uuid.UUID) -> tuple[User | None, bool]:
    """Reuses an existing account linked to this contact (adding the
    `student` role if it's missing one); otherwise creates one with a random
    password and `must_change_password=True` (D4). Returns (None, False) if
    the contact has no email, or if the email is already on a *different*
    user (rare: pre-existing staff account with the same email, not linked
    to this contact) — ops still gets the registration, just not the auto
    LMS account; nothing here is fatal to registration."""
    # .order_by: contact_id isn't unique yet (B4/D1, Phase 2 Stage 1 fixes it
    # properly) — deterministic ordering means a repeated lookup at least
    # resolves to the same account every time.
    existing = (await db.execute(
        select(User).where(User.contact_id == contact_id).order_by(User.created_at)
    )).scalars().first()
    if existing is not None:
        if "student" not in existing.role_values:
            existing.roles = [*existing.roles, "student"]
            await assign_nickname(db, existing)
        return existing, False

    contact = await db.get(Contact, contact_id)
    if contact is None or not contact.email:
        logger.warning("get_or_create_student_account: contact %s has no email, skipping", contact_id)
        return None, False

    dup = (await db.execute(select(User.id).where(User.email == contact.email))).first()
    if dup:
        logger.warning(
            "get_or_create_student_account: email %s is already on a different account, skipping", contact.email
        )
        return None, False

    user = User(
        id=uuid.uuid4(),
        full_name=contact.full_name,
        email=contact.email,
        phone=contact.primary_phone_e164,
        password_hash=get_password_hash(secrets.token_urlsafe(24)),
        roles=["student"],
        contact_id=contact_id,
        status="active",
        must_change_password=True,
    )
    db.add(user)
    await db.flush()
    await assign_nickname(db, user)
    await ensure_card_number(db, user)
    return user, True


async def send_set_password_email(user: User, *, purpose: str = "welcome") -> bool:
    """Public (P3-3, 2026-08-10) — was module-private until the student
    panel's "create account & invite" and "password reset" actions needed
    to call it directly, not just via `sync_registration_lms`. Same token
    mechanism either way (`create_password_set_token`, 24h, stateless) —
    `purpose` only changes the copy, since "an account was created for you"
    reads wrong for a reset on an account that already existed."""
    from app.core.config import settings
    token = create_password_set_token(user.id)
    link = f"{settings.FRONTEND_URL}/learn/set-password?token={token}"
    intro = (
        "An account was created for you on the SpacePoint LMS."
        if purpose == "welcome" else
        "Here's the link to reset your SpacePoint LMS password."
    )
    return await try_send_email(
        user.email,
        "Your SpacePoint learning account",
        (
            f"<p>Hi {user.full_name},</p>"
            f'<p>{intro} Set your password here: <a href="{link}">{link}</a></p>'
            "<p>This link is valid for 24 hours.</p>"
            "<p>— SpacePoint</p>"
        ),
        html=True,
    )


async def sync_registration_lms(
    db: AsyncSession, *, registration: Registration, cohort: Cohort, create_account: bool,
) -> User | None:
    """The D4 flow for one registration: find-or-create the student account,
    assign the cohort's LMS Program checklist if it has one (2026-08-21 —
    enrolls every course item and assigns every mission_run item's attempt
    immediately, same "enroll everything up front" behavior the old
    curriculum table had; a no-op when the cohort has no checklist at
    all), email the set-password link (only for a genuinely new account —
    an existing one has nothing to set). Never raises — an LMS-side
    hiccup must not break registration, mirroring issue_ticket()'s
    "return False, log it" discipline."""
    if not create_account:
        return None
    try:
        user, created = await get_or_create_student_account(db, registration.contact_id)
        if user is None:
            return None
        await assign_lms_program(
            db, user_id=user.id, cohort_id=cohort.id, registration_id=registration.id,
        )
        if created:
            await send_set_password_email(user)
        return user
    except Exception:
        logger.exception("sync_registration_lms failed for registration %s", registration.id)
        return None


async def deactivate_registration_enrollments(db: AsyncSession, registration_id: uuid.UUID) -> None:
    """A cancelled registration takes its LMS enrollments (if any) with it —
    `status` flips to inactive, the row and progress survive (D4/LM1-7 spec).
    Re-registering (register()'s reinstate path) calls sync_registration_lms
    again, and enroll()'s own idempotency reactivates in place."""
    rows = (await db.execute(
        select(Enrollment).where(Enrollment.registration_id == registration_id, Enrollment.status == "active")
    )).scalars().all()
    for row in rows:
        row.status = "inactive"
