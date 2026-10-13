from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_program import WebsiteProgram
from app.schemas.website_program import WebsiteProgramOut, WebsiteProgramUpdate

router = APIRouter(prefix="/website", tags=["admin-website-programs"])


@router.get("/programs", response_model=list[WebsiteProgramOut])
async def list_website_programs(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    """All flagship programs, including unpublished (admin view)."""
    rows = (
        await db.execute(
            select(WebsiteProgram).order_by(WebsiteProgram.display_order, WebsiteProgram.title)
        )
    ).scalars().all()
    return rows


@router.put("/programs/{program_id}", response_model=WebsiteProgramOut)
async def update_website_program(
    program_id: UUID,
    body: WebsiteProgramUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(WebsiteProgram).where(WebsiteProgram.id == program_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Program not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row
