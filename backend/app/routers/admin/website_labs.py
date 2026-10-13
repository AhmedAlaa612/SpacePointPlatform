from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_labs import WebsiteLabProject
from app.schemas.website_labs import LabProjectCreate, LabProjectOut, LabProjectUpdate
from app.services.articles.markdown import slugify

router = APIRouter(prefix="/website", tags=["admin-website-labs"])


async def _unique_slug(db: AsyncSession, title: str, ignore_id: UUID | None = None) -> str:
    base = slugify(title)
    slug = base
    suffix = 2
    while True:
        stmt = select(WebsiteLabProject.id).where(WebsiteLabProject.slug == slug)
        if ignore_id is not None:
            stmt = stmt.where(WebsiteLabProject.id != ignore_id)
        if (await db.execute(stmt)).first() is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


@router.get("/labs", response_model=list[LabProjectOut])
async def list_lab_projects(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    rows = (
        await db.execute(
            select(WebsiteLabProject).order_by(
                WebsiteLabProject.display_order, WebsiteLabProject.title
            )
        )
    ).scalars().all()
    return rows


@router.post("/labs", response_model=LabProjectOut, status_code=status.HTTP_201_CREATED)
async def create_lab_project(
    body: LabProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    data = body.model_dump()
    data["slug"] = (data.get("slug") or "").strip() or await _unique_slug(db, data["title"])
    row = WebsiteLabProject(**data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/labs/{project_id}", response_model=LabProjectOut)
async def update_lab_project(
    project_id: UUID,
    body: LabProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (
        await db.execute(select(WebsiteLabProject).where(WebsiteLabProject.id == project_id))
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Lab project not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("slug"):
        data["slug"] = slugify(data["slug"])
    for field, value in data.items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/labs/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lab_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (
        await db.execute(select(WebsiteLabProject).where(WebsiteLabProject.id == project_id))
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Lab project not found")
    await db.delete(row)
    await db.commit()
    return None
