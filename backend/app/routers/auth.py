from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    Token,
    UserOut,
)
import secrets
from app.models.enums import UserRole
from app.models.ambassadors.teacher_application import TeacherApplication
from app.schemas.user import AmbassadorApply, TeacherApply
from app.services.notification import create_notification as notify

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> dict:
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "roles": user.role_values,
        "status": user.status,
        "must_change_password": user.must_change_password,
    }


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == data.email))).scalars().first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    roles = user.role_values
    if "admin" not in roles and user.status != "active":
        raise HTTPException(status_code=403, detail="Account is not active")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "access_token": create_access_token(user.id, roles),
        "refresh_token": create_refresh_token(user.id, roles),
        "token_type": "bearer",
        "user": _user_out(user),
    }


@router.post("/refresh", response_model=Token)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(data.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != "refresh" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Re-validate against the DB so deactivated users / role changes take effect
    # within the refresh window.
    user = (await db.execute(select(User).where(User.id == payload["sub"]))).scalars().first()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    roles = user.role_values
    if "admin" not in roles and user.status != "active":
        raise HTTPException(status_code=401, detail="Account is no longer active")

    return {
        "access_token": create_access_token(user.id, roles),
        "refresh_token": create_refresh_token(user.id, roles),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_active_user)):
    return _user_out(current_user)


@router.post("/logout")
async def logout():
    # Stateless JWT: the client discards its tokens. Endpoint kept for symmetry.
    return {"detail": "logged out"}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # First-login forced change skips the current-password check.
    if not current_user.must_change_password:
        if not data.current_password or not verify_password(
            data.current_password, current_user.password_hash
        ):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = get_password_hash(data.new_password)
    current_user.must_change_password = False
    await db.commit()
    return {"detail": "password updated"}


async def _email_taken(db: AsyncSession, email: str) -> bool:
    return (await db.execute(select(User.id).where(User.email == email))).first() is not None


@router.post("/apply", status_code=status.HTTP_201_CREATED)
async def apply_ambassador(payload: AmbassadorApply, db: AsyncSession = Depends(get_db)):
    """Public ambassador application. Starts as 'pending' for admin approval."""
    if await _email_taken(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        roles=[UserRole.ambassador],
        country=payload.country,
        invite_code=secrets.token_hex(4).upper(),
        status="pending",
    )
    db.add(user)

    # Notify admins
    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    for admin in admins:
        await notify(db, admin.id, "New Ambassador Application", f"{payload.full_name} applied as an ambassador.")

    await db.commit()
    await db.refresh(user)
    return _user_out(user)


@router.post("/teacher-apply", status_code=status.HTTP_201_CREATED)
async def teacher_apply(payload: TeacherApply, db: AsyncSession = Depends(get_db)):
    """Public teacher application via an ambassador's invite code."""
    if await _email_taken(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    # Find ambassador
    amb = (await db.execute(
        select(User).where(
            User.invite_code == payload.invite_code,
            User.roles.any("ambassador"),
            User.status == "active",
        )
    )).scalars().first()
    if not amb:
        raise HTTPException(status_code=400, detail="Invalid or inactive invite code")

    # Check duplicate app
    dup = (await db.execute(
        select(TeacherApplication.id).where(
            TeacherApplication.email == payload.email,
            TeacherApplication.invited_by_id == amb.id,
            TeacherApplication.status == "pending"
        )
    )).first()
    if dup:
        raise HTTPException(status_code=400, detail="You have already applied via this ambassador")

    app = TeacherApplication(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        invite_code=payload.invite_code,
        invited_by_id=amb.id,
        answers=payload.answers,
        status="pending",
    )
    db.add(app)

    # Notify the ambassador
    await notify(db, amb.id, "New Teacher Application",
                 f"{payload.full_name} applied as a teacher with your invite code — review them in Network.")

    await db.commit()
    await db.refresh(app)
    return {"id": str(app.id), "email": app.email, "status": app.status}


@router.get("/invite/{code}")
async def validate_invite(code: str, db: AsyncSession = Depends(get_db)):
    amb = (await db.execute(
        select(User).where(
            User.invite_code == code,
            User.roles.any("ambassador"),
            User.status == "active"
        )
    )).scalars().first()
    if not amb:
        raise HTTPException(status_code=404, detail="Invalid or inactive invite code")
    return {"ambassador_name": amb.full_name, "valid": True}
