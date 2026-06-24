from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _encode(subject: Any, roles: list[str], token_type: str, expires: timedelta) -> str:
    # `roles` carries the full array — the active role is a client-side concept only.
    payload = {
        "sub": str(subject),
        "roles": roles,
        "exp": datetime.now(timezone.utc) + expires,
        "type": token_type,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: Any, roles: list[str], expires_delta: timedelta | None = None) -> str:
    return _encode(
        subject,
        roles,
        "access",
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(subject: Any, roles: list[str], expires_delta: timedelta | None = None) -> str:
    # The "type" claim keeps access tokens from being replayed as refresh tokens.
    return _encode(
        subject,
        roles,
        "refresh",
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
