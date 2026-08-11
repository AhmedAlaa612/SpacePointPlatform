from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


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


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme_optional), db: AsyncSession = Depends(get_db)
) -> User | None:
    """Same decode as get_current_user, but never raises — None for no token,
    a garbage token, or an unknown subject. For public endpoints that behave
    differently for a signed-in caller without *requiring* auth (B2:
    public_register reusing the caller's own contact_id instead of
    re-resolving identity from a re-typed email)."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        if sub is None or payload.get("type") != "access":
            return None
    except JWTError:
        return None
    return (await db.execute(select(User).where(User.id == sub))).scalars().first()


async def get_ws_user(token: str = Query(...), db: AsyncSession = Depends(get_db)) -> User | None:
    """WS-safe variant of get_current_user (Live Games Phase 2C, 8-5, D7).
    A browser `WebSocket()` can't send an `Authorization` header, so the
    token travels as a query param instead — same decode/claim checks as
    above, but never raises: an HTTPException doesn't render sensibly on
    an upgraded connection, so the route itself closes the socket (code
    1008) when this returns None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        if sub is None or payload.get("type") != "access":
            return None
    except JWTError:
        return None
    return (await db.execute(select(User).where(User.id == sub))).scalars().first()


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
require_instructor_or_facilitator = RequireRole(["instructor", "facilitator"])
require_ambassador = RequireRole(["ambassador"])
require_teacher = RequireRole(["teacher"])
require_operations = RequireRole(["operations"])  # V2 sessions/spine domains (R2-3+)

# ── Inventory phase (I0-2) ──────────────────────────────────────────────────
# `storekeeper` restocks kits, receives goods and records stock movements —
# and nothing else. The restriction is the point of the role: it must not
# reach session assignments, kit create/edit/delete, programs, cohorts,
# registrations or contacts. That is enforced by `require_operations` simply
# not listing it, so no extra machinery is needed.
#
# Operations is included here because ops can obviously also restock — the
# narrowness is the storekeeper's, not an exclusive claim on the action.
require_storekeeper = RequireRole(["storekeeper", "operations"])

# Approvals (purchases, cross-border transfers). `admin` passes every
# RequireRole check, which is exactly what "the CEO can approve in the COO's
# absence without changing the workflow" needs — no delegation table, no
# expiry. The approval record stores who actually signed.
require_inventory_approval = RequireRole(["coo"])
# W5 S5-1 — instructor delivery actions (start/attendance/done) are allowed
# for the assigned instructor/facilitator OR ops; the per-session assignment
# check itself (for the non-ops case) happens in services/sessions/delivery.py,
# not here — this dependency only gates "logged in as one of these roles".
require_session_delivery = RequireRole(["instructor", "facilitator", "operations"])

# I5-6 — teaching materials are maintained by ops, facilitators and admin
# (operator, 2026-07-30). Facilitators are included because they are the ones
# who actually write the material; plain instructors are not, so a session's
# files can't be changed by whoever happens to be teaching it that day.
require_materials_manager = RequireRole(["operations", "facilitator"])

# ── LMS phase (LM0-2) ───────────────────────────────────────────────────────
# `student` is a learner surface, not an ops account. It is deliberately absent
# from every guard above — `require_operations` rejecting it is the whole point
# of the role, and that negative is tested, not assumed (the I3-1 lesson).
#
# This dependency only answers "is this a learner account?". It does NOT answer
# "may this learner see this course" — that is `enrollments` (LMS D8), checked
# in services/lms/, because the answer is per-course and this is not.
require_lms_student = RequireRole(["student"])

# Authoring: ops and facilitators write course content, same split as
# require_materials_manager above (facilitators write the material; plain
# instructors don't, so a course can't be edited by whoever happens to be
# teaching it that day). admin passes, as everywhere.
require_lms_content = RequireRole(["operations", "facilitator"])
