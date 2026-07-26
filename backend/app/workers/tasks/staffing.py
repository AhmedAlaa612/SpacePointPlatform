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
from app.services.email import send_session_assignment_email

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

        sent = await send_session_assignment_email(
            to_email=user.email,
            name=user.full_name,
            program_name=program.name if program else "your session",
            meeting_date=session.meeting_date.isoformat(),
            location=cohort.location if cohort else None,
        )
        if not sent:
            logger.warning("Assignment email did not send for session %s user %s", session_id, user_id)
        return sent
