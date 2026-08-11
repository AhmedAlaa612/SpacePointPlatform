"""Mission-manager scoped access (7B-7) — layered on top of the existing
role checks, not replacing them: staff (the same population
`require_lms_content` allows — operations, facilitator, admin) can always
manage any mission; a `mission_managers` row additionally lets one specific
user manage just that one mission. No FastAPI `Depends` factory here (the
codebase's existing convention for per-resource checks is an explicit
async helper called at the top of the route — see `_own_attempt` in
`routers/missions/student.py` — not a parameterized dependency), so this
matches that shape rather than inventing a new one.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.manager import MissionManager
from app.models.user import User

_STAFF_ROLES = {"operations", "facilitator"}


async def is_mission_manager(db: AsyncSession, *, mission_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = await db.get(MissionManager, (mission_id, user_id))
    return row is not None


async def require_mission_manager_or_staff(db: AsyncSession, *, mission_id: uuid.UUID, user: User) -> None:
    roles = user.role_values
    if "admin" in roles or _STAFF_ROLES & set(roles):
        return
    if await is_mission_manager(db, mission_id=mission_id, user_id=user.id):
        return
    raise HTTPException(403, detail="You don't manage this mission")
