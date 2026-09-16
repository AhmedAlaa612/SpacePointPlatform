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
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_password_set_token, get_password_hash
from app.models.lms import Enrollment
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
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


# Students open these later than staff do — a link that dies overnight strands
# whoever read the email the next evening, and re-inviting is a manual ops step.
# 3 days matches the bulk intern import (scripts/bulk_import_interns.py) for the
# same reason; the token stays stateless, so this is also how long a leaked link
# stays usable. Callers that want a different window (e.g. the self-service
# "Forgot password?" flow, which is a 24h link — /auth/forgot-password) pass
# their own `expires_delta`.
_LINK_VALIDITY = timedelta(days=3)


def _format_validity(delta: timedelta) -> str:
    hours = delta.total_seconds() / 3600
    if hours < 24:
        n = round(hours)
        return f"{n} hour" if n == 1 else f"{n} hours"
    days = round(hours / 24)
    return "1 day" if days == 1 else f"{days} days"


# Copy varies by who's actually receiving the email — a judge invite calling
# itself a "learning account" is confusing, and a portal-wide flow (the
# self-service forgot-password link, used from both /login and /learn/login)
# shouldn't claim to be either. "portal" is the generic fallback for every
# audience that isn't specifically the LMS/student surface or judging.
_AUDIENCE_COPY: dict[str, dict[str, str]] = {
    "student": {
        "noun": "SpacePoint learning account",
        "welcome": "An account was created for you on the SpacePoint learning portal.",
        "welcome_context": "You're registered for {context}.",
        "reset": "Here's the link to reset your SpacePoint learning portal password.",
    },
    "judge": {
        "noun": "SpacePoint judge account",
        "welcome": "You've been added as a judge on SpacePoint.",
        "welcome_context": "You've been registered as a judge for {context}.",
        "reset": "Here's the link to reset your SpacePoint judge account password.",
    },
    "portal": {
        "noun": "SpacePoint account",
        "welcome": "An account was created for you on SpacePoint.",
        "reset": "Here's the link to reset your SpacePoint password.",
    },
}

# Same "you're registered for X" line as _AUDIENCE_COPY's welcome_context, but
# for send_registered_notice_email's audience, which never includes "portal" —
# there's no registration event behind the generic/self-service callers.
_REGISTERED_NOTICE_COPY: dict[str, dict[str, str]] = {
    "student": {
        "subject": "You're registered — {context}",
        "intro": "You're registered for {context}.",
    },
    "judge": {
        "subject": "You're confirmed as a judge — {context}",
        "intro": "You've been registered as a judge for {context}.",
    },
}


def build_set_password_link(user: User, expires_delta: timedelta | None = None) -> str:
    """The same link `send_set_password_email` mints and emails, factored out
    for callers that need the raw URL itself — e.g. an ops action that hands
    it to staff to paste into WhatsApp rather than sending it by email."""
    from app.core.config import settings
    token = create_password_set_token(user.id, expires_delta=expires_delta or _LINK_VALIDITY)
    is_student = "student" in user.role_values
    set_password_path = "/learn/set-password" if is_student else "/set-password"
    return f"{settings.FRONTEND_URL}{set_password_path}?token={token}"


async def send_set_password_email(
    user: User, *, purpose: str = "welcome", expires_delta: timedelta | None = None,
    audience: Literal["student", "judge", "portal"] = "portal", context: str | None = None,
) -> bool:
    """Public (P3-3, 2026-08-10) — was module-private until the student
    panel's "create account & invite" and "password reset" actions needed
    to call it directly, not just via `sync_registration_lms`. Same token
    mechanism either way (`create_password_set_token`, stateless) —
    `purpose` only changes the copy, since "an account was created for you"
    reads wrong for a reset on an account that already existed.

    `audience` picks the subject/intro copy from `_AUDIENCE_COPY` (2026-09-10)
    — callers that know who they're inviting (judge invites, the LMS
    welcome/reset flows) pass it explicitly; callers that don't (the public
    forgot-password endpoint, which serves every role from one form) leave
    it at the generic "portal" default rather than guessing from roles.

    `context` (2026-09-10) is the "you're registered for X" line — a
    Program/Cohort name string, when the caller has one (a registration or a
    judge invite always does; the dormant ops-desk contact endpoints don't).
    Only meaningful on `purpose="welcome"` — a reset has no registration
    event to announce, `_AUDIENCE_COPY[audience]["reset"]` is used as-is.

    `expires_delta` defaults to `_LINK_VALIDITY` (3 days) — the self-service
    "Forgot password?" flow (routers/auth.py::forgot_password) passes 24
    hours instead, since that's a link the requester is waiting on right
    now, not a "get to it whenever" invite."""
    from app.core.config import settings
    validity = expires_delta or _LINK_VALIDITY
    link = build_set_password_link(user, expires_delta=validity)
    # LearnSetPassword is mounted at both paths for exactly this reason (see
    # its own docstring) — a student's link should log them back in at
    # /learn/login, everyone else's at the portal /login, so `roleHomePath`
    # sends them somewhere real afterward instead of the LMS shell. The same
    # split decides the login link quoted in the email body below, since
    # it's the same "which shell does this account belong to" question.
    is_student = "student" in user.role_values
    login_path = "/learn/login" if is_student else "/login"
    login_link = f"{settings.FRONTEND_URL}{login_path}"
    copy = _AUDIENCE_COPY[audience]
    if purpose != "welcome":
        intro = copy["reset"]
    elif context:
        intro = copy["welcome_context"].format(context=context)
    else:
        intro = copy["welcome"]
    return await try_send_email(
        user.email,
        f"Your {copy['noun']}",
        (
            f"<p>Hi {user.full_name},</p>"
            f"<p>{intro}</p>"
            f'<p>Step 1: Set your password here: <a href="{link}">{link}</a></p>'
            f'<p>Step 2: Then log in at <a href="{login_link}">{login_link}</a></p>'
            f"<p>This link is valid for {_format_validity(validity)}.</p>"
            "<p>— SpacePoint</p>"
        ),
        html=True,
    )


