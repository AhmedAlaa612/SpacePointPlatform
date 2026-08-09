from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
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


def create_video_token(user_id: Any, item_id: Any, expires_delta: timedelta | None = None) -> str:
    """Short-lived token scoping one student to one video item (LMS D2) — never
    a static URL. Deliberately its own "type" so it can't be replayed as an
    access/refresh token, and carries no roles claim (it authorizes nothing
    beyond this one item; the enrollment check still runs per request).

    The default must outlast the longest lecture *plus* any pause a student
    takes mid-way. It was 15 minutes, which silently broke every video longer
    than that: hls.js keeps fetching segments for the whole runtime, so the
    token aged out mid-playback, segments started 403-ing, and the student
    got a flat "playback failed" an hour into a course. Callers that want a
    tighter window still pass expires_delta."""
    payload = {
        "sub": str(user_id),
        "item_id": str(item_id),
        "exp": datetime.now(timezone.utc) + (expires_delta or timedelta(hours=4)),
        "type": "lms_video",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_video_token(token: str) -> tuple[str, str]:
    """Returns (user_id, item_id) as strings. Raises JWTError if invalid,
    expired, or not actually a video token."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("type") != "lms_video":
        raise JWTError("Not a video token")
    return payload["sub"], payload["item_id"]


def create_password_set_token(user_id: Any, expires_delta: timedelta | None = None) -> str:
    """LM1-7 / §8 Q5: the "invite sent" email link for ops-created LMS
    accounts (must_change_password=True). 24h — long enough for someone to
    open an email later the same day without leaving a permanent credential
    lying around in an inbox."""
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + (expires_delta or timedelta(hours=24)),
        "type": "password_set",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_password_set_token(token: str) -> str:
    """Returns the user_id. Raises JWTError if invalid, expired, or not
    actually a password-set token."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("type") != "password_set":
        raise JWTError("Not a password-set token")
    return payload["sub"]
