"""Notify everyone who registered interest in a cohort once it opens
(2026-08-07) — mirrors send_import_batch_emails's throttled-loop shape.

Sets each row's `notified_at` only on a successful send, same convention as
issue_ticket's `ticket_sent_at` (registration.py): a failed send must stay
retryable on the next run (e.g. SMTP was down when a cohort first opened),
never silently marked "done" — the row would otherwise get skipped by the
`notified_at IS NULL` filter forever with no interested contact ever emailed.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_interest import CohortInterest
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.services.email import send_cohort_interest_notification_email

logger = logging.getLogger("workers.cohort_interest")

_THROTTLE_SECONDS = 0.2  # ~5/sec, same pacing as send_import_batch_emails


async def send_cohort_interest_notifications(ctx, cohort_id: str) -> dict:
    sent = 0
    failed = 0
    async with AsyncSessionLocal() as db:
        cohort = await db.get(Cohort, uuid.UUID(cohort_id))
        if cohort is None:
            logger.warning("send_cohort_interest_notifications: cohort %s not found", cohort_id)
            return {"sent": 0, "failed": 0}
        program = await db.get(Program, cohort.program_id)
        program_name = program.name if program else "your program"

        rows = (await db.execute(
            select(CohortInterest).where(
                CohortInterest.cohort_id == cohort.id, CohortInterest.notified_at.is_(None),
            )
        )).scalars().all()
        if not rows:
            return {"sent": 0, "failed": 0}

        for i, row in enumerate(rows):
            contact = await db.get(Contact, row.contact_id)
            ok = False
            if contact and contact.email:
                ok = await send_cohort_interest_notification_email(contact.email, contact.full_name, program_name)
            if ok:
                row.notified_at = datetime.now(timezone.utc)
            await db.commit()
            sent += int(ok)
            failed += int(not ok)
            if i < len(rows) - 1:
                await asyncio.sleep(_THROTTLE_SECONDS)

    return {"sent": sent, "failed": failed}
