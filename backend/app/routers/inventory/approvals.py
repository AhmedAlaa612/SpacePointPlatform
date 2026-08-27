"""The approval queue and its policy settings (2026-08-27 follow-up to the
inventory permissions fix).

`GET/PUT /inventory/approval-policies*` and the approve/reject actions are
`require_inventory_approval` (coo; admin passes every `RequireRole` check).
`GET /inventory/approvals/mine` is `require_storekeeper` (storekeeper,
operations, or coo) — anyone who can submit a gated action needs to see what
happened to their own requests; it only ever returns the caller's own rows,
never anyone else's.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_inventory_approval, require_storekeeper
from app.db.session import get_db
from app.models.inventory.approval import InventoryActionPolicy, InventoryApprovalRequest
from app.models.user import User
from app.schemas.inventory.approvals import (
    ActionPolicyOut,
    ActionPolicyUpdate,
    ApprovalDecisionIn,
    ApprovalRequestOut,
)
from app.services.inventory import ACTION_TYPES, approve_request, list_policies, reject_request

router = APIRouter(prefix="/inventory", tags=["inventory-approvals"])


async def _names(db: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    user_ids.discard(None)
    if not user_ids:
        return {}
    return dict((await db.execute(
        select(User.id, User.full_name).where(User.id.in_(user_ids))
    )).all())


async def _request_out(db: AsyncSession, request: InventoryApprovalRequest) -> ApprovalRequestOut:
    names = await _names(db, {request.requested_by, request.reviewed_by})
    return ApprovalRequestOut(
        id=request.id, action_type=request.action_type,
        action_label=ACTION_TYPES.get(request.action_type, request.action_type),
        status=request.status, summary=request.summary,
        requested_by_user_id=request.requested_by,
        requested_by_name=names.get(request.requested_by, "Someone"),
        requested_at=request.requested_at,
        reviewed_by_user_id=request.reviewed_by,
        reviewed_by_name=names.get(request.reviewed_by) if request.reviewed_by else None,
        reviewed_at=request.reviewed_at, review_note=request.review_note,
    )


def _policy_out(policy: InventoryActionPolicy, updated_by_name: str | None) -> ActionPolicyOut:
    return ActionPolicyOut(
        action_type=policy.action_type,
        action_label=ACTION_TYPES.get(policy.action_type, policy.action_type),
        requires_approval=policy.requires_approval,
        updated_by_name=updated_by_name, updated_at=policy.updated_at,
    )


@router.get("/approvals", response_model=list[ApprovalRequestOut])
async def list_approval_requests(
    request_status: str = Query(default="pending", alias="status"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_approval),
):
    stmt = select(InventoryApprovalRequest).order_by(InventoryApprovalRequest.requested_at.desc())
    if request_status != "all":
        stmt = stmt.where(InventoryApprovalRequest.status == request_status)
    requests = (await db.execute(stmt)).scalars().all()
    return [await _request_out(db, r) for r in requests]


@router.get("/approvals/mine", response_model=list[ApprovalRequestOut])
async def my_approval_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_storekeeper),
):
    requests = (await db.execute(
        select(InventoryApprovalRequest)
        .where(InventoryApprovalRequest.requested_by == current_user.id)
        .order_by(InventoryApprovalRequest.requested_at.desc())
    )).scalars().all()
    return [await _request_out(db, r) for r in requests]


@router.post("/approvals/{request_id}/approve", response_model=ApprovalRequestOut)
async def approve(
    request_id: uuid.UUID,
    body: ApprovalDecisionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_approval),
):
    request = await db.get(InventoryApprovalRequest, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Request not found")
    await approve_request(db, request, reviewer=current_user, note=body.note)
    return await _request_out(db, request)


@router.post("/approvals/{request_id}/reject", response_model=ApprovalRequestOut)
async def reject(
    request_id: uuid.UUID,
    body: ApprovalDecisionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_approval),
):
    request = await db.get(InventoryApprovalRequest, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Request not found")
    await reject_request(db, request, reviewer=current_user, note=body.note)
    return await _request_out(db, request)


@router.get("/approval-policies", response_model=list[ActionPolicyOut])
async def get_policies(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_approval),
):
    policies = await list_policies(db)
    names = await _names(db, {p.updated_by for p in policies if p.updated_by})
    return [_policy_out(p, names.get(p.updated_by)) for p in policies]


@router.put("/approval-policies/{action_type}", response_model=ActionPolicyOut)
async def set_policy(
    action_type: str,
    body: ActionPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_approval),
):
    if action_type not in ACTION_TYPES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown action type")

    policy = await db.get(InventoryActionPolicy, action_type)
    if policy is None:
        policy = InventoryActionPolicy(action_type=action_type)
        db.add(policy)

    policy.requires_approval = body.requires_approval
    policy.updated_by = current_user.id
    policy.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(policy)
    return _policy_out(policy, current_user.full_name)
