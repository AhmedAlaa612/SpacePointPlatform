"""Bulk sheet importer endpoints (V2 R2-2). Mounted at /sessions/imports — no
/api prefix, matching this app's real convention (see routers/sessions/public.py)."""

import uuid
from typing import Literal

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.sessions.import_batch import ImportBatch
from app.models.user import User
from app.schemas.sessions.imports import ImportBatchListItem, ImportBatchOut
from app.services.sessions.importer import commit_batch, dry_run, generate_template_xlsx
from app.workers.settings import get_arq_redis, safe_enqueue

router = APIRouter(prefix="/sessions", tags=["sessions-imports"])


def _to_batch_out(batch: ImportBatch) -> ImportBatchOut:
    return ImportBatchOut(
        id=batch.id, source=batch.source, cohort_id=batch.cohort_id, filename=batch.filename,
        status=batch.status, summary=batch.counts.get("summary", {}), rows=batch.counts.get("rows", []),
        created_at=batch.created_at,
    )


@router.get("/imports/template")
async def download_template(current_user: User = Depends(require_operations)):
    return Response(
        content=generate_template_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=spacepoint_import_template.xlsx"},
    )


@router.get("/imports", response_model=list[ImportBatchListItem])
async def list_batches(
    cohort_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    query = select(ImportBatch).order_by(ImportBatch.created_at.desc())
    if cohort_id is not None:
        query = query.where(ImportBatch.cohort_id == cohort_id)
    result = await db.execute(query)
    batches = result.scalars().all()
    return [
        ImportBatchListItem(
            id=b.id, source=b.source, cohort_id=b.cohort_id, filename=b.filename,
            status=b.status, summary=b.counts.get("summary", {}), created_at=b.created_at,
        )
        for b in batches
    ]


@router.get("/imports/{batch_id}", response_model=ImportBatchOut)
async def get_batch(batch_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_operations)):
    batch = await db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Import batch not found")
    return _to_batch_out(batch)


@router.post("/imports/dry-run", response_model=ImportBatchOut)
async def upload_dry_run(
    cohort_id: uuid.UUID = Form(...),
    source: Literal["b2b_sheet", "backfill"] = Form(...),
    payment_status: str | None = Form(None),
    set_contact_organization: bool = Form(False),
    send_emails: bool = Form(False),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    file_bytes = await file.read()
    batch = await dry_run(
        db, file_bytes=file_bytes, cohort_id=cohort_id, uploaded_by=current_user.id, source=source,
        payment_status=payment_status, set_contact_organization=set_contact_organization,
        send_emails=send_emails, filename=file.filename or "upload.xlsx",
    )
    await db.commit()
    return _to_batch_out(batch)


@router.post("/imports/{batch_id}/commit", response_model=ImportBatchOut)
async def commit_import_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    batch = await commit_batch(db, batch_id)
    await db.commit()

    if batch.counts.get("options", {}).get("send_emails"):
        await safe_enqueue(arq_redis, "send_import_batch_emails", str(batch.id))

    return _to_batch_out(batch)
