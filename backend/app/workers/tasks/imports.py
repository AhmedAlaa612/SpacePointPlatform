"""Throttled batch ticket-email dispatch for a committed import batch (V2 R2-2).

One ARQ job per batch, not one job per registration — it iterates and sends
with a small delay between each, rather than flooding the queue (and SMTP)
with N jobs firing all at once for a 50+ row sheet.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.db.session import AsyncSessionLocal
from app.models.sessions.cohort import Cohort
from app.models.sessions.import_batch import ImportBatch
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.services.competitions.registration_import import (
    _import_row,
    results_as_dicts,
    summarize,
)
from app.services.lms.ops_integration import (
    resolve_user_for_contact,
    send_registration_onboarding_email,
)
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


async def run_competition_registration_import_job(ctx, batch_id: str) -> dict:
    """ARQ background job for competition roster import:
    1. Creates/matches contacts, student accounts, LMS program assignments,
       registrations, and teams for all rows in the batch.
    2. Commits all DB records first so account/team creation is never held
       hostage by slow SMTP servers.
    3. Dispatches welcome/onboarding emails and ticket emails with throttling.
    """
    try:
        async with AsyncSessionLocal() as db:
            batch = await db.get(ImportBatch, uuid.UUID(batch_id))
            if batch is None:
                logger.warning("run_competition_registration_import_job: batch %s not found", batch_id)
                return {"status": "not_found"}

            cohort = await db.get(Cohort, batch.cohort_id) if batch.cohort_id else None
            if cohort is None:
                batch.status = "failed"
                batch.counts = {**(batch.counts or {}), "error": "Cohort not found"}
                flag_modified(batch, "counts")
                await db.commit()
                return {"status": "failed", "error": "Cohort not found"}

            rows_in = (batch.counts or {}).get("rows_in", [])
            options = (batch.counts or {}).get("options", {})
            send_welcome_email = bool(options.get("send_welcome_email", True))
            send_ticket_email = bool(options.get("send_ticket_email", True))

            batch.status = "running"
            batch.counts = {
                **(batch.counts or {}),
                "progress": {"processed": 0, "total": len(rows_in)},
            }
            flag_modified(batch, "counts")
            await db.commit()

            results = []
            for idx, entry in enumerate(rows_in):
                res = await _import_row(
                    db,
                    row_number=entry["row_number"],
                    raw=entry["raw"],
                    cohort=cohort,
                    # Defer SMTP sends until after all DB records are committed
                    send_welcome_email=False,
                )
                results.append(res)
                if (idx + 1) % 10 == 0 or (idx + 1) == len(rows_in):
                    batch.counts = {
                        **(batch.counts or {}),
                        "progress": {"processed": idx + 1, "total": len(rows_in)},
                    }
                    flag_modified(batch, "counts")
                    await db.commit()

            summary = summarize(results)
            out_rows = [
                {k: v for k, v in r.items() if k != "registration_id"}
                for r in results_as_dicts(results)
            ]
            created_reg_ids = [
                r.registration_id
                for r in results
                if r.disposition == "created" and r.registration_id is not None
            ]

            # Mark committed right after DB rows land so the UI can show
            # completion immediately while throttled emails finish in background.
            batch.status = "committed"
            batch.counts = {
                **(batch.counts or {}),
                "summary": summary,
                "rows": out_rows,
                "progress": {"processed": len(rows_in), "total": len(rows_in)},
            }
            flag_modified(batch, "counts")
            await db.commit()

            welcome_sent = 0
            tickets_sent = 0
            if (send_welcome_email or send_ticket_email) and created_reg_ids:
                for i, reg_id in enumerate(created_reg_ids):
                    reg = await db.get(Registration, reg_id)
                    if reg is None:
                        continue
                    if send_welcome_email and reg.onboarding_sent_at is None:
                        contact = await db.get(Contact, reg.contact_id) if reg.contact_id else None
                        user = await resolve_user_for_contact(db, contact) if contact else None
                        if user is not None:
                            ok_welcome = await send_registration_onboarding_email(
                                db, user=user, registration=reg, cohort=cohort,
                            )
                            welcome_sent += int(bool(ok_welcome))
                    if send_ticket_email:
                        ok_ticket = await issue_ticket(db, reg_id)
                        tickets_sent += int(bool(ok_ticket))
                    await db.commit()
                    if i < len(created_reg_ids) - 1:
                        await asyncio.sleep(_THROTTLE_SECONDS)

            batch.status = "committed"
            batch.counts = {
                **(batch.counts or {}),
                "summary": summary,
                "rows": out_rows,
                "progress": {"processed": len(rows_in), "total": len(rows_in)},
                "emails": {"welcome_sent": welcome_sent, "tickets_sent": tickets_sent},
            }
            flag_modified(batch, "counts")
            await db.commit()
            return {"status": "committed", "summary": summary}
    except Exception as exc:
        logger.exception("run_competition_registration_import_job failed for batch %s: %s", batch_id, exc)
        try:
            async with AsyncSessionLocal() as db:
                batch = await db.get(ImportBatch, uuid.UUID(batch_id))
                if batch is not None:
                    batch.status = "failed"
                    batch.counts = {**(batch.counts or {}), "error": str(exc)}
                    flag_modified(batch, "counts")
                    await db.commit()
        except Exception:
            logger.exception("Could not record failure state on batch %s", batch_id)
        return {"status": "failed", "error": str(exc)}

