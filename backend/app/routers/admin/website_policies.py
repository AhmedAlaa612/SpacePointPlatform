from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_policy import WebsitePolicy
from app.schemas.website_policy import (
    WebsitePolicyCreate,
    WebsitePolicyOut,
    WebsitePolicyUpdate,
)
from app.services.website_policies import seed_default_policies

router = APIRouter(prefix="/website/policies", tags=["admin-website-policies"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")


@router.get("", response_model=list[WebsitePolicyOut])
async def list_admin_policies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """List all policies (including draft/inactive) for Ops portal management."""
    await seed_default_policies(db)
    stmt = select(WebsitePolicy).order_by(
        WebsitePolicy.display_order.asc(), WebsitePolicy.created_at.asc()
    )
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.post("", response_model=WebsitePolicyOut, status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: WebsitePolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Create a new website policy."""
    clean_slug = body.slug.strip().lower()
    existing = (
        await db.execute(select(WebsitePolicy).where(WebsitePolicy.slug == clean_slug))
    ).scalars().first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A policy with slug '{clean_slug}' already exists",
        )

    data = body.model_dump()
    data["slug"] = clean_slug
    row = WebsitePolicy(**data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{policy_id}", response_model=WebsitePolicyOut)
async def get_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Get policy details by ID."""
    row = (
        await db.execute(select(WebsitePolicy).where(WebsitePolicy.id == policy_id))
    ).scalars().first()
    if row is None:
        raise _not_found()
    return row


@router.put("/{policy_id}", response_model=WebsitePolicyOut)
async def update_policy(
    policy_id: UUID,
    body: WebsitePolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Update policy details, content, or publication status."""
    row = (
        await db.execute(select(WebsitePolicy).where(WebsitePolicy.id == policy_id))
    ).scalars().first()
    if row is None:
        raise _not_found()

    updates = body.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"]:
        new_slug = updates["slug"].strip().lower()
        if new_slug != row.slug:
            existing = (
                await db.execute(
                    select(WebsitePolicy).where(
                        WebsitePolicy.slug == new_slug,
                        WebsitePolicy.id != policy_id,
                    )
                )
            ).scalars().first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"A policy with slug '{new_slug}' already exists",
                )
        updates["slug"] = new_slug

    for k, v in updates.items():
        setattr(row, k, v)

    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Remove a policy document."""
    row = (
        await db.execute(select(WebsitePolicy).where(WebsitePolicy.id == policy_id))
    ).scalars().first()
    if row is None:
        raise _not_found()

    await db.delete(row)
    await db.commit()
    return None
