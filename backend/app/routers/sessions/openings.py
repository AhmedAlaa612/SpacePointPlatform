"""Delivery roles, openings and add-ons (I5-3, I5-4, §G-addons).

    GET/POST/PATCH     /sessions/delivery-roles          ops configures the vocabulary
    GET/PUT            /sessions/{id}/openings           the offer, per role
    GET/POST           /sessions/{id}/addons             extra money
    PUT                /sessions/addons/{id}/decision    ops answers a request
    PATCH/DELETE       /sessions/addons/{id}             ops corrects or removes one

Roles and openings are `require_operations` — they define what a session is
offering, which is an ops decision.

**Add-ons are the exception, deliberately.** An instructor has to be able to
*raise* one (with their interest response, or in the post-session survey), so
POST is `require_session_delivery` and the service decides the status from the
source: ops-side sources land `agreed`, instructor-side ones land `proposed`.
Answering a request is `require_operations`, because self-approval is the one
thing the proposed/agreed split exists to prevent.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_session_delivery
from app.db.session import get_db
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.opening import SessionAddon
from app.models.user import User
from app.schemas.sessions.openings import (
    AddonDecisionIn,
    AddonIn,
    AddonOut,
    AddonUpdateIn,
    CohortOpeningOut,
    DeliveryRoleCreate,
    DeliveryRoleOut,
    DeliveryRoleUpdate,
    OpeningOut,
    ProgramOpeningOut,
    SetOpeningsIn,
)
from app.services.org_access import (
    can_read_cohort,
    is_ops_or_admin,
    require_cohort_delivery_manager_or_ops,
    require_cohort_read_or_ops,
    require_program_manager_or_ops,
    require_program_read_or_ops,
    require_session_delivery_manager_or_ops,
)
from app.services.sessions import openings as svc
from app.services.sessions.delivery import _get_deliverable_session
from app.models.sessions.cohort import Cohort
from app.models.sessions.session import Session

router = APIRouter(prefix="/sessions", tags=["sessions-openings"])


def _is_partner_caller(user: User) -> bool:
    return "organization" in user.role_values and not is_ops_or_admin(user)


def _redact_role_out(role: DeliveryRole, partner: bool) -> DeliveryRoleOut:
    out = DeliveryRoleOut.model_validate(role)
    if partner:
        out.default_rate_aed = None
    return out


def _redact_session_opening(row: dict, partner: bool) -> OpeningOut:
    out = OpeningOut(**row)
    if partner:
        out.amount_aed = None
        out.rate_source = None
    return out


def _redact_cohort_opening(row: dict, partner: bool) -> CohortOpeningOut:
    out = CohortOpeningOut(**row)
    if partner:
        out.amount_aed = None
        out.role_default_rate_aed = None
    return out


def _redact_program_opening(row: dict, partner: bool) -> ProgramOpeningOut:
    out = ProgramOpeningOut(**row)
    if partner:
        out.amount_aed = None
        out.role_default_rate_aed = None
    return out


# ── delivery roles ──────────────────────────────────────────────────────────

@router.get("/delivery-roles", response_model=list[DeliveryRoleOut])
async def list_delivery_roles(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    # Readable by anyone who delivers: an instructor's own session shows the
    # role they hold, and the invite names the role being offered.
    current_user: User = Depends(require_session_delivery),
):
    roles = await svc.list_roles(db, include_inactive=include_inactive)
    partner = _is_partner_caller(current_user)
    return [_redact_role_out(r, partner) for r in roles]


@router.post("/delivery-roles", response_model=DeliveryRoleOut, status_code=status.HTTP_201_CREATED)
async def create_delivery_role(
    body: DeliveryRoleCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    role = await svc.create_role(
        db, name=body.name, description=body.description, sort_order=body.sort_order,
        default_rate_aed=body.default_rate_aed,
    )
    await db.commit()
    await db.refresh(role)
    return role


@router.patch("/delivery-roles/{role_id}", response_model=DeliveryRoleOut)
async def update_delivery_role(
    role_id: uuid.UUID,
    body: DeliveryRoleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Renaming is safe: `payment_sessions.role` snapshots the name at the
    time, so signed letters keep saying what they said. There is no delete —
    a role that has ever been assigned is part of the record; deactivate it."""
    role = await db.get(DeliveryRole, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Delivery role not found")
    await svc.update_role(
        db, role=role, name=body.name, description=body.description,
        sort_order=body.sort_order, is_active=body.is_active,
        default_rate_aed=body.default_rate_aed, clear_default_rate=body.clear_default_rate,
    )
    await db.commit()
    await db.refresh(role)
    return role


# ── openings ────────────────────────────────────────────────────────────────

@router.get("/{session_id}/openings", response_model=list[OpeningOut])
async def get_openings(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Slots, offer and how many are left. Visible to instructors, org managers/observers, and Ops."""
    session = await _get_deliverable_session(db, session_id, current_user, read_only=True)
    is_ops = is_ops_or_admin(current_user)
    is_org_reader = False
    if not is_ops and "organization" in current_user.role_values:
        cohort = await db.get(Cohort, session.cohort_id)
        if cohort is not None:
            is_org_reader = await can_read_cohort(db, cohort, current_user)
    rows = await svc.openings_for_session(db, session_id, open_only=not (is_ops or is_org_reader))
    partner = _is_partner_caller(current_user)
    return [_redact_session_opening(row, partner) for row in rows]


@router.put("/{session_id}/openings", response_model=list[OpeningOut])
async def set_openings(
    session_id: uuid.UUID,
    body: SetOpeningsIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_session_delivery_manager_or_ops(db, session_id, current_user)
    partner = _is_partner_caller(current_user)
    lines = []
    for line in body.openings:
        d = line.model_dump()
        if partner:
            d["amount_aed"] = None
        lines.append(d)
    await svc.set_openings(
        db,
        session_id=session_id,
        lines=lines,
        actor_user_id=current_user.id,
    )
    await db.commit()
    return [_redact_session_opening(row, partner) for row in await svc.openings_for_session(db, session_id)]


# ── cohort-level opening defaults (2026-08-01) ─────────────────────────────

@router.get("/cohorts/{cohort_id}/openings-defaults", response_model=list[CohortOpeningOut])
async def get_cohort_openings(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """The template new sessions in this cohort inherit until they're
    individually customized — see openings_for_session's fallback."""
    await require_cohort_read_or_ops(db, cohort_id, current_user)
    partner = _is_partner_caller(current_user)
    return [_redact_cohort_opening(row, partner) for row in await svc.cohort_openings(db, cohort_id)]


@router.put("/cohorts/{cohort_id}/openings-defaults", response_model=list[CohortOpeningOut])
async def set_cohort_openings(
    cohort_id: uuid.UUID,
    body: SetOpeningsIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_cohort_delivery_manager_or_ops(db, cohort_id, current_user)
    partner = _is_partner_caller(current_user)
    lines = []
    for line in body.openings:
        d = line.model_dump()
        if partner:
            d["amount_aed"] = None
        lines.append(d)
    await svc.set_cohort_openings(
        db, cohort_id=cohort_id,
        lines=lines,
        actor_user_id=current_user.id,
    )
    await db.commit()
    return [_redact_cohort_opening(row, partner) for row in await svc.cohort_openings(db, cohort_id)]


# ── program-level role template (2026-09) ──────────────────────────────────

@router.get("/programs/{program_id}/openings-defaults", response_model=list[ProgramOpeningOut])
async def get_program_openings(
    program_id: uuid.UUID,
    variation_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """The template new cohorts of this program/variation are seeded from at creation."""
    await require_program_read_or_ops(db, program_id, current_user)
    partner = _is_partner_caller(current_user)
    return [
        _redact_program_opening(row, partner)
        for row in await svc.program_openings(db, program_id, variation_id=variation_id)
    ]


@router.put("/programs/{program_id}/openings-defaults", response_model=list[ProgramOpeningOut])
async def set_program_openings(
    program_id: uuid.UUID,
    body: SetOpeningsIn,
    variation_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_program_manager_or_ops(db, program_id, current_user)
    partner = _is_partner_caller(current_user)
    lines = []
    for line in body.openings:
        d = line.model_dump()
        if partner:
            d["amount_aed"] = None
        lines.append(d)
    await svc.set_program_openings(
        db, program_id=program_id,
        variation_id=variation_id,
        lines=lines,
        actor_user_id=current_user.id,
    )
    await db.commit()
    return [
        _redact_program_opening(row, partner)
        for row in await svc.program_openings(db, program_id, variation_id=variation_id)
    ]


# ── add-ons ─────────────────────────────────────────────────────────────────

@router.get("/{session_id}/addons", response_model=list[AddonOut])
async def get_addons(
    session_id: uuid.UUID,
    mine: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """`mine=true` narrows to this person's — theirs plus anything attached to
    a role they hold, which is what the invite and the payment letter need."""
    await _get_deliverable_session(db, session_id, current_user)
    rows = await svc.addons_for_session(
        db, session_id, user_id=current_user.id if mine else None
    )
    return [AddonOut(**row) for row in rows]


@router.post("/{session_id}/addons", response_model=AddonOut, status_code=status.HTTP_201_CREATED)
async def create_addon(
    session_id: uuid.UUID,
    body: AddonIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Raise an add-on from any of its five moments.

    An instructor may only ever attach one to *themselves*: letting them name
    another user, or leave it on the role, would be raising a request on
    somebody else's behalf. Ops can do both.
    """
    await _get_deliverable_session(db, session_id, current_user)

    is_ops = {"operations", "admin"} & set(current_user.role_values)
    source = body.source
    user_id, role_id = body.user_id, body.role_id
    if not is_ops:
        # Instructor-side: force it onto them, and force an instructor-side
        # source so a request cannot arrive pre-agreed.
        user_id, role_id = current_user.id, None
        if source not in {"interest", "survey"}:
            source = "interest"

    addon = await svc.add_addon(
        db,
        session_id=session_id,
        description=body.description,
        amount_aed=body.amount_aed,
        source=source,
        actor_user_id=current_user.id,
        user_id=user_id,
        role_id=role_id,
        notes=body.notes,
    )
    await db.commit()

    for row in await svc.addons_for_session(db, session_id):
        if row["id"] == addon.id:
            return AddonOut(**row)
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Add-on vanished")


@router.put("/addons/{addon_id}/decision", response_model=AddonOut)
async def decide_addon(
    addon_id: uuid.UUID,
    body: AddonDecisionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Ops answers a request. `require_operations`, because the whole point of
    proposed-vs-agreed is that the person asking isn't the person approving."""
    addon = await db.get(SessionAddon, addon_id)
    if addon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Add-on not found")

    await svc.decide_addon(db, addon=addon, status=body.status, actor_user_id=current_user.id)
    await db.commit()

    for row in await svc.addons_for_session(db, addon.session_id):
        if row["id"] == addon_id:
            return AddonOut(**row)
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Add-on not found")


@router.patch("/addons/{addon_id}", response_model=AddonOut)
async def update_addon(
    addon_id: uuid.UUID,
    body: AddonUpdateIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Correct a mistyped description or amount. Ops-only — an instructor who
    wants a change asks for a new add-on (§G-addons's `proposed` path) rather
    than editing what's already on record."""
    addon = await db.get(SessionAddon, addon_id)
    if addon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Add-on not found")

    await svc.update_addon(db, addon=addon, description=body.description, amount_aed=body.amount_aed)
    await db.commit()

    for row in await svc.addons_for_session(db, addon.session_id):
        if row["id"] == addon_id:
            return AddonOut(**row)
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Add-on not found")


@router.delete("/addons/{addon_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_addon(
    addon_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    addon = await db.get(SessionAddon, addon_id)
    if addon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Add-on not found")
    await svc.delete_addon(db, addon=addon)
    await db.commit()
