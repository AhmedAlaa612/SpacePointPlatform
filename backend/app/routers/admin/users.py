"""Generic user management (PLAN §9.4) — not domain-specific, since the `users`
table is shared across all 8 roles.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["admin"])


@router.post("", response_model=UserOut)
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await user_service.create_user(db, user_in)


@router.get("", response_model=List[UserOut])
async def read_users(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await user_service.get_users(db)


@router.patch("/{id}", response_model=UserOut)
async def update_user(id: UUID, user_in: UserUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await user_service.update_user(db, id, user_in)


@router.delete("/{id}")
async def delete_user(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await user_service.delete_user(db, id)