async def send_registered_notice_email(
    user: User, *, audience: Literal["student", "judge"], context: str,
) -> bool:
    """The "you already have an account" sibling of send_set_password_email
    (2026-09-10) — no token, no password step, just a plain "you're
    registered for X, log in here" notice. Exists because an account that
    already exists getting silently re-added to a new cohort/judge roster
    previously sent nothing at all; every registration event should produce
    exactly one email regardless of whether the account behind it is new."""
    from app.core.config import settings
    is_student = "student" in user.role_values
    login_link = f"{settings.FRONTEND_URL}{'/learn/login' if is_student else '/login'}"
    copy = _REGISTERED_NOTICE_COPY[audience]
    return await try_send_email(
        user.email,
        copy["subject"].format(context=context),
        (
            f"<p>Hi {user.full_name},</p>"
            f"<p>{copy['intro'].format(context=context)}</p>"
            f'<p>Log in here: <a href="{login_link}">{login_link}</a></p>'
            "<p>— SpacePoint</p>"
        ),
        html=True,
    )


async def send_registration_onboarding_email(
    db: AsyncSession, *, user: User, registration: Registration, cohort: Cohort,
) -> bool:
    """Picks and sends the right onboarding email for one registration's
    student account — set-password if they still haven't set one
    (`must_change_password`, not "was the account just created": a bulk-
    imported account that's never been opened still needs the password
    step on a *later* registration too, not the bare login notice), the
    plain "you're registered" notice otherwise. Stamps
    `registration.onboarding_sent_at` on success — used both by
    `sync_registration_lms`'s automatic send and by the ops "resend
    onboarding email" action, so both paths share one stamping rule."""
    program = await db.get(Program, cohort.program_id)
    context = f"{program.name} ({cohort.name})" if program else cohort.name
    if user.must_change_password:
        sent = await send_set_password_email(user, audience="student", context=context)
    else:
        sent = await send_registered_notice_email(user, audience="student", context=context)
    if sent:
        registration.onboarding_sent_at = datetime.now(timezone.utc)
        await db.flush()
    return sent


async def sync_registration_lms(
    db: AsyncSession, *, registration: Registration, cohort: Cohort, create_account: bool,
    send_welcome_email: bool = True,
) -> User | None:
    """The D4 flow for one registration: find-or-create the student account,
    assign the cohort's LMS Program checklist if it has one (2026-08-21 —
    enrolls every course item and assigns every mission_run item's attempt
    immediately, same "enroll everything up front" behavior the old
    curriculum table had; a no-op when the cohort has no checklist at
    all), email the onboarding link via `send_registration_onboarding_email`.
    Never raises — an LMS-side hiccup must not break registration, mirroring
    issue_ticket()'s "return False, log it" discipline.

    `send_welcome_email=False` still creates the account (a caller that
    structurally needs a User back — e.g. adding someone to a competition
    team — can't skip that part) but suppresses the notification, for a
    caller sending its own combined notice or deliberately going quiet."""
    if not create_account:
        return None
    try:
        user, _created = await get_or_create_student_account(db, registration.contact_id)
        if user is None:
            return None
        await assign_lms_program(
            db, user_id=user.id, cohort_id=cohort.id, registration_id=registration.id,
        )
        if send_welcome_email:
            await send_registration_onboarding_email(db, user=user, registration=registration, cohort=cohort)
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
