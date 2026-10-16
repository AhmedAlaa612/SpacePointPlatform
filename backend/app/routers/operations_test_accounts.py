"""Operations-scoped management & cascade deletion for @spacepoint.local test accounts."""

from datetime import timedelta
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_operations
from app.core.security import create_password_set_token
from app.db.session import get_db
from app.models.application import Application
from app.models.enums import UserRole
from app.models.user import User
from app.routers.admin.users import _attach_org_and_author
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import user as user_service
from app.services.test_account_cleanup import (
    assert_test_email_allowed,
    assert_test_user_allowed,
    cascade_delete_test_account,
)

router = APIRouter(prefix="/operations/test-accounts", tags=["operations-test-accounts"])


def _reject_admin_role(roles: list[UserRole] | None) -> None:
    if not roles:
        return
    role_strs = [r.value if isinstance(r, UserRole) else str(r) for r in roles]
    if "admin" in role_strs:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operations cannot assign or test the admin role.",
        )


@router.get("/users", response_model=List[UserOut])
async def list_test_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    domain_suffix = f"%@{settings.TEST_EMAIL_DOMAIN.strip().lower().lstrip('@')}"
    users = (
        await db.execute(
            select(User)
            .where(func.lower(User.email).like(domain_suffix))
            .order_by(User.created_at.desc())
        )
    ).scalars().all()

    out: list[UserOut] = []
    for u in users:
        if "admin" in u.role_values:
            continue
        row = UserOut.model_validate(u)
        out.append(await _attach_org_and_author(db, u, row))
    return out


@router.get("/applications")
async def list_test_applications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    domain_suffix = f"%@{settings.TEST_EMAIL_DOMAIN.strip().lower().lstrip('@')}"
    apps = (
        await db.execute(
            select(Application)
            .where(func.lower(Application.email).like(domain_suffix))
            .order_by(Application.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(a.id),
            "full_name": a.full_name,
            "email": a.email,
            "role": a.role,
            "status": a.status,
            "created_at": a.created_at,
        }
        for a in apps
    ]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_test_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    assert_test_email_allowed(user_in.email)
    _reject_admin_role(user_in.roles)
    user = await user_service.create_user(db, user_in)
    row = UserOut.model_validate(user)
    return await _attach_org_and_author(db, user, row)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_test_user(
    user_id: UUID,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    target = await user_service.get_user_by_id(db, user_id)
    assert_test_user_allowed(target)
    if user_in.email is not None:
        assert_test_email_allowed(user_in.email)
    _reject_admin_role(user_in.roles)
    updated = await user_service.update_user(db, user_id, user_in, actor_user_id=current_user.id)
    row = UserOut.model_validate(updated)
    return await _attach_org_and_author(db, updated, row)


@router.post("/users/{user_id}/reset-link")
async def generate_test_user_reset_link(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    target = await user_service.get_user_by_id(db, user_id)
    assert_test_user_allowed(target)
    token = create_password_set_token(target.id, expires_delta=timedelta(days=3))
    base = (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    return {
        "user_id": str(target.id),
        "email": target.email,
        "reset_url": f"{base}/set-password?token={token}",
    }


@router.delete("/users/{user_id}")
async def delete_test_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    return await cascade_delete_test_account(db, user_id=user_id)


@router.delete("/by-email")
async def delete_test_account_by_email(
    email: str = Query(..., description="Must end with @spacepoint.local"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    return await cascade_delete_test_account(db, email=email)
