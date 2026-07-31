"""Responsibilities acceptance (I5-5) and the sessions → payments bridge (I5-8).

Two ends of the same journey, kept together because both are about turning a
delivered session into something an instructor signs.
"""

import uuid
from datetime import datetime, timezone
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.payment import PaymentLetter, PaymentSession
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.services.sessions.openings import resolve_duration
from app.services.settings import get_portal_setting, set_portal_setting

RESPONSIBILITIES_KEY = "instructor.responsibilities"

# Shown under the responsibilities on every invite (§G). Static, not a
# negotiated term — it is a statement of how SpacePoint pays, and putting it
# in settings would invite it being edited per session, which it is not.
PAYMENT_TERMS_NOTE = "Standard payment is within 30 days of delivery."


async def get_responsibilities(db: AsyncSession) -> tuple[str, str]:
    """The general responsibilities text and its version — the part that
    applies regardless of which role someone is agreeing to (arrive on time,
    wear the branded shirt, that kind of thing). Editable by ops on its own;
    `get_responsibilities_for_role` is what an instructor actually reads.

    The version is a hash of the text rather than a counter nobody remembers
    to bump: it changes exactly when the words change, and it lets an old
    acceptance prove *which* wording was agreed to.
    """
    text = await get_portal_setting(db, RESPONSIBILITIES_KEY, "") or ""
    return text, sha256(text.encode("utf-8")).hexdigest()[:16]


async def set_responsibilities(db: AsyncSession, text: str) -> tuple[str, str]:
    await set_portal_setting(db, RESPONSIBILITIES_KEY, text or "")
    return await get_responsibilities(db)


async def get_responsibilities_for_role(
    db: AsyncSession, role_id: uuid.UUID | None
) -> tuple[str, str, str | None]:
    """What an instructor actually reads and agrees to: the general text plus
    that role's own description, if it has one. One combined block, one
    checkbox — not a generic agreement that says nothing about the job and a
    separate, unagreed-to role blurb next to it.

    `role_id=None` (a session with no configured openings) falls back to the
    general text alone, unchanged from before per-role responsibilities
    existed. The version is a hash of the *combination*, so editing either
    half invalidates a stale acceptance — same reasoning as the general-only
    version, just scoped to what this instructor was actually shown.
    """
    general, general_version = await get_responsibilities(db)
    role_desc: str | None = None
    role_name: str | None = None
    if role_id is not None:
        role = await db.get(DeliveryRole, role_id)
        if role is not None:
            role_desc = (role.description or "").strip() or None
            role_name = role.name

    if role_desc is None:
        # No role, or a role with nothing extra to say — text and version
        # are byte-identical to the general-only ones, so an acceptance
        # recorded before this role had its own text (or against a session
        # with no configured openings) still checks out.
        return general, general_version, role_name

    general_stripped = general.strip()
    text = f"{general_stripped}\n\n{role_desc}" if general_stripped else role_desc
    version = sha256(f"{role_id}\x1f{text}".encode("utf-8")).hexdigest()[:16]
    return text, version, role_name


async def accept_responsibilities(
    db: AsyncSession, *, interest: InstructorInterest, version: str
) -> InstructorInterest:
    """Record the read-and-agree tick against the version that was on screen.

    Scoped to the role on the interest itself (set at registration) — the
    instructor agreed to *that* role's combined text, not a generic one.
    Refusing a stale version is the point: if ops edits either half while
    somebody has the invite open, the acceptance they submit is for wording
    they never saw.
    """
    _text, current, _role_name = await get_responsibilities_for_role(db, interest.role_id)
    if version != current:
        raise HTTPException(
            409, detail="The responsibilities have changed — reload and read them again"
        )

    interest.responsibilities_accepted_at = datetime.now(timezone.utc)
    interest.responsibilities_version = version
    await db.flush()
    return interest


# ── I5-8: completed sessions prefill the payment letter ─────────────────────

async def unbilled_sessions(db: AsyncSession, instructor_user_id: uuid.UUID) -> list[dict]:
    """Completed sessions this person delivered that no payment line covers.

    "Unbilled" is derived from the absence of a `payment_sessions.session_id`
    pointing at it — which is also what stops the same session being billed
    twice, so there is no separate flag to keep honest.

    **Scoped to this instructor's own letters.** One session is routinely
    delivered by several people — `session_openings` exists precisely to offer
    "1 Lead Facilitator at 2000 and 2 Assistants at 400" — and each of them is
    paid separately. Asking globally whether a session had *ever* been billed
    made paying the lead silently delete it from the assistant's list, so the
    assistant could never be offered it again and nobody would see that it had
    gone missing.
    """
    billed = set((await db.execute(
        select(PaymentSession.session_id)
        .join(PaymentLetter, PaymentLetter.id == PaymentSession.payment_letter_id)
        .where(
            PaymentSession.session_id.isnot(None),
            PaymentLetter.instructor_user_id == instructor_user_id,
        )
    )).scalars().all())

    rows = (await db.execute(
        select(Session, Cohort, Program, DeliveryRole.name)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .join(SessionInstructor, SessionInstructor.session_id == Session.id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(
            SessionInstructor.user_id == instructor_user_id,
            Session.completed_at.isnot(None),
        )
        .order_by(Session.meeting_date.desc())
    )).all()

    out = []
    for session, cohort, program, role_name in rows:
        if session.id in billed:
            continue
        out.append({
            "session_id": session.id,
            # Formatted the way the document prints it, because that is what
            # the (String) payment line stores.
            "session_date": session.meeting_date.strftime("%d/%m/%Y"),
            "workshop_description": session.title or program.name,
            "role": role_name,
            "location": cohort.location,
            "duration_hours": float(await resolve_duration(db, session) or 0) or None,
            "cohort_name": cohort.name,
        })
    return out
