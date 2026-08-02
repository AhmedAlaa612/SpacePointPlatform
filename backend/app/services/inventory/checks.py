"""The session loop: assigning kits to a session, and counting them before
and after (I2-1/I2-2).

The whole point of this module is that nobody maintains inventory. They finish
a workshop, and inventory falls out of it. The legacy system had a
check-in feature too — `cubesat_session_logs`, zero rows after thirteen
months — and the difference is not the form, it is that this one sits inside
something the instructor was already doing.

Two rules that look inconsistent and are not:

* **The post-session check hard-gates `mark_done`.** It is asynchronous, they
  have finished teaching, and there is a real incentive at the other end.
* **The pre-session check does not gate anything.** It happens live, in front
  of students, at the moment a workshop is supposed to start. Blocking that on
  a 27-item form gets the form faked or the system abandoned, and a survey
  everyone fakes is worse than no survey because you then trust bad data.
  Skipping is *recorded* instead, so a later shortage can still be read
  correctly.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.item import Item
from app.models.inventory.kit import Kit, KitItem
from app.models.inventory.kit_template import KitTemplateItem
from app.models.inventory.session_kit import KitCheck, SessionKit
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.services.inventory.cohort_kits import materialize_session_kits

CHECK_PHASES = {"pre", "post", "adhoc"}


async def assign_kits(
    db: AsyncSession, *, session_id: uuid.UUID, kit_ids: list[uuid.UUID], actor_user_id: uuid.UUID
) -> list[SessionKit]:
    """Earmark kits for a session. Idempotent — re-assigning an already
    assigned kit is a no-op rather than a 409, because the natural UI is a
    multi-select that resubmits the whole set."""
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, detail="Session not found")

    # First kit activity on this specific session copies the cohort's
    # current default in and makes this session independent of it from here
    # on (Phase 3 follow-up). A no-op for the universal case today — a
    # cohort with no default kit list.
    await materialize_session_kits(db, session=session, actor_user_id=actor_user_id)

    existing = {
        sk.kit_id: sk
        for sk in (await db.execute(
            select(SessionKit).where(SessionKit.session_id == session_id)
        )).scalars().all()
    }

    for kit_id in kit_ids:
        if kit_id in existing:
            continue
        if await db.get(Kit, kit_id) is None:
            raise HTTPException(404, detail="Kit not found")
        link = SessionKit(
            id=uuid.uuid4(), session_id=session_id, kit_id=kit_id, created_by=actor_user_id
        )
        db.add(link)
        existing[kit_id] = link

    await db.flush()
    return list(existing.values())


async def unassign_kit(
    db: AsyncSession, *, session_id: uuid.UUID, kit_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, detail="Session not found")

    # A kit that is only inherited from the cohort default has no row here
    # yet — materialize first so it does, then the lookup-and-delete below
    # is unchanged. From this point the session is independent of the
    # cohort default (Phase 3 follow-up). `actor_user_id` is optional here
    # only because materializing zero cohort-default kits (today's universal
    # case) never actually needs an attributable actor — it's required in
    # practice the moment a cohort has any default kits to copy.
    await materialize_session_kits(db, session=session, actor_user_id=actor_user_id)

    link = (await db.execute(
        select(SessionKit).where(SessionKit.session_id == session_id, SessionKit.kit_id == kit_id)
    )).scalars().first()
    if link is None:
        raise HTTPException(404, detail="That kit isn't assigned to this session")
    await db.delete(link)
    await db.flush()


async def assigned_kits(db: AsyncSession, session_id: uuid.UUID) -> list[Kit]:
    return (await db.execute(
        select(Kit).join(SessionKit, SessionKit.kit_id == Kit.id)
        .where(SessionKit.session_id == session_id).order_by(Kit.label)
    )).scalars().all()


async def kit_sessions(db: AsyncSession, kit_id: uuid.UUID) -> list[dict]:
    """Every session this kit has ever been earmarked for — past and future,
    the reverse of `assigned_kits`. Includes both explicit session assignments
    and cohort-level default kit inheritances. Ordered oldest first so a
    calendar view can split it on today's date without re-sorting."""
    from datetime import time
    from app.models.inventory.cohort_kit import CohortKit

    # 1. Explicitly assigned or materialized session kits
    explicit_rows = (await db.execute(
        select(SessionKit, Session, Cohort, Program)
        .join(Session, Session.id == SessionKit.session_id)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .where(SessionKit.kit_id == kit_id)
    )).all()

    sessions_map: dict[uuid.UUID, dict] = {}
    for session_kit, session, cohort, program in explicit_rows:
        sessions_map[session.id] = {
            "session_id": session.id,
            "cohort_id": cohort.id,
            "cohort_name": cohort.name,
            "program_name": program.name,
            "title": session.title or program.name,
            "meeting_date": session.meeting_date,
            "starts_at": session.starts_at,
            "return_status": session_kit.return_status,
            "received": session_kit.received_at is not None,
            "ops_confirmed": session_kit.ops_confirmed_at is not None,
        }

    # 2. Inherited cohort default kits (sessions where kits_overridden is False)
    cohort_inherited_rows = (await db.execute(
        select(Session, Cohort, Program)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .join(CohortKit, CohortKit.cohort_id == Cohort.id)
        .where(
            CohortKit.kit_id == kit_id,
            Session.kits_overridden.is_(False),
        )
    )).all()

    for session, cohort, program in cohort_inherited_rows:
        if session.id not in sessions_map:
            sessions_map[session.id] = {
                "session_id": session.id,
                "cohort_id": cohort.id,
                "cohort_name": cohort.name,
                "program_name": program.name,
                "title": session.title or program.name,
                "meeting_date": session.meeting_date,
                "starts_at": session.starts_at,
                "return_status": None,
                "received": False,
                "ops_confirmed": False,
            }

    results = list(sessions_map.values())
    results.sort(key=lambda s: (s["meeting_date"], s["starts_at"] or time.min))
    return results


