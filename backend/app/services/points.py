from datetime import datetime
from typing import Optional
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.ambassadors.points_transaction import PointsTransaction


async def award_points(db: AsyncSession, user_id: UUID, amount: int, reason: str) -> None:
    """Add lifetime points. Points only ever accrue. Part of caller's transaction."""
    if amount and amount > 0:
        db.add(PointsTransaction(ambassador_id=user_id, amount=amount, type="earn", reason=reason))


async def adjust_points(db: AsyncSession, user_id: UUID, amount: int, reason: str) -> None:
    """Record a points correction (e.g. reversing a mistaken lead conversion).
    `amount` may be negative. Part of caller's transaction."""
    if amount:
        db.add(PointsTransaction(ambassador_id=user_id, amount=amount, type="adjust", reason=reason))


async def lifetime_points(db: AsyncSession, user_id: UUID, since: Optional[datetime] = None) -> int:
    """Sum of points earned. Pass `since` to scope to a season/time window."""
    q = select(func.coalesce(func.sum(PointsTransaction.amount), 0)).where(
        PointsTransaction.ambassador_id == user_id
    )
    if since is not None:
        q = q.where(PointsTransaction.created_at >= since)
    result = await db.execute(q)
    return int(result.scalar() or 0)


async def get_setting_int(db: AsyncSession, key: str, default: int) -> int:
    from app.models.ambassadors.system_setting import SystemSetting
    result = await db.execute(select(SystemSetting.value).where(SystemSetting.key == key))
    row = result.scalar()
    try:
        return int(row) if row is not None else default
    except (ValueError, TypeError):
        return default
