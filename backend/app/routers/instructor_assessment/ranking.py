"""The configurable Priority Score weighting (2026-09) —
`/instructor-assessment/ranking/weights`. One `RankingWeightProfile` is
active at a time for now; this is deliberately a small settings surface
(a tab inside Delivery Settings), not a dedicated new feature — see
`app/models/instructor_assessment/ranking.py` for why the shape still
supports more later without a migration.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.instructor_assessment.ranking import RankingWeightProfile
from app.schemas.instructor_assessment import RankingWeightProfileIn, RankingWeightProfileOut

router = APIRouter(
    prefix="/instructor-assessment/ranking", tags=["instructor-assessment-ranking"],
    dependencies=[Depends(require_operations)],
)


def _out(profile: RankingWeightProfile) -> RankingWeightProfileOut:
    return RankingWeightProfileOut(
        id=profile.id, name=profile.name, factor_weights=profile.factor_weights,
        is_active=profile.is_active, updated_at=profile.updated_at,
    )


@router.get("/weights", response_model=RankingWeightProfileOut)
async def get_active_weights(db: AsyncSession = Depends(get_db)):
    profile = (await db.execute(
        select(RankingWeightProfile).where(RankingWeightProfile.is_active.is_(True))
    )).scalars().first()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No active ranking weight profile is configured")
    return _out(profile)


@router.put("/weights", response_model=RankingWeightProfileOut)
async def update_active_weights(body: RankingWeightProfileIn, db: AsyncSession = Depends(get_db)):
    """Edits the active profile in place — a name/weights change, not a new
    profile. Multiple named profiles (e.g. per program type) are a natural
    extension of this same table later, not a redesign."""
    profile = (await db.execute(
        select(RankingWeightProfile).where(RankingWeightProfile.is_active.is_(True))
    )).scalars().first()
    if profile is None:
        profile = RankingWeightProfile(id=uuid.uuid4(), is_active=True, name=body.name, factor_weights=body.factor_weights)
        db.add(profile)
    else:
        profile.name = body.name
        profile.factor_weights = body.factor_weights
    await db.commit()
    await db.refresh(profile)
    return _out(profile)