async def expected_counts(db: AsyncSession, kit: Kit) -> list[dict]:
    """What to show on the check form: every line of the kit's template,
    prefilled with what we currently believe is in the box.

    Prefilled rather than blank so the common case is one tap. A form that
    demands 27 numbers gets 27 guesses.
    """
    rows = (await db.execute(
        select(KitTemplateItem, Item)
        .join(Item, Item.id == KitTemplateItem.item_id)
        .where(KitTemplateItem.template_id == kit.template_id)
        .order_by(Item.category, Item.name)
    )).all()

    held = dict((await db.execute(
        select(KitItem.item_id, KitItem.qty).where(KitItem.kit_id == kit.id)
    )).all())

    return [
        {
            "item_id": item.id,
            "item_name": item.name,
            "required": line.required_qty,
            "expected": held.get(item.id, 0),
        }
        for line, item in rows
    ]


async def record_check(
    db: AsyncSession,
    *,
    kit: Kit,
    phase: str,
    checked_by: uuid.UUID,
    counts: dict[uuid.UUID, int] | None = None,
    skipped: bool = False,
    session_id: uuid.UUID | None = None,
    note: str | None = None,
) -> KitCheck:
    """Record a count and update what we believe is in the kit.

    The counted numbers become the kit's contents — the person who just looked
    inside the box outranks the database. `missing` is computed here and
    stored, not recomputed on read.
    """
    if phase not in CHECK_PHASES:
        raise HTTPException(400, detail=f"Unknown check phase '{phase}'")

    if skipped:
        check = KitCheck(
            id=uuid.uuid4(), kit_id=kit.id, session_id=session_id, phase=phase,
            skipped=True, checked_by=checked_by, counts={}, missing={}, note=note,
        )
        db.add(check)
        await db.flush()
        return check

    counts = counts or {}
    if not counts:
        raise HTTPException(400, detail="Count something, or mark the check skipped")

    required = dict((await db.execute(
        select(KitTemplateItem.item_id, KitTemplateItem.required_qty)
        .where(KitTemplateItem.template_id == kit.template_id)
    )).all())

    missing: dict[str, int] = {}
    for item_id, counted in counts.items():
        if counted < 0:
            raise HTTPException(400, detail="A count cannot be negative")
        # The person looking in the box wins.
        row = (await db.execute(
            select(KitItem).where(KitItem.kit_id == kit.id, KitItem.item_id == item_id)
        )).scalars().first()
        if row is None:
            row = KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=item_id, qty=0)
            db.add(row)
        row.qty = counted

        short = required.get(item_id, 0) - counted
        if short > 0:
            missing[str(item_id)] = short

    check = KitCheck(
        id=uuid.uuid4(), kit_id=kit.id, session_id=session_id, phase=phase,
        skipped=False, checked_by=checked_by,
        counts={str(k): v for k, v in counts.items()},
        missing=missing, note=note,
    )
    db.add(check)
    await db.flush()
    return check


async def outstanding_post_checks(db: AsyncSession, session_id: uuid.UUID) -> list[Kit]:
    """Kits assigned to this session with no post-session check yet.

    This is what gates `mark_done`. An empty list means the session can be
    closed out; a non-empty one names exactly which boxes still need counting,
    rather than saying "something is missing" and leaving them to hunt.
    """
    kits = await assigned_kits(db, session_id)
    if not kits:
        return []

    checked = set((await db.execute(
        select(KitCheck.kit_id).where(
            KitCheck.session_id == session_id, KitCheck.phase == "post"
        )
    )).scalars().all())

    return [k for k in kits if k.id not in checked]


async def check_history(db: AsyncSession, kit_id: uuid.UUID) -> list[tuple[KitCheck, str | None]]:
    """Every count of this kit, newest first, with who did it."""
    rows = (await db.execute(
        select(KitCheck, User.full_name)
        .outerjoin(User, User.id == KitCheck.checked_by)
        .where(KitCheck.kit_id == kit_id)
        .order_by(KitCheck.created_at.desc())
    )).all()
    return [(check, name) for check, name in rows]
