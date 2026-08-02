"""Cohort-level kit defaults (Phase 3 follow-up to the session kit loop,
I2-1/I2-2).

A cohort can define a default kit list. A session inherits that as its
provisional kit set until the session's own kit activity happens — ops
assigns/removes a kit directly on it, or an instructor receives/returns one
— at which point the cohort's current default is copied
("materialized") into real `SessionKit` rows for that one session, and from
then on that session is fully independent of the cohort default, even if the
cohort default changes later.

Same shape as `services/sessions/materials.py::resolve_for_session` — override,
not merge — just one tier shallower (cohort/session only, no program tier for
kits).
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.kit import Kit
from app.models.inventory.cohort_kit import CohortKit
from app.models.inventory.session_kit import SessionKit
from app.models.sessions.cohort import Cohort
from app.models.sessions.session import Session


async def set_cohort_kits(
    db: AsyncSession, *, cohort_id: uuid.UUID, kit_ids: list[uuid.UUID], actor_user_id: uuid.UUID
) -> list[CohortKit]:
    """Full resubmit, idempotent — same contract as `assign_kits` one level
    down: the UI is a multi-select that resubmits the whole set."""
    if await db.get(Cohort, cohort_id) is None:
        raise HTTPException(404, detail="Cohort not found")

    existing = {
        ck.kit_id: ck
        for ck in (await db.execute(
            select(CohortKit).where(CohortKit.cohort_id == cohort_id)
        )).scalars().all()
    }

    for kit_id in kit_ids:
        if kit_id in existing:
            continue
        if await db.get(Kit, kit_id) is None:
            raise HTTPException(404, detail="Kit not found")
        link = CohortKit(
            id=uuid.uuid4(), cohort_id=cohort_id, kit_id=kit_id, created_by=actor_user_id
        )
        db.add(link)
        existing[kit_id] = link

    await db.flush()
    return list(existing.values())


async def cohort_kit_ids(db: AsyncSession, cohort_id: uuid.UUID) -> list[uuid.UUID]:
    return list((await db.execute(
        select(CohortKit.kit_id).where(CohortKit.cohort_id == cohort_id)
    )).scalars().all())


async def cohort_kits(db: AsyncSession, cohort_id: uuid.UUID) -> list[Kit]:
    """Joined for display, ordered by label — mirrors `checks.py`'s
    `assigned_kits`."""
    return (await db.execute(
        select(Kit).join(CohortKit, CohortKit.kit_id == Kit.id)
        .where(CohortKit.cohort_id == cohort_id).order_by(Kit.label)
    )).scalars().all()


async def remove_cohort_kit(db: AsyncSession, *, cohort_id: uuid.UUID, kit_id: uuid.UUID) -> None:
    link = (await db.execute(
        select(CohortKit).where(CohortKit.cohort_id == cohort_id, CohortKit.kit_id == kit_id)
    )).scalars().first()
    if link is None:
        raise HTTPException(404, detail="That kit isn't in this cohort's default list")
    await db.delete(link)
    await db.flush()


async def resolve_session_kits(db: AsyncSession, session: Session) -> tuple[list[Kit], str]:
    """What this session's kit list actually is, and where it came from.

    If the session has its own kit activity (`kits_overridden`), that is
    final — the session's own `SessionKit` rows, `level="session"`, even if
    that is an empty list (ops deliberately cleared it). Otherwise, the
    cohort's current default, `level="cohort"` — or `([], "none")` if the
    cohort has no default of its own.

    `assigned_kits` is imported lazily, inside the function body, because
    `checks.py` imports `materialize_session_kits` from this module — a
    module-level import either way would be circular.
    """
    if session.kits_overridden:
        from app.services.inventory.checks import assigned_kits

        return await assigned_kits(db, session.id), "session"

    ids = await cohort_kit_ids(db, session.cohort_id)
    if not ids:
        return [], "none"

    return await cohort_kits(db, session.cohort_id), "cohort"


async def materialize_session_kits(
    db: AsyncSession, *, session: Session, actor_user_id: uuid.UUID
) -> None:
    """Copy the cohort's current default kits onto this one session, and
    make that permanent.

    No-op if `session.kits_overridden` is already True — materialization
    happens exactly once per session, on whatever kit activity touches it
    first. Otherwise, every kit in the cohort's default list gets a real
    `SessionKit` row (skipping any that already exist, to respect the
    `(session_id, kit_id)` unique constraint), and the flag flips to True
    regardless of how many kits the cohort actually had to copy — zero is a
    legitimate outcome (an unset cohort default), and the point of the flag
    is recording that this session's kit story has started, not how many
    rows came out of it.
    """
    if session.kits_overridden:
        return

    kit_ids = await cohort_kit_ids(db, session.cohort_id)
    if kit_ids:
        existing = set((await db.execute(
            select(SessionKit.kit_id).where(SessionKit.session_id == session.id)
        )).scalars().all())

        for kit_id in kit_ids:
            if kit_id in existing:
                continue
            db.add(SessionKit(
                id=uuid.uuid4(), session_id=session.id, kit_id=kit_id, created_by=actor_user_id
            ))

    session.kits_overridden = True
    await db.flush()
