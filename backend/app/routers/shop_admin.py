"""Ground Station shop operations surface (Step 7).

Catalogue CRUD plus order tracking and warehouse fulfillment. Guarded by
`require_inventory_manage` (operations + COO; admin passes everywhere):
fulfillment writes stock levels and ledger movements, so it sits with
the inventory write role rather than the marketing-admin role.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_inventory_manage
from app.db.session import get_db
from app.models.inventory.shop_item import ShopItem
from app.models.inventory.shop_order import ShopOrder
from app.models.user import User
from app.schemas.shop import (
    ShopItemAdminOut,
    ShopItemCreate,
    ShopItemUpdate,
    ShopOrderFulfillIn,
    ShopOrderOut,
)
from app.services.shop_service import SHOP_ORDER_STATUSES, fulfill_order

router = APIRouter(prefix="/shop", tags=["shop-admin"])


async def _get_item_or_404(db: AsyncSession, item_id: UUID) -> ShopItem:
    row = await db.get(ShopItem, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Shop item not found")
    return row


async def _get_order_or_404(db: AsyncSession, order_id: UUID) -> ShopOrder:
    row = await db.get(ShopOrder, order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return row


@router.get("/items", response_model=list[ShopItemAdminOut])
async def list_shop_items(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_inventory_manage)
):
    rows = (
        await db.execute(select(ShopItem).order_by(ShopItem.display_order, ShopItem.display_name))
    ).scalars().all()
    return rows


@router.post("/items", response_model=ShopItemAdminOut, status_code=status.HTTP_201_CREATED)
async def create_shop_item(
    body: ShopItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage),
):
    data = body.model_dump()
    data["slug"] = data["slug"].strip()
    if (
        await db.execute(select(ShopItem.id).where(ShopItem.slug == data["slug"]))
    ).first() is not None:
        raise HTTPException(status_code=409, detail="Slug already in use")
    row = ShopItem(**data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/items/{item_id}", response_model=ShopItemAdminOut)
async def update_shop_item(
    item_id: UUID,
    body: ShopItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage),
):
    row = await _get_item_or_404(db, item_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("slug"):
        data["slug"] = data["slug"].strip()
        if (
            await db.execute(
                select(ShopItem.id).where(ShopItem.slug == data["slug"], ShopItem.id != item_id)
            )
        ).first() is not None:
            raise HTTPException(status_code=409, detail="Slug already in use")
    for field, value in data.items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage),
):
    row = await _get_item_or_404(db, item_id)
    await db.delete(row)
    await db.commit()
    return None


@router.get("/orders", response_model=list[ShopOrderOut])
async def list_shop_orders(
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage),
):
    if status is not None and status not in SHOP_ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status: {status}")
    stmt = select(ShopOrder).order_by(ShopOrder.created_at.desc())
    if status is not None:
        stmt = stmt.where(ShopOrder.status == status)
    return (await db.execute(stmt)).scalars().all()


@router.get("/orders/{order_id}", response_model=ShopOrderOut)
async def get_shop_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage),
):
    return await _get_order_or_404(db, order_id)


@router.post("/orders/{order_id}/fulfill", response_model=ShopOrderOut)
async def fulfill_shop_order(
    order_id: UUID,
    body: ShopOrderFulfillIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage),
):
    order = await _get_order_or_404(db, order_id)
    return await fulfill_order(
        db,
        order,
        warehouse_id=body.warehouse_id,
        notes=body.notes,
        actor_user_id=current_user.id,
    )
