from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.ambassadors.points_transaction import PointsTransaction
from app.schemas.ambassadors.points import PointsTransactionOut

router = APIRouter(prefix="/points", tags=["ambassador-points"])


@router.get("/me", response_model=list[PointsTransactionOut])
async def my_points_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    rows = (await db.execute(
        select(PointsTransaction)
        .where(PointsTransaction.ambassador_id == current_user.id)
        .order_by(PointsTransaction.created_at.desc())
    )).scalars().all()
    return list(rows)
