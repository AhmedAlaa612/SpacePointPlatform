from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.services.ambassadors import achievements as ach_service

router = APIRouter(prefix="/achievements", tags=["ambassador-achievements"])


@router.get("/me")
async def my_achievements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return await ach_service.list_for(db, current_user.id)
