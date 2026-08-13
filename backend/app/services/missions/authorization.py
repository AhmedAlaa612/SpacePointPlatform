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


async def require_design_library_editor(db: AsyncSession, *, user: User) -> None:
    """Who may edit the shared CubeSat component library (Design v2, D7).

    Staff always. Plus **anyone who manages any `design`-kind mission** —
    the operator's explicit call, overriding the safer staff-only
    recommendation, on the grounds that content volume is the real
    bottleneck (the same reasoning behind the intern pipeline in D7 of the
    Phase 2B plan).

    Worth naming the trade this accepts, because it is not obvious from the
    code: `design_component_library` has no `mission_id`. It is one global
    catalog shared by every design mission, so an edit made by one
    mission's manager is seen by all of them. Finished designs are safe —
    `DesignComponent` froze their specs at add time (F2) — but a live,
    in-progress design picks up the new value for any field the student has
    not overridden. The bounding safeguards are retire-not-delete and the
    `updated_by` audit trail, both enforced in `routers/missions/library.py`.
    """
    roles = user.role_values
    if "admin" in roles or _STAFF_ROLES & set(roles):
        return

    from app.models.missions.mission import Mission
    from sqlalchemy import select

    manages_a_design = await db.scalar(
        select(MissionManager.mission_id)
        .join(Mission, Mission.id == MissionManager.mission_id)
        .where(MissionManager.user_id == user.id, Mission.kind == "design")
        .limit(1)
    )
    if manages_a_design is not None:
        return
    raise HTTPException(403, detail="Only staff and design-mission managers can edit the component library")
