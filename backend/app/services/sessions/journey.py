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

from app.models.instructors.payment import PaymentSession
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
    """The current responsibilities text and its version.

    The version is a hash of the text rather than a counter nobody remembers
    to bump: it changes exactly when the words change, and it lets an old
    acceptance prove *which* wording was agreed to.
    """
    text = await get_portal_setting(db, RESPONSIBILITIES_KEY, "") or ""
    return text, sha256(text.encode("utf-8")).hexdigest()[:16]


async def set_responsibilities(db: AsyncSession, text: str) -> tuple[str, str]:
    await set_portal_setting(db, RESPONSIBILITIES_KEY, text or "")
    return await get_responsibilities(db)


async def accept_responsibilities(
    db: AsyncSession, *, interest: InstructorInterest, version: str
) -> InstructorInterest:
    """Record the read-and-agree tick against the version that was on screen.

    Refusing a stale version is the point: if ops edits the wording while
    somebody has the invite open, the acceptance they submit is for text they
    never saw.
    """
    _text, current = await get_responsibilities(db)
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
    """
    billed = set((await db.execute(
        select(PaymentSession.session_id).where(PaymentSession.session_id.isnot(None))
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
