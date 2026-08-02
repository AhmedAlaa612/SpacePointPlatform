"""The session loop endpoints (I2-1/I2-2).

Ops assigns kits to a session. The instructor counts them before and after.
The post-count is what unlocks finishing the session — see
`services/sessions/delivery.py::mark_done`.

Assignment is `require_operations`. The check endpoints are
`require_session_delivery` and go through the same `_get_deliverable_session`
gate the rest of the delivery flow uses, so an instructor can only count kits
on a session they are actually assigned to — and an unrelated session is a
404, not a 403.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_session_delivery
from app.db.session import get_db
from app.models.inventory.kit import Kit
from app.models.inventory.kit_template import KitTemplate
from app.models.inventory.location import Location
from app.models.inventory.session_kit import KitCheck, SessionKit
from app.models.sessions.cohort import Cohort
from app.models.sessions.session import Session
from app.models.user import User
from app.schemas.inventory.checks import (
    AssignKitsIn,
    CheckOut,
    CheckSubmitIn,
    CohortKitOut,
    CohortKitStatusOut,
    ConfirmKitReturnsIn,
    ExpectedCountOut,
    MarkKitsReturnedIn,
    ReceiveKitsIn,
    SessionKitOut,
    SessionKitStatusOut,
)
from app.services.inventory import (
    assign_kits,
    check_history,
    cohort_kits,
    confirm_kit_returns,
    expected_counts,
    mark_kits_received,
    mark_kits_returned,
    outstanding_post_checks,
    record_check,
    remove_cohort_kit,
    resolve_session_kits,
    set_cohort_kits,
    unassign_kit,
)
from app.services.sessions.delivery import _get_deliverable_session

router = APIRouter(prefix="/inventory", tags=["inventory-session-loop"])


async def _session_kit_view(db: AsyncSession, session: Session) -> SessionKitStatusOut:
    kits, level = await resolve_session_kits(db, session)
    if not kits:
        return SessionKitStatusOut(kits=[], outstanding_post_checks=[], can_finish=True, level=level)

    templates = dict((await db.execute(
        select(KitTemplate.id, KitTemplate.name)
        .where(KitTemplate.id.in_({k.template_id for k in kits}))
    )).all())
    locations = dict((await db.execute(
        select(Location.id, Location.name)
        .where(Location.id.in_({k.current_location_id for k in kits}))
    )).all())

    done = (await db.execute(
        select(KitCheck.kit_id, KitCheck.phase).where(KitCheck.session_id == session.id)
    )).all()
    pre = {kit_id for kit_id, phase in done if phase == "pre"}
    post = {kit_id for kit_id, phase in done if phase == "post"}

    # Only real (materialized) kits have a `SessionKit` row — an inherited,
    # not-yet-materialized kit has nothing to report received/returned yet.
    session_kits = {
        sk.kit_id: sk
        for sk in (await db.execute(
            select(SessionKit).where(SessionKit.session_id == session.id)
        )).scalars().all()
    }

    # The actual `mark_done` gate only ever looks at this session's own
    # materialized kits (see `outstanding_post_checks` in services/inventory/
    # checks.py) — an inherited-but-untouched kit isn't gating anything, so
    # the display mirrors that exactly rather than recomputing from `kits`.
    outstanding = await outstanding_post_checks(db, session.id)

    return SessionKitStatusOut(
        kits=[
            SessionKitOut(
                kit_id=k.id, label=k.label,
                template_name=templates.get(k.template_id, ""),
                status=k.status,
                location_name=locations.get(k.current_location_id, ""),
                pre_checked=k.id in pre,
                post_checked=k.id in post,
                received=session_kits[k.id].received_at is not None if k.id in session_kits else False,
                received_at=session_kits[k.id].received_at if k.id in session_kits else None,
                return_status=session_kits[k.id].return_status if k.id in session_kits else None,
                returned_at=session_kits[k.id].returned_at if k.id in session_kits else None,
                ops_confirmed=session_kits[k.id].ops_confirmed_at is not None if k.id in session_kits else False,
                inherited=(level != "session"),
            )
            for k in kits
        ],
        outstanding_post_checks=[k.id for k in outstanding],
        can_finish=not outstanding,
        level=level,
    )


async def _get_session_or_404(db: AsyncSession, session_id: uuid.UUID) -> Session:
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


# ── ops: which kits go to this session ──────────────────────────────────────

@router.put("/sessions/{session_id}/kits", response_model=SessionKitStatusOut)
async def set_session_kits(
    session_id: uuid.UUID,
    body: AssignKitsIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    await assign_kits(
        db, session_id=session_id, kit_ids=body.kit_ids, actor_user_id=current_user.id
    )
    await db.commit()
    return await _session_kit_view(db, await _get_session_or_404(db, session_id))


@router.delete("/sessions/{session_id}/kits/{kit_id}", response_model=SessionKitStatusOut)
async def remove_session_kit(
    session_id: uuid.UUID,
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    await unassign_kit(
        db, session_id=session_id, kit_id=kit_id, actor_user_id=current_user.id
    )
    await db.commit()
    return await _session_kit_view(db, await _get_session_or_404(db, session_id))


# ── instructor: the session's kits, and counting them ───────────────────────

@router.get("/sessions/{session_id}/kits", response_model=SessionKitStatusOut)
async def get_session_kits(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Assigned kits and whether each has been counted. `can_finish` mirrors
    exactly what `mark_done` will enforce, so the UI can disable the button
    instead of letting someone press it and get a 409."""
    session = await _get_deliverable_session(db, session_id, current_user)
    return await _session_kit_view(db, session)


