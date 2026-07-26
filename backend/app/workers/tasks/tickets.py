"""Ticket-email ARQ task (V2 R2-1 — moves R1-4's synchronous send off the
request path). Reuses services.sessions.registration.issue_ticket() as-is —
the actual QR/email logic doesn't change, only how it gets invoked: a worker
process, with its own DB session, not the web request's session.
"""

import logging
import uuid

from app.db.session import AsyncSessionLocal
from app.services.sessions.registration import issue_ticket

logger = logging.getLogger("workers.tickets")


async def send_ticket_email(ctx, registration_id: str, force: bool = False) -> bool:
    async with AsyncSessionLocal() as db:
        sent = await issue_ticket(db, uuid.UUID(registration_id), force=force)
        await db.commit()
        if not sent:
            logger.warning("Ticket email did not send for registration %s", registration_id)
        return sent
