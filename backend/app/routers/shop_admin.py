import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import (
    get_current_active_user,
    require_inventory_manage,
    require_storekeeper,
)
from app.db.session import get_db
from app.models.inventory.item import Item
from app.models.inventory.shop_item import ShopItem
from app.models.inventory.shop_order import ShopOrder, ShopOrderItem
from app.models.inventory.warehouse import Warehouse
from app.models.user import User
from app.schemas.shop import (
    ShopItemAdminResponse,
    ShopItemCreate,
    ShopItemUpdate,
    ShopOrderFulfillRequest,
    ShopOrderItemResponse,
    ShopOrderResponse,
)
from app.services.shop_service import (
    build_admin_shop_item_response,
    get_item_stock_breakdown,
    mark_order_fulfilled,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["inventory-shop-admin"])


@router.get("/admin/inventory/shop", response_model=List[ShopItemAdminResponse])
async def list_shop_items(
    search: Optional[str] = Query(None, description="Search by display name or slug"),
    is_published: Optional[bool] = Query(None, description="Filter by published status"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_storekeeper),
):
    """List all products configured in the shop with live inventory totals and warehouse breakdowns."""
    stmt = select(ShopItem).options(selectinload(ShopItem.item)).order_by(ShopItem.display_order.asc(), ShopItem.created_at.desc())

    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(ShopItem.display_name.ilike(term), ShopItem.slug.ilike(term)))
    if is_published is not None:
        stmt = stmt.where(ShopItem.is_published == is_published)

    result = await db.execute(stmt)
    shop_items = result.scalars().all()

    responses = []
    for item in shop_items:
        resp = await build_admin_shop_item_response(db, item)
        responses.append(resp)

    return responses


@router.get("/admin/inventory/shop/available-items")
async def list_available_catalog_items(
    search: Optional[str] = Query(None, description="Search catalogue items"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_storekeeper),
):
    """List catalog items that are not yet added to the shop."""
    # Subquery for already added item IDs
    existing_subq = select(ShopItem.item_id)

    stmt = (
        select(Item)
        .where(Item.id.not_in(existing_subq))
        .order_by(Item.name.asc())
        .limit(100)
    )

    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(Item.name.ilike(term), Item.code.ilike(term)))

    result = await db.execute(stmt)
    items = result.scalars().all()

    output = []
    for item in items:
        total_stock, breakdown = await get_item_stock_breakdown(db, item.id)
        output.append({
            "id": str(item.id),
            "name": item.name,
            "code": item.code,
            "category": item.category,
            "unit": item.unit,
            "total_stock": total_stock,
            "warehouse_breakdown": [b.model_dump() for b in breakdown],
        })

    return output


