from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        if sub is None or payload.get("type") != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = (await db.execute(select(User).where(User.id == sub))).scalars().first()
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if "admin" not in current_user.role_values and current_user.status != "active":
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


class RequireRole:
    """Allows any of the listed roles. Admin always passes."""

    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    async def __call__(self, current_user: User = Depends(get_current_active_user)) -> User:
        roles = current_user.role_values
        if "admin" in roles:
            return current_user
        if not any(r in roles for r in self.allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Operation not permitted"
            )
        return current_user


require_admin = RequireRole(["admin"])
require_intern = RequireRole(["intern", "leader"])
require_leader = RequireRole(["leader"])
require_applicant = RequireRole(["applicant"])
require_instructor = RequireRole(["instructor"])
require_facilitator = RequireRole(["facilitator"])
require_ambassador = RequireRole(["ambassador"])
require_teacher = RequireRole(["teacher"])
