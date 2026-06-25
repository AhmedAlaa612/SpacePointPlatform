import uuid
import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core.dependencies import get_current_active_user, require_admin
from app.models.user import User
from app.models.ambassadors.badge_definition import BadgeDefinition
from app.schemas.ambassadors.badge import BadgeOut, BadgeCreate, BadgeUpdate, slugify
from app.services.ambassadors.achievements import CRITERIA_TYPES, CRITERIA_BY_AUDIENCE

router = APIRouter(prefix="/badges", tags=["ambassador-badges"])


@router.get("", response_model=list[BadgeOut])
async def list_badges(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_active_user)):
    rows = (await db.execute(
        select(BadgeDefinition).order_by(BadgeDefinition.sort_order.asc(), BadgeDefinition.threshold.asc())
    )).scalars().all()
    return list(rows)


@router.get("/criteria-types")
async def criteria_types(_: User = Depends(require_admin)):
    """Criteria available per badge audience."""
    return CRITERIA_BY_AUDIENCE


@router.post("", response_model=BadgeOut, status_code=201)
async def create_badge(body: BadgeCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    allowed = CRITERIA_BY_AUDIENCE.get(body.audience)
    if allowed is None:
        raise HTTPException(status_code=400, detail="audience must be 'ambassador' or 'teacher'")
    if body.criteria_type not in allowed:
        raise HTTPException(status_code=400, detail=f"criteria_type must be one of {allowed}")
    code = body.code or slugify(body.label)
    if (await db.execute(select(BadgeDefinition.id).where(BadgeDefinition.code == code))).first():
        code = f"{code}_{secrets.token_hex(2)}"
    badge = BadgeDefinition(
        code=code, label=body.label, description=body.description, icon=body.icon,
        criteria_type=body.criteria_type, threshold=body.threshold, sort_order=body.sort_order,
        audience=body.audience,
    )
    db.add(badge)
    await db.commit()
    await db.refresh(badge)
    return badge


@router.patch("/{badge_id}", response_model=BadgeOut)
async def update_badge(badge_id: uuid.UUID, body: BadgeUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    badge = (await db.execute(select(BadgeDefinition).where(BadgeDefinition.id == badge_id))).scalars().first()
    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")
    data = body.model_dump(exclude_unset=True)
    audience = data.get("audience", badge.audience)
    allowed = CRITERIA_BY_AUDIENCE.get(audience)
    if allowed is None:
        raise HTTPException(status_code=400, detail="audience must be 'ambassador' or 'teacher'")
    if data.get("criteria_type", badge.criteria_type) not in allowed:
        raise HTTPException(status_code=400, detail=f"criteria_type must be one of {allowed}")
    for k, v in data.items():
        setattr(badge, k, v)
    await db.commit()
    await db.refresh(badge)
    return badge


@router.delete("/{badge_id}")
async def delete_badge(badge_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    badge = (await db.execute(select(BadgeDefinition).where(BadgeDefinition.id == badge_id))).scalars().first()
    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")
    await db.delete(badge)
    await db.commit()
    return {"status": "deleted"}