@router.post("/sessions/{session_id}/kits/receive", response_model=SessionKitStatusOut)
async def receive_kits(
    session_id: uuid.UUID,
    body: ReceiveKitsIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """The instructor confirms they have these kits — one at a time, or all
    selected at once. No custody movement, nothing to wait on the other side
    for."""
    await _get_deliverable_session(db, session_id, current_user)
    await mark_kits_received(
        db, session_id=session_id, kit_ids=body.kit_ids, actor_user_id=current_user.id
    )
    await db.commit()
    return await _session_kit_view(db, await _get_session_or_404(db, session_id))


@router.post("/sessions/{session_id}/kits/mark-returned", response_model=SessionKitStatusOut)
async def mark_kits_returned_route(
    session_id: uuid.UUID,
    body: MarkKitsReturnedIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """The instructor reports these kits back, or says they're coming back
    later. No destination to pick — ops decides where a kit actually lands
    when it reviews the report."""
    await _get_deliverable_session(db, session_id, current_user)
    await mark_kits_returned(
        db, session_id=session_id, kit_ids=body.kit_ids, actor_user_id=current_user.id,
        later=body.later, note=body.note,
    )
    await db.commit()
    return await _session_kit_view(db, await _get_session_or_404(db, session_id))


@router.post("/sessions/{session_id}/kits/confirm-returns", response_model=SessionKitStatusOut)
async def confirm_kit_returns_route(
    session_id: uuid.UUID,
    body: ConfirmKitReturnsIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Ops reviews the instructor's report, in the session review screen.
    Restocking a kit onto a shelf is optional and separate from confirming
    the report — a kit that never physically left has nothing to move."""
    await confirm_kit_returns(
        db, session_id=session_id, kit_ids=body.kit_ids, actor_user_id=current_user.id,
        restock_warehouse_id=body.restock_warehouse_id,
    )
    await db.commit()
    return await _session_kit_view(db, await _get_session_or_404(db, session_id))


@router.get("/sessions/{session_id}/kits/{kit_id}/check", response_model=list[ExpectedCountOut])
async def get_check_form(
    session_id: uuid.UUID,
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """The count form, prefilled. Consumables are absent by design — counting
    twenty screws after every workshop is how a shortage list becomes noise."""
    await _get_deliverable_session(db, session_id, current_user)
    kit = await db.get(Kit, kit_id)
    if kit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kit not found")
    return [ExpectedCountOut(**line) for line in await expected_counts(db, kit)]


@router.post(
    "/sessions/{session_id}/kits/{kit_id}/check",
    response_model=CheckOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_check(
    session_id: uuid.UUID,
    kit_id: uuid.UUID,
    body: CheckSubmitIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Record a pre- or post-session count.

    The counted numbers become the kit's contents — someone who just looked
    inside the box outranks the database.
    """
    await _get_deliverable_session(db, session_id, current_user)
    kit = await db.get(Kit, kit_id)
    if kit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kit not found")

    check = await record_check(
        db,
        kit=kit,
        phase=body.phase,
        checked_by=current_user.id,
        counts=body.counts,
        skipped=body.skipped,
        session_id=session_id,
        note=body.note,
    )
    await db.commit()
    await db.refresh(check)
    return CheckOut(
        id=check.id, kit_id=check.kit_id, session_id=check.session_id,
        phase=check.phase, skipped=check.skipped, checked_by=check.checked_by,
        checked_by_name=current_user.full_name,
        counts=check.counts, missing=check.missing, note=check.note,
        created_at=check.created_at,
    )


@router.get("/kits/{kit_id}/checks", response_model=list[CheckOut])
async def kit_check_history(
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Every count of this kit, newest first — the record of what was in the
    box on any given day."""
    if await db.get(Kit, kit_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kit not found")
    return [
        CheckOut(
            id=c.id, kit_id=c.kit_id, session_id=c.session_id, phase=c.phase,
            skipped=c.skipped, checked_by=c.checked_by, checked_by_name=name,
            counts=c.counts, missing=c.missing, note=c.note, created_at=c.created_at,
        )
        for c, name in await check_history(db, kit_id)
    ]


# ── ops: a cohort's default kit list (Phase 3 follow-up) ────────────────────
# A session with no kit activity of its own inherits whatever this list is at
# read time; the first assign/unassign/receive/return on a specific session
# copies it in and that session stops watching this list from then on.

async def _cohort_kit_view(db: AsyncSession, cohort_id: uuid.UUID) -> CohortKitStatusOut:
    kits = await cohort_kits(db, cohort_id)
    if not kits:
        return CohortKitStatusOut(kits=[])

    templates = dict((await db.execute(
        select(KitTemplate.id, KitTemplate.name)
        .where(KitTemplate.id.in_({k.template_id for k in kits}))
    )).all())
    locations = dict((await db.execute(
        select(Location.id, Location.name)
        .where(Location.id.in_({k.current_location_id for k in kits}))
    )).all())

    return CohortKitStatusOut(
        kits=[
            CohortKitOut(
                kit_id=k.id, label=k.label,
                template_name=templates.get(k.template_id, ""),
                location_name=locations.get(k.current_location_id, ""),
            )
            for k in kits
        ]
    )


@router.get("/cohorts/{cohort_id}/kits-defaults", response_model=CohortKitStatusOut)
async def get_cohort_kits(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """A cohort's default kit list — what every session in it starts with
    until that specific session's own kit activity happens."""
    if await db.get(Cohort, cohort_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return await _cohort_kit_view(db, cohort_id)


@router.put("/cohorts/{cohort_id}/kits-defaults", response_model=CohortKitStatusOut)
async def set_cohort_kits_route(
    cohort_id: uuid.UUID,
    body: AssignKitsIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """The full default list, resubmitted — same multi-select contract as
    `set_session_kits`, one level up. Sessions already materialized (their
    own kit activity has already happened) are untouched by this."""
    await set_cohort_kits(
        db, cohort_id=cohort_id, kit_ids=body.kit_ids, actor_user_id=current_user.id
    )
    await db.commit()
    return await _cohort_kit_view(db, cohort_id)


@router.delete("/cohorts/{cohort_id}/kits-defaults/{kit_id}", response_model=CohortKitStatusOut)
async def remove_cohort_kit_route(
    cohort_id: uuid.UUID,
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    await remove_cohort_kit(db, cohort_id=cohort_id, kit_id=kit_id)
    await db.commit()
    return await _cohort_kit_view(db, cohort_id)
