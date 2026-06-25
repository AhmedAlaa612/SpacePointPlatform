import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.ambassadors.material import Material
from app.schemas.ambassadors.material import MaterialCreate, MaterialUpdate, MaterialOut

router = APIRouter(prefix="/materials", tags=["ambassador-materials"])


def _can_manage(user: User) -> bool:
    return any(r in user.role_values for r in ("admin", "ambassador"))


async def _get_editable(db: AsyncSession, material_id: uuid.UUID, user: User) -> Material:
    mat = (await db.execute(select(Material).where(Material.id == material_id))).scalars().first()
    if not mat:
        raise HTTPException(status_code=404, detail="Material not found")
    if "admin" not in user.role_values and mat.created_by != user.id:
        raise HTTPException(status_code=403, detail="Only the uploader or an admin can do this")
    return mat


@router.get("", response_model=list[MaterialOut])
async def list_materials(
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Library is readable by every active user (teachers browse, managers curate)."""
    stmt = (
        select(Material, User.full_name)
        .outerjoin(User, Material.created_by == User.id)
        .order_by(Material.created_at.desc())
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Material.title.ilike(like) | Material.description.ilike(like) | Material.category.ilike(like))
    rows = (await db.execute(stmt)).all()
    out = []
    for mat, uploader in rows:
        d = MaterialOut.model_validate(mat)
        d.created_by_name = uploader
        out.append(d)
    return out


@router.post("", response_model=MaterialOut, status_code=201)
async def create_material(
    body: MaterialCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _can_manage(current_user):
        raise HTTPException(status_code=403, detail="Only admins and ambassadors can add materials")
    link = (body.link or "").strip()
    if not link:
        raise HTTPException(status_code=400, detail="A link is required")
    mat = Material(
        created_by=current_user.id,
        title=body.title.strip(),
        description=(body.description or "").strip() or None,
        link=link,
        category=(body.category or "").strip() or None,
    )
    db.add(mat)
    await db.commit()
    await db.refresh(mat)
    result = MaterialOut.model_validate(mat)
    result.created_by_name = current_user.full_name
    return result


@router.patch("/{material_id}", response_model=MaterialOut)
async def update_material(
    material_id: uuid.UUID,
    body: MaterialUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    mat = await _get_editable(db, material_id, current_user)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(mat, k, v)
    await db.commit()
    await db.refresh(mat)
    return MaterialOut.model_validate(mat)


@router.delete("/{material_id}")
async def delete_material(
    material_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    mat = await _get_editable(db, material_id, current_user)
    await db.delete(mat)
    await db.commit()
    return {"status": "deleted"}
