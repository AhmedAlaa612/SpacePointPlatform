"""Server-side step gating per cohort (P7-7) — replaces Madar's
`page_access`. **S1 in the audit**: Madar's budget API endpoints had no
page-access dependency at all; only the HTML pages called `GET
/page-access/check/{page_key}` and hid themselves. A student who knew the
URL — or opened devtools — bypassed the entire instructor-paced release
mechanism. The whole feature was decorative at the API layer. Here the
gate is enforced where the write actually happens, not just in the UI.

Mission Setup / Components / CONOPS are never gated, same as Madar's
`ALWAYS_OPEN`. A missing gate row means locked, matching Madar's own
"defaults to locked" behavior for the five budget steps.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.design import Design, DesignStepGate
from app.models.sessions.registration import Registration
from app.models.user import User

GATED_STEPS = {"data_budget", "power_budget", "link_budget", "mass_budget", "cost_budget"}


async def resolve_student_cohort(db: AsyncSession, *, user_id: uuid.UUID) -> uuid.UUID | None:
    """The cohort a design's gating is scoped to: the student's most
    recent active registration, if any. NULL means never gated — a
    standalone attempt outside a workshop cohort, or a team attempt
    (resolving "the team's shared cohort" when members may span
    different ones is deliberately out of scope; team design missions
    are simply ungated for now)."""
    user = await db.get(User, user_id)
    if user is None or user.contact_id is None:
        return None
    reg = (await db.execute(
        select(Registration)
        .where(Registration.contact_id == user.contact_id, Registration.status.in_(["registered", "attended"]))
        .order_by(Registration.created_at.desc())
    )).scalars().first()
    return reg.cohort_id if reg else None


async def is_step_unlocked(db: AsyncSession, *, cohort_id: uuid.UUID | None, step_key: str) -> bool:
    if step_key not in GATED_STEPS or cohort_id is None:
        return True
    gate = await db.get(DesignStepGate, (cohort_id, step_key))
    return bool(gate and gate.is_unlocked)


async def assert_step_unlocked(db: AsyncSession, *, design: Design, step_key: str) -> None:
    if not await is_step_unlocked(db, cohort_id=design.cohort_id, step_key=step_key):
        raise HTTPException(403, detail=f"'{step_key}' is not unlocked yet for your cohort")
