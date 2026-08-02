"""Duration, delivery roles, openings and add-ons (I5-2 … I5-4, §G-addons).

Four small pieces of the instructor journey that share a table or two, kept
together because splitting them would mean four modules importing each other.

Services raise `HTTPException` directly — house convention, no domain-exception
layer.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.opening import SessionAddon, SessionOpening
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User

ADDON_SOURCES = {"offer", "interest", "invite", "survey", "payment"}
ADDON_STATUSES = {"proposed", "agreed", "declined"}

# Anything ops offers is already agreed; anything an instructor raises is a
# request. This mapping *is* the approval rule (§G-addons).
_OPS_SOURCES = {"offer", "invite", "payment"}


# ── I5-2: duration ──────────────────────────────────────────────────────────

async def resolve_duration(db: AsyncSession, session: Session) -> Decimal | None:
    """Session → cohort → program, first non-NULL wins.

    Same three-level fallback the operator asked for, and the same shape
    `price` already uses. Returns None when nobody has set it anywhere, which
    is honest — the payment line then stays blank rather than printing a
    guessed number on a document someone signs.
    """
    if session.duration_hours is not None:
        return session.duration_hours

    cohort = await db.get(Cohort, session.cohort_id)
    if cohort is None:
        return None
    if cohort.duration_hours is not None:
        return cohort.duration_hours

    program = await db.get(Program, cohort.program_id)
    return program.duration_hours if program else None


# ── I5-3: delivery roles ────────────────────────────────────────────────────

async def list_roles(db: AsyncSession, *, include_inactive: bool = False) -> list[DeliveryRole]:
    stmt = select(DeliveryRole).order_by(DeliveryRole.sort_order, DeliveryRole.name)
    if not include_inactive:
        stmt = stmt.where(DeliveryRole.is_active.is_(True))
    return (await db.execute(stmt)).scalars().all()


async def create_role(
    db: AsyncSession, *, name: str, description: str | None = None, sort_order: int | None = None,
) -> DeliveryRole:
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, detail="A role needs a name")

    clash = (await db.execute(
        select(DeliveryRole.id).where(func.lower(DeliveryRole.name) == name.lower())
    )).first()
    if clash:
        raise HTTPException(409, detail="A role with that name already exists")

    if sort_order is None:
        highest = await db.scalar(select(func.max(DeliveryRole.sort_order)))
        sort_order = (highest or 0) + 1

    role = DeliveryRole(
        id=uuid.uuid4(), name=name, description=description, sort_order=sort_order, is_active=True,
    )
    db.add(role)
    await db.flush()
    return role


async def update_role(
    db: AsyncSession, *, role: DeliveryRole,
    name: str | None = None, description: str | None = None,
    sort_order: int | None = None, is_active: bool | None = None,
) -> DeliveryRole:
    """Renaming is safe by design: `payment_sessions.role` snapshots the name
    at the time, so a signed letter keeps saying what it said."""
    if description is not None:
        role.description = description
    if name is not None:
        name = name.strip()
        if not name:
            raise HTTPException(400, detail="A role needs a name")
        clash = (await db.execute(
            select(DeliveryRole.id).where(
                func.lower(DeliveryRole.name) == name.lower(), DeliveryRole.id != role.id
            )
        )).first()
        if clash:
            raise HTTPException(409, detail="A role with that name already exists")
        role.name = name

    if sort_order is not None:
        role.sort_order = sort_order

    if is_active is False:
        in_use = await db.scalar(
            select(func.count()).select_from(SessionInstructor)
            .where(SessionInstructor.role_id == role.id)
        )
        remaining = await db.scalar(
            select(func.count()).select_from(DeliveryRole)
            .where(DeliveryRole.is_active.is_(True), DeliveryRole.id != role.id)
        )
        if not remaining:
            raise HTTPException(409, detail="That's the last active role — add another first")
        # Deactivating with assignments is allowed: it stops *new* ones while
        # history keeps resolving. Deleting would not, which is why there is
        # no delete.
        role.is_active = False
    elif is_active is True:
        role.is_active = True

    await db.flush()
    return role


async def lead_role_id(db: AsyncSession) -> uuid.UUID | None:
    """The most senior role — lowest `sort_order`.

    Everything that used to mean `role == "lead"` reads this instead, so
    renaming a role or inserting one above it doesn't break the notion of who
    is in charge. Used by the default assignment role and by inventory's
    "hand the kits to the lead instructor".
    """
    return await db.scalar(
        select(DeliveryRole.id)
        .where(DeliveryRole.is_active.is_(True))
        .order_by(DeliveryRole.sort_order)
        .limit(1)
    )


async def session_lead_user_id(db: AsyncSession, session_id: uuid.UUID) -> uuid.UUID | None:
    """Who is most senior on this session — by role seniority, not by name."""
    return await db.scalar(
        select(SessionInstructor.user_id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(SessionInstructor.session_id == session_id)
        .order_by(DeliveryRole.sort_order)
        .limit(1)
    )


# ── I5-4: openings ──────────────────────────────────────────────────────────

async def set_openings(
    db: AsyncSession, *, session_id: uuid.UUID, lines: list[dict], actor_user_id: uuid.UUID
) -> list[SessionOpening]:
    """Replace the whole set of openings for a session.

    Whole-set rather than per-line editing, the same choice as
    `PUT /templates/{id}/items`: a client never has to diff, and a
    half-applied edit can't leave a session advertising a role it doesn't
    want. Removing an opening that people are already assigned to is refused
    — the assignment is the thing that would be silently orphaned.
    """
    if await db.get(Session, session_id) is None:
        raise HTTPException(404, detail="Session not found")

    existing = {
        o.role_id: o for o in (await db.execute(
            select(SessionOpening).where(SessionOpening.session_id == session_id)
        )).scalars().all()
    }
    wanted_role_ids = {line["role_id"] for line in lines}

    assigned_by_role = dict((await db.execute(
        select(SessionInstructor.role_id, func.count())
        .where(SessionInstructor.session_id == session_id)
        .group_by(SessionInstructor.role_id)
    )).all())

    for role_id, opening in existing.items():
        if role_id not in wanted_role_ids and assigned_by_role.get(role_id):
            role = await db.get(DeliveryRole, role_id)
            raise HTTPException(
                409,
                detail=f"Someone is already assigned as {role.name if role else 'that role'} — "
                       "remove them before removing the opening",
            )

    for role_id, opening in list(existing.items()):
        if role_id not in wanted_role_ids:
            await db.delete(opening)

    out = []
    for line in lines:
        role_id = line["role_id"]
        if await db.get(DeliveryRole, role_id) is None:
            raise HTTPException(404, detail="Delivery role not found")

        slots = int(line.get("slots") or 1)
        if slots < 1:
            raise HTTPException(400, detail="An opening needs at least one slot")
        taken = assigned_by_role.get(role_id, 0)
        if slots < taken:
            raise HTTPException(
                409, detail=f"{taken} already assigned — can't drop below that many slots"
            )

        opening = existing.get(role_id)
        if opening is None:
            opening = SessionOpening(
                id=uuid.uuid4(), session_id=session_id, role_id=role_id,
                created_by=actor_user_id,
            )
            db.add(opening)
        opening.slots = slots
        opening.amount_aed = line.get("amount_aed")
        opening.notes = line.get("notes")
        out.append(opening)

    await db.flush()
    return out


async def openings_for_session(
    db: AsyncSession, session_id: uuid.UUID, *, open_only: bool = False,
) -> list[dict]:
    """Openings with slots taken/remaining and the waitlist size.

    None of those three are stored — an assignment count and an interest count
    is all it takes, and storing them would be a second source of truth for a
    number that changes every time somebody is assigned.

    `open_only=True` (B2) is what the instructor-facing marketplace uses — a
    role ops hasn't (or no longer) is soliciting for is invisible there, even
    though the row and its history still exist for ops's own view.

    A session with no `SessionOpening` rows of its own falls back to its
    cohort's `CohortOpening` template (2026-08-01) — inherit, don't duplicate,
    same shape as materials' program -> cohort -> session resolution. The
    moment ops saves real openings for this one session, those win from then
    on; every other session in the cohort keeps inheriting the template.
    """
    stmt = (
        select(SessionOpening, DeliveryRole)
        .join(DeliveryRole, DeliveryRole.id == SessionOpening.role_id)
        .where(SessionOpening.session_id == session_id)
        .order_by(DeliveryRole.sort_order)
    )
    if open_only:
        stmt = stmt.where(SessionOpening.is_open.is_(True))
    rows = (await db.execute(stmt)).all()

    inherited = False
    if not rows:
        session = await db.get(Session, session_id)
        if session is not None:
            rows = (await db.execute(
                select(CohortOpening, DeliveryRole)
                .join(DeliveryRole, DeliveryRole.id == CohortOpening.role_id)
                .where(CohortOpening.cohort_id == session.cohort_id)
                .order_by(DeliveryRole.sort_order)
            )).all()
            inherited = bool(rows)

    if not rows:
        return []

    assigned = dict((await db.execute(
        select(SessionInstructor.role_id, func.count())
        .where(SessionInstructor.session_id == session_id)
        .group_by(SessionInstructor.role_id)
    )).all())
    interested = await db.scalar(
        select(func.count()).select_from(InstructorInterest)
        .where(InstructorInterest.session_id == session_id)
    ) or 0

    out = []
    for opening, role in rows:
        taken = assigned.get(opening.role_id, 0)
        remaining = max(0, opening.slots - taken)
        out.append({
            "id": opening.id,
            "session_id": session_id,
            "role_id": role.id,
            "role_name": role.name,
            "role_description": role.description,
            "slots": opening.slots,
            "filled": taken,
            "remaining": remaining,
            "amount_aed": opening.amount_aed,
            "notes": opening.notes,
            # A template row has no is_open of its own — inherited rows are
            # never individually closed, only the whole session's call is.
            "is_open": True if inherited else opening.is_open,
            "inherited": inherited,
            # Interest is session-wide, not per role, so this is "people
            # waiting on this session" rather than on this specific opening.
            # Saying otherwise would be inventing precision we don't have.
            "waitlist": max(0, interested - sum(assigned.values())) if remaining == 0 else 0,
        })
    return out


# ── cohort-level opening defaults (2026-08-01) ──────────────────────────────

async def set_cohort_openings(
    db: AsyncSession, *, cohort_id: uuid.UUID, lines: list[dict], actor_user_id: uuid.UUID
) -> list[CohortOpening]:
    """Replace the whole template. No "someone's already assigned" guard here
    — unlike `set_openings`, this row has no assignments of its own to
    orphan; individual sessions that already customized their own openings
    are entirely unaffected by changing the template underneath them."""
    if await db.get(Cohort, cohort_id) is None:
        raise HTTPException(404, detail="Cohort not found")

    existing = {
        o.role_id: o for o in (await db.execute(
            select(CohortOpening).where(CohortOpening.cohort_id == cohort_id)
        )).scalars().all()
    }
    wanted_role_ids = {line["role_id"] for line in lines}
    for role_id, opening in list(existing.items()):
        if role_id not in wanted_role_ids:
            await db.delete(opening)

    out = []
    for line in lines:
        role_id = line["role_id"]
        if await db.get(DeliveryRole, role_id) is None:
            raise HTTPException(404, detail="Delivery role not found")
        slots = int(line.get("slots") or 1)
        if slots < 1:
            raise HTTPException(400, detail="An opening needs at least one slot")

        opening = existing.get(role_id)
        if opening is None:
            opening = CohortOpening(
                id=uuid.uuid4(), cohort_id=cohort_id, role_id=role_id, created_by=actor_user_id,
            )
            db.add(opening)
        opening.slots = slots
        opening.amount_aed = line.get("amount_aed")
        opening.notes = line.get("notes")
        out.append(opening)

    await db.flush()
    return out


async def cohort_openings(db: AsyncSession, cohort_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(
        select(CohortOpening, DeliveryRole)
        .join(DeliveryRole, DeliveryRole.id == CohortOpening.role_id)
        .where(CohortOpening.cohort_id == cohort_id)
        .order_by(DeliveryRole.sort_order)
    )).all()
    return [
        {
            "id": o.id, "cohort_id": o.cohort_id, "role_id": role.id, "role_name": role.name,
            "slots": o.slots, "amount_aed": o.amount_aed, "notes": o.notes,
        }
        for o, role in rows
    ]


async def set_openings_open(
    db: AsyncSession, *, session_id: uuid.UUID, role_ids: list[uuid.UUID] | None,
) -> None:
    """Which roles are currently on offer (B2). `None` opens every existing
    opening (today's exact behaviour — an open call was all-or-nothing);
    given a list, only those roles become `is_open`, the rest close. Closing
    a role never touches assignments or the opening row itself — it only
    stops it from appearing to instructors."""
    rows = (await db.execute(
        select(SessionOpening).where(SessionOpening.session_id == session_id)
    )).scalars().all()
    wanted = None if role_ids is None else set(role_ids)
    for opening in rows:
        opening.is_open = True if wanted is None else opening.role_id in wanted
    await db.flush()


async def fully_staffed(db: AsyncSession, session_id: uuid.UUID) -> bool:
    """Every opening filled. A session with no openings falls back to "has
    anyone at all", so sessions created before I5-4 behave as they always did.
    """
    openings = await openings_for_session(db, session_id)
    if not openings:
        return bool(await db.scalar(
            select(func.count()).select_from(SessionInstructor)
            .where(SessionInstructor.session_id == session_id)
        ))
    return all(o["remaining"] == 0 for o in openings)


# ── §G-addons ───────────────────────────────────────────────────────────────

async def add_addon(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    description: str,
    amount_aed: Decimal | float,
    source: str,
    actor_user_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    role_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> SessionAddon:
    """Record an add-on from any of the five moments it can arise.

    `status` is decided by `source`, never passed in: ops offering something
    has already agreed it; an instructor asking for something has not. That is
    the whole approval mechanism, and letting a caller choose would let an
    instructor's request arrive pre-approved.
    """
    if source not in ADDON_SOURCES:
        raise HTTPException(400, detail=f"Unknown add-on source '{source}'")
    if await db.get(Session, session_id) is None:
        raise HTTPException(404, detail="Session not found")

    description = (description or "").strip()
    if not description:
        raise HTTPException(400, detail="An add-on needs a description")
    if Decimal(str(amount_aed)) < 0:
        raise HTTPException(400, detail="An add-on can't be negative")

    ops_side = source in _OPS_SOURCES
    addon = SessionAddon(
        id=uuid.uuid4(),
        session_id=session_id,
        user_id=user_id,
        role_id=role_id if user_id is None else None,
        description=description,
        amount_aed=Decimal(str(amount_aed)),
        notes=notes,
        source=source,
        status="agreed" if ops_side else "proposed",
        created_by=actor_user_id,
        decided_by=actor_user_id if ops_side else None,
        decided_at=datetime.now(timezone.utc) if ops_side else None,
    )
    db.add(addon)
    await db.flush()
    return addon


async def decide_addon(
    db: AsyncSession, *, addon: SessionAddon, status: str, actor_user_id: uuid.UUID
) -> SessionAddon:
    """Ops answers a request. Recording the decision is the point — "asked and
    never answered" is a state worth being able to query for."""
    if status not in {"agreed", "declined"}:
        raise HTTPException(400, detail="A decision is 'agreed' or 'declined'")

    addon.status = status
    addon.decided_by = actor_user_id
    addon.decided_at = datetime.now(timezone.utc)
    await db.flush()
    return addon


async def update_addon(
    db: AsyncSession, *, addon: SessionAddon,
    description: str | None = None, amount_aed: Decimal | float | None = None,
) -> SessionAddon:
    if description is not None:
        description = description.strip()
        if not description:
            raise HTTPException(400, detail="An add-on needs a description")
        addon.description = description
    if amount_aed is not None:
        if Decimal(str(amount_aed)) < 0:
            raise HTTPException(400, detail="An add-on can't be negative")
        addon.amount_aed = Decimal(str(amount_aed))
    await db.flush()
    return addon


async def delete_addon(db: AsyncSession, *, addon: SessionAddon) -> None:
    await db.delete(addon)
    await db.flush()


async def addons_for_session(
    db: AsyncSession, session_id: uuid.UUID, *, user_id: uuid.UUID | None = None
) -> list[dict]:
    """Add-ons on a session. With `user_id`, narrows to that person's — theirs
    plus anything attached to a role they hold, which is what the invite and
    the payment letter both need."""
    rows = (await db.execute(
        select(SessionAddon, User.full_name, DeliveryRole.name)
        .outerjoin(User, User.id == SessionAddon.user_id)
        .outerjoin(DeliveryRole, DeliveryRole.id == SessionAddon.role_id)
        .where(SessionAddon.session_id == session_id)
        .order_by(SessionAddon.created_at)
    )).all()

    if user_id is not None:
        my_roles = set((await db.execute(
            select(SessionInstructor.role_id).where(
                SessionInstructor.session_id == session_id,
                SessionInstructor.user_id == user_id,
            )
        )).scalars().all())
        rows = [
            r for r in rows
            if r[0].user_id == user_id or (r[0].user_id is None and r[0].role_id in my_roles)
        ]

    return [
        {
            "id": a.id, "session_id": a.session_id,
            "user_id": a.user_id, "user_name": user_name,
            "role_id": a.role_id, "role_name": role_name,
            "description": a.description, "amount_aed": a.amount_aed, "notes": a.notes,
            "source": a.source, "status": a.status,
            "created_at": a.created_at, "decided_at": a.decided_at,
        }
        for a, user_name, role_name in rows
    ]