@router.post("/admin/inventory/shop", response_model=ShopItemAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_shop_item(
    payload: ShopItemCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_inventory_manage),
):
    """Add a catalogue item to the shop with pricing and commercial details."""
    # Verify catalogue item exists
    item = (await db.execute(select(Item).where(Item.id == payload.item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Catalogue item not found")

    # Check if already in shop
    existing = (await db.execute(select(ShopItem).where(ShopItem.item_id == payload.item_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="This catalogue item is already in the shop")

    # Check slug uniqueness
    slug_existing = (await db.execute(select(ShopItem).where(ShopItem.slug == payload.slug))).scalar_one_or_none()
    if slug_existing:
        raise HTTPException(status_code=400, detail="Slug already in use by another shop product")

    shop_item = ShopItem(
        item_id=payload.item_id,
        slug=payload.slug.strip().lower(),
        display_name=payload.display_name.strip(),
        subtitle=payload.subtitle,
        description=payload.description,
        price_aed=payload.price_aed,
        compare_at_price_aed=payload.compare_at_price_aed,
        cover_image_url=payload.cover_image_url,
        gallery_images=payload.gallery_images or [],
        is_published=payload.is_published,
        is_preorder_enabled=payload.is_preorder_enabled,
        preorder_message=payload.preorder_message,
        display_order=payload.display_order,
    )
    db.add(shop_item)
    await db.commit()
    await db.refresh(shop_item)

    # Re-fetch with item relationship
    res = await db.execute(select(ShopItem).options(selectinload(ShopItem.item)).where(ShopItem.id == shop_item.id))
    reloaded = res.scalar_one()
    return await build_admin_shop_item_response(db, reloaded)


@router.get("/admin/inventory/shop/{shop_item_id}", response_model=ShopItemAdminResponse)
async def get_shop_item(
    shop_item_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_storekeeper),
):
    """Retrieve details and real-time inventory for a specific shop item."""
    res = await db.execute(
        select(ShopItem).options(selectinload(ShopItem.item)).where(ShopItem.id == shop_item_id)
    )
    shop_item = res.scalar_one_or_none()
    if not shop_item:
        raise HTTPException(status_code=404, detail="Shop item not found")

    return await build_admin_shop_item_response(db, shop_item)


@router.put("/admin/inventory/shop/{shop_item_id}", response_model=ShopItemAdminResponse)
async def update_shop_item(
    shop_item_id: UUID,
    payload: ShopItemUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_inventory_manage),
):
    """Update shop item pricing, publishing status, or content."""
    res = await db.execute(
        select(ShopItem).options(selectinload(ShopItem.item)).where(ShopItem.id == shop_item_id)
    )
    shop_item = res.scalar_one_or_none()
    if not shop_item:
        raise HTTPException(status_code=404, detail="Shop item not found")

    if payload.slug is not None and payload.slug != shop_item.slug:
        slug_check = (await db.execute(select(ShopItem).where(ShopItem.slug == payload.slug, ShopItem.id != shop_item_id))).scalar_one_or_none()
        if slug_check:
            raise HTTPException(status_code=400, detail="Slug already in use by another shop product")
        shop_item.slug = payload.slug.strip().lower()

    if payload.display_name is not None:
        shop_item.display_name = payload.display_name.strip()
    if payload.subtitle is not None:
        shop_item.subtitle = payload.subtitle
    if payload.description is not None:
        shop_item.description = payload.description
    if payload.price_aed is not None:
        shop_item.price_aed = payload.price_aed
    if payload.compare_at_price_aed is not None:
        shop_item.compare_at_price_aed = payload.compare_at_price_aed
    if payload.cover_image_url is not None:
        shop_item.cover_image_url = payload.cover_image_url
    if payload.gallery_images is not None:
        shop_item.gallery_images = payload.gallery_images
    if payload.is_published is not None:
        shop_item.is_published = payload.is_published
    if payload.is_preorder_enabled is not None:
        shop_item.is_preorder_enabled = payload.is_preorder_enabled
    if payload.preorder_message is not None:
        shop_item.preorder_message = payload.preorder_message
    if payload.display_order is not None:
        shop_item.display_order = payload.display_order

    await db.commit()
    await db.refresh(shop_item)
    return await build_admin_shop_item_response(db, shop_item)


@router.delete("/admin/inventory/shop/{shop_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop_item(
    shop_item_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_inventory_manage),
):
    """Remove an item from the shop (does NOT delete the underlying catalog item)."""
    res = await db.execute(select(ShopItem).where(ShopItem.id == shop_item_id))
    shop_item = res.scalar_one_or_none()
    if not shop_item:
        raise HTTPException(status_code=404, detail="Shop item not found")

    await db.delete(shop_item)
    await db.commit()
    return None


@router.get("/admin/inventory/shop/orders", response_model=List[ShopOrderResponse])
async def list_shop_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    order_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search by order number or customer email"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_storekeeper),
):
    """List customer shop orders and pre-orders."""
    stmt = (
        select(ShopOrder)
        .options(
            selectinload(ShopOrder.items),
            selectinload(ShopOrder.fulfilled_warehouse),
        )
        .order_by(ShopOrder.created_at.desc())
    )

    if status_filter:
        stmt = stmt.where(ShopOrder.status == status_filter)
    if order_type:
        stmt = stmt.where(ShopOrder.order_type == order_type)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                ShopOrder.order_number.ilike(term),
                ShopOrder.customer_email.ilike(term),
                ShopOrder.customer_name.ilike(term),
            )
        )

    res = await db.execute(stmt)
    orders = res.scalars().all()

    output = []
    for order in orders:
        items_out = [
            ShopOrderItemResponse(
                id=item.id,
                shop_item_id=item.shop_item_id,
                item_name=item.item_name,
                unit_price_aed=item.unit_price_aed,
                quantity=item.quantity,
                is_preorder=item.is_preorder,
            )
            for item in order.items
        ]
        output.append(
            ShopOrderResponse(
                id=order.id,
                order_number=order.order_number,
                customer_name=order.customer_name,
                customer_email=order.customer_email,
                customer_phone=order.customer_phone,
                shipping_address=order.shipping_address or {},
                status=order.status,
                order_type=order.order_type,
                total_amount_aed=order.total_amount_aed,
                currency=order.currency,
                stripe_payment_intent_id=order.stripe_payment_intent_id,
                stripe_checkout_session_id=order.stripe_checkout_session_id,
                fulfilled_warehouse_id=order.fulfilled_warehouse_id,
                fulfilled_warehouse_name=order.fulfilled_warehouse.name if order.fulfilled_warehouse else None,
                fulfilled_at=order.fulfilled_at,
                fulfillment_notes=order.fulfillment_notes,
                created_at=order.created_at,
                items=items_out,
            )
        )

    return output


