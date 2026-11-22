"""Program Landing Page (unified on WebsiteEvent) endpoints.

Accessible to:
- SpacePoint Admin / Operations on ANY program (`org_access = "ops"`)
- Partner Org Owners / Coordinators on their OWN org-owned program when
  `organization.program_page_access` is `"review"` or `"direct"`.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_session_delivery
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.sessions.program import Program
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import WebsiteEvent
from app.schemas.website_event import WebsiteEventOut, WebsiteEventUpdate
from app.services.notification import create_notification
from app.services.org_access import is_ops_or_admin, is_program_org_manager
from app.services.program_web_live import (
    EVENT_LIVE_FIELDS,
    invalidate_program_web_cache,
)
from app.services.program_web_pages import ensure_program_landing_draft
from app.services.website_events import serialize_website_events, slugify_event

router = APIRouter(prefix="/sessions/programs", tags=["program-landing-pages"])


class ResetFieldIn(BaseModel):
    field: str


async def _require_landing_page_access(
    db: AsyncSession,
    program_id: UUID,
    current_user: User,
) -> tuple[Program, str]:
    """Return `(program, access_level)` where `access_level` is `ops | direct | review`."""
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    if is_ops_or_admin(current_user):
        return program, "ops"

    if not await is_program_org_manager(db, program_id, current_user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only SpacePoint Operations or the owning organization's managers can manage this program's landing page.",
        )

    org = await db.get(Organization, program.organization_id) if program.organization_id else None
    access = (getattr(org, "program_page_access", None) or "disabled").strip().lower() if org else "disabled"
    if access not in ("review", "direct"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Program landing pages are not enabled for your organization. Contact SpacePoint Operations.",
        )
    return program, access


async def _serialize_single(
    db: AsyncSession,
    ev: WebsiteEvent,
    access_level: str,
) -> dict:
    item = (await serialize_website_events(db, [ev], include_admin_meta=True, use_cache=False))[0]
    item["org_access"] = access_level
    return item


@router.get("/{program_id}/landing-page", response_model=WebsiteEventOut | None)
async def get_program_landing_page(
    program_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    program, access = await _require_landing_page_access(db, program_id, current_user)
    ev = (
        await db.execute(select(WebsiteEvent).where(WebsiteEvent.program_id == program.id))
    ).scalars().first()
    if ev is None:
        return None
    return await _serialize_single(db, ev, access)


@router.post("/{program_id}/landing-page", response_model=WebsiteEventOut)
async def create_program_landing_page(
    program_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    program, access = await _require_landing_page_access(db, program_id, current_user)
    ev = await ensure_program_landing_draft(
        db, program, created_by_user_id=current_user.id, commit=True
    )
    return await _serialize_single(db, ev, access)


@router.put("/{program_id}/landing-page", response_model=WebsiteEventOut)
async def update_program_landing_page(
    program_id: UUID,
    body: WebsiteEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    program, access = await _require_landing_page_access(db, program_id, current_user)
    ev = await ensure_program_landing_draft(
        db, program, created_by_user_id=current_user.id, commit=True
    )

    data = body.model_dump(exclude_unset=True)
    # Never let partners silently flip is_published via PUT when restricted to review
    if access == "review":
        data.pop("is_published", None)

    if "slug" in data and data["slug"]:
        clean_slug = slugify_event(data["slug"])
        conflict = (
            await db.execute(
                select(WebsiteEvent.id).where(
                    WebsiteEvent.slug == clean_slug,
                    WebsiteEvent.id != ev.id,
                )
            )
        ).first()
        if conflict:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Slug '{clean_slug}' is already in use by another event.",
            )
        data["slug"] = clean_slug

    if "country" in data and data["country"]:
        c = data["country"].strip().lower()
        data["country"] = "uae" if c == "ae" else c

    # Merge explicit overrides dict if sent
    existing_overrides = dict(ev.overrides or {})
    if "overrides" in data and isinstance(data["overrides"], dict):
        existing_overrides = dict(data["overrides"])
        data.pop("overrides")

    # If live_linked and caller edited a live field directly, record it in overrides
    # so the live resolver respects the editor's change until Reset to live.
    if ev.live_linked:
        for lf in EVENT_LIVE_FIELDS:
            if lf in data and lf not in ("steps", "curriculum_chapters"):
                existing_overrides[lf] = data[lf]

    ev.overrides = existing_overrides

    for field, value in data.items():
        if hasattr(ev, field) and field not in ("id", "program_id", "organization_id", "preview_token"):
            setattr(ev, field, value)

    ev.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ev)
    invalidate_program_web_cache(program.id)
    return await _serialize_single(db, ev, access)


@router.post("/{program_id}/landing-page/reset-field", response_model=WebsiteEventOut)
async def reset_program_landing_page_field(
    program_id: UUID,
    body: ResetFieldIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    program, access = await _require_landing_page_access(db, program_id, current_user)
    ev = await ensure_program_landing_draft(
        db, program, created_by_user_id=current_user.id, commit=True
    )
    ov = dict(ev.overrides or {})
    ov.pop(body.field, None)
    ev.overrides = ov
    ev.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ev)
    invalidate_program_web_cache(program.id)
    return await _serialize_single(db, ev, access)


@router.post("/{program_id}/landing-page/publish", response_model=WebsiteEventOut)
async def publish_program_landing_page(
    program_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    program, access = await _require_landing_page_access(db, program_id, current_user)
    ev = await ensure_program_landing_draft(
        db, program, created_by_user_id=current_user.id, commit=True
    )

    if access in ("ops", "direct"):
        ev.is_published = True
        ev.submitted_for_review_at = None
    else:
        # access == "review": submit for SpacePoint Ops approval
        ev.submitted_for_review_at = datetime.now(timezone.utc)
        ops_users = (
            await db.execute(select(User).where(User.status == "active"))
        ).scalars().all()
        for u in ops_users:
            roles = getattr(u, "role_values", set())
            if UserRole.admin.value in roles or UserRole.operations.value in roles:
                await create_notification(
                    db,
                    user_id=u.id,
                    title="Program Landing Page Submitted for Review",
                    body=f"Partner submitted '{program.name}' landing page for publishing approval.",
                    type="website_review",
                    link=f"/operations/programs/{program.id}",
                )

    ev.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ev)
    invalidate_program_web_cache(program.id)
    return await _serialize_single(db, ev, access)


@router.post("/{program_id}/landing-page/unpublish", response_model=WebsiteEventOut)
async def unpublish_program_landing_page(
    program_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    program, access = await _require_landing_page_access(db, program_id, current_user)
    ev = await ensure_program_landing_draft(
        db, program, created_by_user_id=current_user.id, commit=True
    )
    ev.is_published = False
    ev.submitted_for_review_at = None
    ev.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ev)
    invalidate_program_web_cache(program.id)
    return await _serialize_single(db, ev, access)


@router.post("/{program_id}/landing-page/preview-token/regenerate", response_model=WebsiteEventOut)
async def regenerate_program_landing_preview_token(
    program_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    program, access = await _require_landing_page_access(db, program_id, current_user)
    ev = await ensure_program_landing_draft(
        db, program, created_by_user_id=current_user.id, commit=True
    )
    ev.preview_token = secrets.token_urlsafe(24)
    ev.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ev)
    return await _serialize_single(db, ev, access)
