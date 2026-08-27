"""The approval gate (2026-08-27 follow-up to the inventory permissions fix).

Every gateable write (kit move, merch issue/return, stock adjustment) still
runs its own existence/ownership checks exactly as before — `gate()` is
called *after* those, right where the direct write used to happen. So a
request only ever reaches the queue for a policy reason, never a data one,
and the COO never opens a ticket that was always going to 404.

`payload` is deliberately the minimal set of ids/values the executor needs
to replay the write, not a snapshot of derived state (e.g. a kit's current
warehouse) — replaying against the kit's state *at approval time* is more
correct than freezing it at submission time, especially once more than one
request can be queued against the same kit.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.approval import InventoryActionPolicy, InventoryApprovalRequest
from app.models.inventory.kit import Kit
from app.models.user import User
from app.services.inventory.custody import issue_merch, return_merch
from app.services.inventory.movements import move
from app.services.inventory.stock import adjust_stock

# Every known action type and the label the settings page shows for it.
# Catalogue writes (items/templates/categories/locations/warehouses/cities)
# are a deliberate follow-up, not here yet — see kits.py/custody.py/stock.py's
# own gate() call sites for the ones that are.
ACTION_TYPES: dict[str, str] = {
    "kit.move": "Move or assign a kit",
    "merch.issue": "Hand out merchandise",
    "merch.return": "Take back merchandise",
    "stock.adjust": "Correct a stock count",
}

_APPROVER_ROLES = {"coo", "admin"}


def is_approver(user: User) -> bool:
    return bool(_APPROVER_ROLES & set(user.role_values))


async def policy_requires_approval(db: AsyncSession, action_type: str) -> bool:
    """No row for this action type reads as `False` — deploying a new
    action type, or this migration itself, never starts gating anything
    until the COO explicitly turns it on via `PUT /inventory/approval-
    policies/{action_type}`."""
    policy = await db.get(InventoryActionPolicy, action_type)
    return bool(policy and policy.requires_approval)


async def gate(
    db: AsyncSession,
    *,
    action_type: str,
    actor: User,
    summary: str,
    payload: dict[str, Any],
) -> InventoryApprovalRequest | None:
    """Adds a pending `InventoryApprovalRequest` to the session and returns
    it if `actor` must wait for sign-off; returns `None` if they should
    proceed immediately (an approver, or this action type isn't gated right
    now). Callers still owe the commit either way — this only flushes."""
    if is_approver(actor):
        return None
    if not await policy_requires_approval(db, action_type):
        return None

    request = InventoryApprovalRequest(
        id=uuid.uuid4(), action_type=action_type, status="pending",
        summary=summary, payload=payload, requested_by=actor.id,
        requested_at=datetime.now(timezone.utc),
    )
    db.add(request)
    await db.flush()
    return request


# ── executors ────────────────────────────────────────────────────────────────
#
# One per action type, each replaying the exact service call its direct
# endpoint makes, with the original requester (not the reviewer) as the
# actor — the Movement this produces should say the storekeeper did it; the
# COO's name lives on the approval request's `reviewed_by`, not here. None of
# these commit; the caller (the approve endpoint) does, once, after the
# request's own review fields are set.

async def _exec_kit_move(db: AsyncSession, *, actor_user_id: uuid.UUID, payload: dict) -> None:
    kit = await db.get(Kit, uuid.UUID(payload["kit_id"]))
    if kit is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="That kit no longer exists")
    to_warehouse_id = payload.get("to_warehouse_id")
    to_user_id = payload.get("to_user_id")
    await move(
        db, actor_user_id=actor_user_id, reason=payload["reason"], kit_id=kit.id,
        from_warehouse_id=kit.current_warehouse_id if to_user_id else None,
        from_user_id=kit.current_holder_user_id if to_warehouse_id else None,
        to_warehouse_id=uuid.UUID(to_warehouse_id) if to_warehouse_id else None,
        to_user_id=uuid.UUID(to_user_id) if to_user_id else None,
        session_id=uuid.UUID(payload["session_id"]) if payload.get("session_id") else None,
        due_back_on=date.fromisoformat(payload["due_back_on"]) if payload.get("due_back_on") else None,
        note=payload.get("note"),
    )


async def _exec_merch_issue(db: AsyncSession, *, actor_user_id: uuid.UUID, payload: dict) -> None:
    await issue_merch(
        db, actor_user_id=actor_user_id,
        item_id=uuid.UUID(payload["item_id"]), to_user_id=uuid.UUID(payload["to_user_id"]),
        from_warehouse_id=uuid.UUID(payload["from_warehouse_id"]), qty=payload.get("qty", 1),
        returnable=payload.get("returnable"),
        due_back_on=date.fromisoformat(payload["due_back_on"]) if payload.get("due_back_on") else None,
        note=payload.get("note"),
    )


async def _exec_merch_return(db: AsyncSession, *, actor_user_id: uuid.UUID, payload: dict) -> None:
    await return_merch(
        db, actor_user_id=actor_user_id,
        item_id=uuid.UUID(payload["item_id"]), from_user_id=uuid.UUID(payload["from_user_id"]),
        to_warehouse_id=uuid.UUID(payload["to_warehouse_id"]), qty=payload.get("qty", 1),
    )


async def _exec_stock_adjust(db: AsyncSession, *, actor_user_id: uuid.UUID, payload: dict) -> None:
    """Loops the same `adjust_stock()` a single correction uses, matching
    `POST /stock/adjust-bulk`'s own skip-unchanged-lines behaviour — a count
    that already matches by the time this is approved isn't a failure, it's
    one fewer thing that needed sign-off."""
    applied = 0
    for line in payload["lines"]:
        try:
            await adjust_stock(
                db, actor_user_id=actor_user_id,
                item_id=uuid.UUID(line["item_id"]), warehouse_id=uuid.UUID(line["warehouse_id"]),
                new_qty=line["new_qty"], reason=payload["reason"],
            )
            applied += 1
        except HTTPException as exc:
            if exc.status_code == status.HTTP_409_CONFLICT:
                continue
            raise
    if not applied:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Nothing left to change")


ACTION_EXECUTORS: dict[str, Callable[..., Awaitable[None]]] = {
    "kit.move": _exec_kit_move,
    "merch.issue": _exec_merch_issue,
    "merch.return": _exec_merch_return,
    "stock.adjust": _exec_stock_adjust,
}


async def approve_request(
    db: AsyncSession, request: InventoryApprovalRequest, *, reviewer: User, note: str | None = None,
) -> InventoryApprovalRequest:
    if request.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This request was already decided")

    executor = ACTION_EXECUTORS[request.action_type]
    await executor(db, actor_user_id=request.requested_by, payload=request.payload)

    request.status = "approved"
    request.reviewed_by = reviewer.id
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = note
    await db.commit()
    await db.refresh(request)
    return request


async def reject_request(
    db: AsyncSession, request: InventoryApprovalRequest, *, reviewer: User, note: str | None = None,
) -> InventoryApprovalRequest:
    if request.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This request was already decided")

    request.status = "rejected"
    request.reviewed_by = reviewer.id
    request.reviewed_at = datetime.now(timezone.utc)
    request.review_note = note
    await db.commit()
    await db.refresh(request)
    return request


async def list_policies(db: AsyncSession) -> list[InventoryActionPolicy]:
    """Every known action type, seeded rows and all — `ACTION_TYPES` is the
    source of truth for *which* ones exist; a type with no row yet (deployed
    but never explicitly set) is synthesised at `requires_approval=False`
    rather than omitted, so the settings page always shows a complete,
    togglable list."""
    existing = {
        p.action_type: p
        for p in (await db.execute(select(InventoryActionPolicy))).scalars().all()
    }
    return [
        existing.get(action_type) or InventoryActionPolicy(action_type=action_type, requires_approval=False)
        for action_type in ACTION_TYPES
    ]
