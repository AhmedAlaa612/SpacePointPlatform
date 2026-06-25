import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core.dependencies import get_current_active_user, require_admin
from app.models.user import User
from app.models.ambassadors.title import Title
from app.schemas.ambassadors.title import TitleOut, TitleCreate, TitleUpdate
from app.services.ambassadors.titles import all_titles

router = APIRouter(prefix="/titles", tags=["ambassador-titles"])


@router.get("", response_model=list[TitleOut])
async def list_titles(
    audience: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """No `audience` filter returns every ladder (the admin editor shows both)."""
    return await all_titles(db, audience)


@router.post("", response_model=TitleOut, status_code=201)
async def create_title(
    body: TitleCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    if body.audience not in ("ambassador", "teacher"):
        raise HTTPException(status_code=400, detail="audience must be 'ambassador' or 'teacher'")
    title = Title(**body.model_dump())
    db.add(title)
    await db.commit()
    await db.refresh(title)
    return title


@router.patch("/{title_id}", response_model=TitleOut)
async def update_title(
    title_id: uuid.UUID,
    body: TitleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    title = (await db.execute(select(Title).where(Title.id == title_id))).scalars().first()
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    data = body.model_dump(exclude_unset=True)
    if "audience" in data and data["audience"] not in ("ambassador", "teacher"):
        raise HTTPException(status_code=400, detail="audience must be 'ambassador' or 'teacher'")
    for k, v in data.items():
        setattr(title, k, v)
    await db.commit()
    await db.refresh(title)
    return title


@router.delete("/{title_id}")
async def delete_title(
    title_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    title = (await db.execute(select(Title).where(Title.id == title_id))).scalars().first()
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    await db.delete(title)
    await db.commit()
    return {"status": "deleted"}
