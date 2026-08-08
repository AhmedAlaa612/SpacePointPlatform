"""Session-assignment email ARQ task (V2 W4 S4-2). Fetches everything the
email needs itself (session/cohort/program/user) since the caller only has
IDs to hand off — same shape as tickets.py's send_ticket_email.
"""

import logging
import uuid

from app.db.session import AsyncSessionLocal
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.services.email import send_call_invite_email, send_session_assignment_email
from app.services.sessions import staffing

logger = logging.getLogger("workers.staffing")


async def send_assignment_email(ctx, session_id: str, user_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        session = await db.get(Session, uuid.UUID(session_id))
        user = await db.get(User, uuid.UUID(user_id))
        if session is None or user is None:
            logger.warning("Assignment email skipped: session=%s user=%s not found", session_id, user_id)
            return False

        cohort = await db.get(Cohort, session.cohort_id)
        program = await db.get(Program, cohort.program_id) if cohort else None
        location = await staffing.resolve_session_location_display(db, session, cohort)

        sent = await send_session_assignment_email(
            to_email=user.email,
            name=user.full_name,
            program_name=program.name if program else "your session",
            meeting_date=session.meeting_date.isoformat(),
            location=location["name"],
            location_address=location["address"],
            location_maps_url=location["maps_url"],
        )
        if not sent:
            logger.warning("Assignment email did not send for session %s user %s", session_id, user_id)
        return sent


async def send_call_invite_emails(ctx, session_id: str, user_ids: list[str]) -> int:
    """One call, many targeted instructors — batched into a single task so
    opening a call with a dozen targets is one enqueue, not a dozen."""
    async with AsyncSessionLocal() as db:
        session = await db.get(Session, uuid.UUID(session_id))
        if session is None:
            logger.warning("Call invite email skipped: session=%s not found", session_id)
            return 0

        cohort = await db.get(Cohort, session.cohort_id)
        program = await db.get(Program, cohort.program_id) if cohort else None
        program_name = program.name if program else "a session"
        location = await staffing.resolve_session_location_display(db, session, cohort)

        sent_count = 0
        for user_id in user_ids:
            user = await db.get(User, uuid.UUID(user_id))
            if user is None:
                logger.warning("Call invite email skipped: user=%s not found", user_id)
                continue
            sent = await send_call_invite_email(
                to_email=user.email, name=user.full_name,
                program_name=program_name, meeting_date=session.meeting_date.isoformat(),
                location=location["name"],
                location_address=location["address"],
                location_maps_url=location["maps_url"],
            )
            if sent:
                sent_count += 1
            else:
                logger.warning("Call invite email did not send for session %s user %s", session_id, user_id)
        return sent_count
