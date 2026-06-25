from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.services.ambassadors import stats as stats_service
from app.services.ambassadors import achievements
from app.services.points import lifetime_points
from app.services.ambassadors.titles import resolve_title_progress

router = APIRouter(prefix="/dashboard", tags=["ambassador-dashboard"])


@router.get("/stats")
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    amb_id = current_user.id
    overview = await stats_service.ambassador_overview(db, amb_id)

    points = await lifetime_points(db, amb_id)
    season_pts = await lifetime_points(db, amb_id, since=stats_service.season_start())
    title_info = await resolve_title_progress(db, points)

    full = await stats_service.leaderboard(db)
    season_full = await stats_service.leaderboard(db, since=stats_service.season_start())
    board = full[:10]
    season_board = season_full[:10]
    my_rank = next((i + 1 for i, r in enumerate(full) if r["id"] == str(amb_id)), len(full) + 1)

    badges = await achievements.list_for(db, amb_id)

    return {
        **overview,
        "points_balance": points,
        "season_points": season_pts,
        "my_rank": my_rank,
        "leaderboard": board,
        "season_leaderboard": season_board,
        "achievements": badges,
        **title_info,
    }
