from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.models.user import User
from app.core.dependencies import get_current_user
from app.schemas.notification import NotificationOut
from app.services import notification as notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/me", response_model=List[NotificationOut])
async def read_my_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await notification_service.get_notifications(db, current_user.id)


@router.patch("/{id}/read", response_model=NotificationOut)
async def mark_notification_read(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await notification_service.mark_read(db, id, current_user.id)


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await notification_service.mark_all_read(db, current_user.id)
    return {"detail": "All notifications marked as read"}
