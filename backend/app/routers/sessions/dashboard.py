from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_operations
from app.db.session import get_db
from app.models.user import User
from app.schemas.sessions.dashboard import OpsDashboardOut
from app.services.sessions.dashboard import get_ops_dashboard

router = APIRouter(prefix="/sessions", tags=["sessions-dashboard"])


@router.get("/dashboard", response_model=OpsDashboardOut)
async def ops_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    roles = current_user.role_values
    if not ("operations" in roles or "admin" in roles):
        raise HTTPException(403, detail="Dashboard requires operations or admin role")
    return await get_ops_dashboard(db)
