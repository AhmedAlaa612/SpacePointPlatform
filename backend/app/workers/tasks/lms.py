"""LMS worker jobs: video transcode (LM1-6) + import-batch account sync (LM1-7).

`sync_import_batch_lms_accounts` mirrors `workers/tasks/imports.py`'s
`send_import_batch_emails` exactly — same contact_id lookup off the committed
batch, same "one job per batch, driven off real commit" shape — so LMS
account creation never runs inside the importer's rolled-back dry-run
SAVEPOINT (services/sessions/importer.py's whole design point).
"""

import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.sessions.cohort import Cohort
from app.models.sessions.import_batch import ImportBatch
from app.models.sessions.registration import Registration
from app.services.lms.ops_integration import sync_registration_lms
from app.services.lms.video import run_transcode


async def transcode_lms_video(ctx, item_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        await run_transcode(db, uuid.UUID(item_id))
    return {"item_id": item_id}


async def sync_import_batch_lms_accounts(ctx, batch_id: str) -> dict:
    synced = 0
    async with AsyncSessionLocal() as db:
        batch = await db.get(ImportBatch, uuid.UUID(batch_id))
        if batch is None:
            return {"synced": 0}
        cohort = await db.get(Cohort, batch.cohort_id)
        if cohort is None:
            return {"synced": 0}

        contact_ids = {
            row["contact_id"] for row in batch.counts.get("rows", [])
            if row.get("contact_id") and row["disposition"] in ("create", "link")
        }
        if not contact_ids:
            return {"synced": 0}

        registrations = (await db.execute(
            select(Registration).where(
                Registration.cohort_id == batch.cohort_id,
                Registration.contact_id.in_(contact_ids),
            )
        )).scalars().all()

        for registration in registrations:
            user = await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=True)
            await db.commit()
            synced += int(user is not None)

    return {"synced": synced}
