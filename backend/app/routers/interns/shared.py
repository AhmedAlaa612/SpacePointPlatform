from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.models.user import User
from app.core.dependencies import get_current_user
from app.schemas.user import UserOut, UserUpdate
from app.schemas.interns.team import TeamOut

from app.services import user as user_service
from app.services.interns import team as team_service

router = APIRouter(tags=["shared"])

@router.get("/users/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.patch("/users/me", response_model=UserOut)
async def update_users_me(user_in: UserUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # User can only update their own details, not role
    user_in.roles = None
    return await user_service.update_user(db, current_user.id, user_in)

@router.get("/teams/{id}/members", response_model=List[UserOut])
async def read_team_members(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    team = await team_service.get_team_by_id(db, id)
    return team.members