@router.get("/admin/inventory/shop/orders/{order_id}", response_model=ShopOrderResponse)
async def get_shop_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_storekeeper),
):
    """Get single order details."""
    stmt = (
        select(ShopOrder)
        .options(
            selectinload(ShopOrder.items),
            selectinload(ShopOrder.fulfilled_warehouse),
        )
        .where(ShopOrder.id == order_id)
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    items_out = [
        ShopOrderItemResponse(
            id=item.id,
            shop_item_id=item.shop_item_id,
            item_name=item.item_name,
            unit_price_aed=item.unit_price_aed,
            quantity=item.quantity,
            is_preorder=item.is_preorder,
        )
        for item in order.items
    ]

    return ShopOrderResponse(
        id=order.id,
        order_number=order.order_number,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        customer_phone=order.customer_phone,
        shipping_address=order.shipping_address or {},
        status=order.status,
        order_type=order.order_type,
        total_amount_aed=order.total_amount_aed,
        currency=order.currency,
        stripe_payment_intent_id=order.stripe_payment_intent_id,
        stripe_checkout_session_id=order.stripe_checkout_session_id,
        fulfilled_warehouse_id=order.fulfilled_warehouse_id,
        fulfilled_warehouse_name=order.fulfilled_warehouse.name if order.fulfilled_warehouse else None,
        fulfilled_at=order.fulfilled_at,
        fulfillment_notes=order.fulfillment_notes,
        created_at=order.created_at,
        items=items_out,
    )


@router.post("/admin/inventory/shop/orders/{order_id}/fulfill", response_model=ShopOrderResponse)
async def fulfill_shop_order(
    order_id: UUID,
    payload: ShopOrderFulfillRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_inventory_manage),
):
    """Mark an order fulfilled and deduct physical inventory from the selected warehouse."""
    try:
        order = await mark_order_fulfilled(
            db=db,
            order_id=order_id,
            warehouse_id=payload.warehouse_id,
            user_id=user.id,
            notes=payload.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Reload warehouse
    if order.fulfilled_warehouse_id:
        res = await db.execute(select(Warehouse).where(Warehouse.id == order.fulfilled_warehouse_id))
        wh = res.scalar_one_or_none()
        order.fulfilled_warehouse = wh

    items_out = [
        ShopOrderItemResponse(
            id=item.id,
            shop_item_id=item.shop_item_id,
            item_name=item.item_name,
            unit_price_aed=item.unit_price_aed,
            quantity=item.quantity,
            is_preorder=item.is_preorder,
        )
        for item in order.items
    ]

    return ShopOrderResponse(
        id=order.id,
        order_number=order.order_number,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        customer_phone=order.customer_phone,
        shipping_address=order.shipping_address or {},
        status=order.status,
        order_type=order.order_type,
        total_amount_aed=order.total_amount_aed,
        currency=order.currency,
        stripe_payment_intent_id=order.stripe_payment_intent_id,
        stripe_checkout_session_id=order.stripe_checkout_session_id,
        fulfilled_warehouse_id=order.fulfilled_warehouse_id,
        fulfilled_warehouse_name=order.fulfilled_warehouse.name if order.fulfilled_warehouse else None,
        fulfilled_at=order.fulfilled_at,
        fulfillment_notes=order.fulfillment_notes,
        created_at=order.created_at,
        items=items_out,
    )
