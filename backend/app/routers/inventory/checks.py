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
from app.models.inventory.movement import Movement
from app.models.inventory.session_kit import KitCheck
from app.models.user import User
from app.schemas.inventory.checks import (
    AssignKitsIn,
    CheckOut,
    CheckSubmitIn,
    ExpectedCountOut,
    SessionKitOut,
    SessionKitStatusOut,
)
from app.services.inventory import (
    assign_kits,
    assigned_kits,
    check_history,
    expected_counts,
    outstanding_post_checks,
    record_check,
    unassign_kit,
)
from app.services.sessions.delivery import _get_deliverable_session

router = APIRouter(prefix="/inventory", tags=["inventory-session-loop"])


async def _session_kit_view(
    db: AsyncSession, session_id: uuid.UUID, viewer_id: uuid.UUID | None = None,
) -> SessionKitStatusOut:
    kits = await assigned_kits(db, session_id)
    if not kits:
        return SessionKitStatusOut(kits=[], outstanding_post_checks=[], can_finish=True)

    pending_confirmation = False
    if viewer_id is not None:
        pending_confirmation = bool((await db.execute(
            select(Movement.id).where(
                Movement.session_id == session_id,
                Movement.to_user_id == viewer_id,
                Movement.reason == "issue",
                Movement.confirmed_at.is_(None),
            ).limit(1)
        )).first())

    templates = dict((await db.execute(
        select(KitTemplate.id, KitTemplate.name)
        .where(KitTemplate.id.in_({k.template_id for k in kits}))
    )).all())
    locations = dict((await db.execute(
        select(Location.id, Location.name)
        .where(Location.id.in_({k.current_location_id for k in kits}))
    )).all())
    holders = dict((await db.execute(
        select(User.id, User.full_name)
        .where(User.id.in_({k.current_holder_user_id for k in kits if k.current_holder_user_id}))
    )).all()) if any(k.current_holder_user_id for k in kits) else {}

    done = (await db.execute(
        select(KitCheck.kit_id, KitCheck.phase).where(KitCheck.session_id == session_id)
    )).all()
    pre = {kit_id for kit_id, phase in done if phase == "pre"}
    post = {kit_id for kit_id, phase in done if phase == "post"}

    outstanding = [k.id for k in kits if k.id not in post]
    return SessionKitStatusOut(
        kits=[
            SessionKitOut(
                kit_id=k.id, label=k.label,
                template_name=templates.get(k.template_id, ""),
                status=k.status,
                location_name=locations.get(k.current_location_id, ""),
                holder_name=holders.get(k.current_holder_user_id),
                pre_checked=k.id in pre,
                post_checked=k.id in post,
            )
            for k in kits
        ],
        outstanding_post_checks=outstanding,
        can_finish=not outstanding,
        pending_confirmation=pending_confirmation,
    )


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
    return await _session_kit_view(db, session_id)


@router.delete("/sessions/{session_id}/kits/{kit_id}", response_model=SessionKitStatusOut)
async def remove_session_kit(
    session_id: uuid.UUID,
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    await unassign_kit(db, session_id=session_id, kit_id=kit_id)
    await db.commit()
    return await _session_kit_view(db, session_id)


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
    await _get_deliverable_session(db, session_id, current_user)
    return await _session_kit_view(db, session_id, current_user.id)


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
