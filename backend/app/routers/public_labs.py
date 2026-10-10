"""Public labs projects endpoint — no auth required.

Step 7 — labs.spacepoint.ae hydrates its project cards here. Unmigrated
(fresh table) reads as an empty list rather than a 500 so the labs page
keeps its built-in Miura-Ori card.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.website_labs import WebsiteLabProject
from app.schemas.website_labs import LabProjectOut

router = APIRouter(prefix="/public", tags=["public-labs"])


@router.get("/labs/projects", response_model=list[LabProjectOut])
async def list_public_lab_projects(db: AsyncSession = Depends(get_db)):
    try:
        rows = (
            await db.execute(
                select(WebsiteLabProject)
                .where(WebsiteLabProject.is_active.is_(True))
                .order_by(WebsiteLabProject.display_order, WebsiteLabProject.title)
            )
        ).scalars().all()
    except Exception:
        return []
    return rows
