from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.admin.overview import AdminCommandOverviewOut
from app.services.admin.overview import get_admin_command_overview

router = APIRouter()


@router.get("/overview", response_model=AdminCommandOverviewOut)
async def get_admin_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await get_admin_command_overview(db)
