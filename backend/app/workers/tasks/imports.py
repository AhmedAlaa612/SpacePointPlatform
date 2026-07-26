"""Throttled batch ticket-email dispatch for a committed import batch (V2 R2-2).

One ARQ job per batch, not one job per registration — it iterates and sends
with a small delay between each, rather than flooding the queue (and SMTP)
with N jobs firing all at once for a 50+ row sheet.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.sessions.import_batch import ImportBatch
from app.models.sessions.registration import Registration
from app.services.sessions.registration import issue_ticket

logger = logging.getLogger("workers.imports")

_THROTTLE_SECONDS = 0.2  # ~5/sec


async def send_import_batch_emails(ctx, batch_id: str) -> dict:
    sent = 0
    failed = 0
    async with AsyncSessionLocal() as db:
        batch = await db.get(ImportBatch, uuid.UUID(batch_id))
        if batch is None:
            logger.warning("send_import_batch_emails: batch %s not found", batch_id)
            return {"sent": 0, "failed": 0}

        contact_ids = {
            row["contact_id"] for row in batch.counts.get("rows", [])
            if row.get("contact_id") and row["disposition"] in ("create", "link")
        }
        if not contact_ids:
            return {"sent": 0, "failed": 0}

        result = await db.execute(
            select(Registration).where(
                Registration.cohort_id == batch.cohort_id,
                Registration.contact_id.in_(contact_ids),
            )
        )
        registrations = result.scalars().all()

        for i, registration in enumerate(registrations):
            ok = await issue_ticket(db, registration.id)
            await db.commit()
            sent += int(ok)
            failed += int(not ok)
            if i < len(registrations) - 1:
                await asyncio.sleep(_THROTTLE_SECONDS)

    return {"sent": sent, "failed": failed}
