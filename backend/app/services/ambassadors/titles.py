from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.ambassadors.title import Title


async def all_titles(db: AsyncSession, audience: Optional[str] = "ambassador") -> list[Title]:
    q = select(Title).order_by(Title.min_points.asc(), Title.sort_order.asc())
    if audience is not None:
        q = q.where(Title.audience == audience)
    result = await db.execute(q)
    return list(result.scalars().all())


def _title_dict(t: Optional[Title]) -> Optional[dict]:
    if not t:
        return None
    return {
        "id": str(t.id),
        "name": t.name,
        "min_points": t.min_points,
        "icon": t.icon,
        "color": t.color,
    }


async def resolve_title_progress(db: AsyncSession, points: int, audience: str = "ambassador") -> dict:
    """Given a lifetime points total, return the current + next title and
    progress toward the next one."""
    titles = await all_titles(db, audience)
    current = None
    nxt = None
    for t in titles:
        if points >= t.min_points:
            current = t
        elif nxt is None:
            nxt = t  # first title above current points
            break

    points_into = points - current.min_points if current else points
    span = (nxt.min_points - (current.min_points if current else 0)) if nxt else 0
    progress = round(min(1.0, points_into / span), 4) if span > 0 else (1.0 if not nxt else 0.0)

    return {
        "current_title": _title_dict(current),
        "next_title": _title_dict(nxt),
        "points_to_next": max(0, nxt.min_points - points) if nxt else 0,
        "progress_to_next": progress,
    }
