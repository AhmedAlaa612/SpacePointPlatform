from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.sessions.dashboard import (
    DashboardRange,
    MilestoneKindFilter,
    OpsDashboardOut,
    OpsDashboardOverviewOut,
)
from app.services.sessions.dashboard import get_ops_dashboard, get_ops_dashboard_overview

router = APIRouter(prefix="/sessions", tags=["sessions-dashboard"])


def _require_ops_or_admin(current_user: User) -> None:
    roles = current_user.role_values
    if not ("operations" in roles or "admin" in roles):
        raise HTTPException(403, detail="Dashboard requires operations or admin role")


@router.get("/dashboard", response_model=OpsDashboardOut)
async def ops_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_ops_or_admin(current_user)
    return await get_ops_dashboard(db)


@router.get("/dashboard/overview", response_model=OpsDashboardOverviewOut)
async def ops_dashboard_overview(
    range: DashboardRange = Query("7d"),
    kind: MilestoneKindFilter = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_ops_or_admin(current_user)
    return await get_ops_dashboard_overview(
        db,
        range_key=range,
        kind=kind,
        page=page,
        page_size=page_size,
    )
