"""Booth router — public kiosk endpoints and operations management endpoints."""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.booth import BoothEvent, BoothPhoto
from app.models.instructors.invitation_code import InvitationCode
from app.models.user import User
from app.services import storage_r2
from app.services.booth import get_booth_analytics, process_booth_capture

# Public router for booth kiosk
public_router = APIRouter(prefix="/public/booth", tags=["public-booth"])

# Ops router for platform administration
ops_router = APIRouter(
    prefix="/operations/booth",
    tags=["operations-booth"],
    dependencies=[Depends(require_operations)],
)


# ===================== SCHEMAS =====================

class BoothCaptureRequest(BaseModel):
    event_slug: str
    participant_name: str
    participant_email: EmailStr
    image_base64: str
    satellite_id: Optional[str] = None


class BoothEventCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    invitation_code_id: Optional[UUID] = None
    auto_create_lms_account: bool = True
    email_subject: Optional[str] = None
    email_body_template: Optional[str] = None


class BoothEventUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    invitation_code_id: Optional[UUID] = None
    auto_create_lms_account: Optional[bool] = None
    email_subject: Optional[str] = None
    email_body_template: Optional[str] = None


class BoothEventOut(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str]
    is_active: bool
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    invitation_code_id: Optional[UUID]
    invitation_code_str: Optional[str] = None
    auto_create_lms_account: bool
    email_subject: Optional[str]
    created_at: datetime
    total_photos: int = 0
    new_lms_users_created: int = 0
    logged_in_students: int = 0

    class Config:
        from_attributes = True


class BoothPhotoOut(BaseModel):
    id: UUID
    event_id: UUID
    participant_name: str
    participant_email: str
    storage_path: str
    satellite_id: Optional[str]
    user_id: Optional[UUID]
    is_new_lms_user: bool
    email_sent: bool
    email_sent_at: Optional[datetime]
    email_error: Optional[str]
    created_at: datetime
    student_logged_in: bool = False
    last_login_at: Optional[datetime] = None
    photo_url: Optional[str] = None

    class Config:
        from_attributes = True


# ===================== PUBLIC ENDPOINTS =====================

@public_router.get("/events/{slug}")
async def get_public_booth_event(slug: str, db: AsyncSession = Depends(get_db)):
    """Allows kiosk app to fetch the event name and confirm it is active."""
    clean_slug = slug.strip().lower()
    stmt = select(BoothEvent).where(BoothEvent.slug == clean_slug)
    event = (await db.execute(stmt)).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "id": str(event.id),
        "name": event.name,
        "slug": event.slug,
        "is_active": event.is_active,
        "auto_create_lms_account": event.auto_create_lms_account,
    }


@public_router.post("/capture")
async def public_booth_capture(
    payload: BoothCaptureRequest,
    db: AsyncSession = Depends(get_db),
):
    """Kiosk entry point: receives photo and participant info, uploads to R2,
    creates student LMS account if eligible, and sends branded photo email."""
    return await process_booth_capture(
        db,
        event_slug=payload.event_slug,
        participant_name=payload.participant_name,
        participant_email=payload.participant_email,
        image_base64=payload.image_base64,
        satellite_id=payload.satellite_id,
    )


# ===================== OPS / ADMIN ENDPOINTS =====================

@ops_router.get("/analytics")
async def get_analytics(
    event_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_booth_analytics(db, event_id=event_id)


@ops_router.get("/events", response_model=List[BoothEventOut])
async def list_booth_events(db: AsyncSession = Depends(get_db)):
    """List all booth events with aggregate counters."""
    stmt = (
        select(BoothEvent)
        .options(selectinload(BoothEvent.invitation_code))
        .order_by(BoothEvent.created_at.desc())
    )
    events = (await db.execute(stmt)).scalars().all()

    out: List[BoothEventOut] = []
    for ev in events:
        stats = await get_booth_analytics(db, event_id=ev.id)
        out.append(
            BoothEventOut(
                id=ev.id,
                name=ev.name,
                slug=ev.slug,
                description=ev.description,
                is_active=ev.is_active,
                starts_at=ev.starts_at,
                ends_at=ev.ends_at,
                invitation_code_id=ev.invitation_code_id,
                invitation_code_str=ev.invitation_code.code if ev.invitation_code else None,
                auto_create_lms_account=ev.auto_create_lms_account,
                email_subject=ev.email_subject,
                created_at=ev.created_at,
                total_photos=stats["total_photos"],
                new_lms_users_created=stats["new_lms_users_created"],
                logged_in_students=stats["logged_in_students"],
            )
        )
    return out


@ops_router.post("/events", response_model=BoothEventOut)
async def create_booth_event(
    payload: BoothEventCreate,
    db: AsyncSession = Depends(get_db),
):
    # Auto slugify if not provided
    slug = payload.slug
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", payload.name.lower()).strip("-")
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")

    # Check slug uniqueness
    existing = (await db.execute(select(BoothEvent).where(BoothEvent.slug == slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"An event with slug '{slug}' already exists")

    event = BoothEvent(
        name=payload.name.strip(),
        slug=slug,
        description=payload.description,
        is_active=payload.is_active,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        invitation_code_id=payload.invitation_code_id,
        auto_create_lms_account=payload.auto_create_lms_account,
        email_subject=payload.email_subject,
        email_body_template=payload.email_body_template,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    return BoothEventOut(
        id=event.id,
        name=event.name,
        slug=event.slug,
        description=event.description,
        is_active=event.is_active,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        invitation_code_id=event.invitation_code_id,
        auto_create_lms_account=event.auto_create_lms_account,
        email_subject=event.email_subject,
        created_at=event.created_at,
        total_photos=0,
        new_lms_users_created=0,
        logged_in_students=0,
    )


@ops_router.get("/events/{event_id}", response_model=BoothEventOut)
async def get_booth_event(event_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(BoothEvent)
        .options(selectinload(BoothEvent.invitation_code))
        .where(BoothEvent.id == event_id)
    )
    event = (await db.execute(stmt)).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    stats = await get_booth_analytics(db, event_id=event.id)
    return BoothEventOut(
        id=event.id,
        name=event.name,
        slug=event.slug,
        description=event.description,
        is_active=event.is_active,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        invitation_code_id=event.invitation_code_id,
        invitation_code_str=event.invitation_code.code if event.invitation_code else None,
        auto_create_lms_account=event.auto_create_lms_account,
        email_subject=event.email_subject,
        created_at=event.created_at,
        total_photos=stats["total_photos"],
        new_lms_users_created=stats["new_lms_users_created"],
        logged_in_students=stats["logged_in_students"],
    )


@ops_router.patch("/events/{event_id}", response_model=BoothEventOut)
async def update_booth_event(
    event_id: UUID,
    payload: BoothEventUpdate,
    db: AsyncSession = Depends(get_db),
):
    event = await db.get(BoothEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    data = payload.dict(exclude_unset=True)
    if "slug" in data and data["slug"]:
        new_slug = re.sub(r"[^a-z0-9]+", "-", data["slug"].lower()).strip("-")
        existing = (
            await db.execute(select(BoothEvent).where(BoothEvent.slug == new_slug, BoothEvent.id != event_id))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail=f"Slug '{new_slug}' is already taken")
        event.slug = new_slug
        del data["slug"]

    for k, v in data.items():
        setattr(event, k, v)

    await db.commit()
    await db.refresh(event)
    stats = await get_booth_analytics(db, event_id=event.id)
    return BoothEventOut(
        id=event.id,
        name=event.name,
        slug=event.slug,
        description=event.description,
        is_active=event.is_active,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        invitation_code_id=event.invitation_code_id,
        auto_create_lms_account=event.auto_create_lms_account,
        email_subject=event.email_subject,
        created_at=event.created_at,
        total_photos=stats["total_photos"],
        new_lms_users_created=stats["new_lms_users_created"],
        logged_in_students=stats["logged_in_students"],
    )


@ops_router.delete("/events/{event_id}")
async def delete_booth_event(event_id: UUID, db: AsyncSession = Depends(get_db)):
    event = await db.get(BoothEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(event)
    await db.commit()
    return {"success": True}


@ops_router.get("/events/{event_id}/photos")
async def list_event_photos(
    event_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List paginated photos for an event with student login status and presigned photo URLs."""
    stmt = (
        select(BoothPhoto, User)
        .outerjoin(User, BoothPhoto.user_id == User.id)
        .where(BoothPhoto.event_id == event_id)
        .order_by(BoothPhoto.created_at.desc())
    )

    if search:
        search_pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            (func.lower(BoothPhoto.participant_name).like(search_pattern))
            | (func.lower(BoothPhoto.participant_email).like(search_pattern))
        )

    # Count total
    count_stmt = select(func.count(BoothPhoto.id)).where(BoothPhoto.event_id == event_id)
    if search:
        count_stmt = count_stmt.where(
            (func.lower(BoothPhoto.participant_name).like(search_pattern))
            | (func.lower(BoothPhoto.participant_email).like(search_pattern))
        )
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginate
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    rows = (await db.execute(stmt)).all()

    bucket_name = settings.R2_BOOTH_BUCKET or "spacepoint-booth"
    items: List[BoothPhotoOut] = []
    for photo, user in rows:
        # Generate presigned URL for preview/download (valid 1 hour)
        photo_url = None
        try:
            # storage_path is "photos/{slug}/{uuid}.jpg" -> bucket="photos", path="{slug}/{uuid}.jpg"
            parts = photo.storage_path.split("/", 1)
            b = parts[0] if len(parts) > 1 else "photos"
            p = parts[1] if len(parts) > 1 else parts[0]
            photo_url = await storage_r2.get_signed_url(bucket=b, path=p, expires_in=3600, r2_bucket=bucket_name)
        except Exception:
            pass

        items.append(
            BoothPhotoOut(
                id=photo.id,
                event_id=photo.event_id,
                participant_name=photo.participant_name,
                participant_email=photo.participant_email,
                storage_path=photo.storage_path,
                satellite_id=photo.satellite_id,
                user_id=photo.user_id,
                is_new_lms_user=photo.is_new_lms_user,
                email_sent=photo.email_sent,
                email_sent_at=photo.email_sent_at,
                email_error=photo.email_error,
                created_at=photo.created_at,
                student_logged_in=user.last_login_at is not None if user else False,
                last_login_at=user.last_login_at if user else None,
                photo_url=photo_url,
            )
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
    }


@ops_router.post("/photos/{photo_id}/resend-email")
async def resend_booth_photo_email(photo_id: UUID, db: AsyncSession = Depends(get_db)):
    """Resend the photo email to the participant."""
    photo = await db.get(BoothPhoto, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo record not found")

    event = await db.get(BoothEvent, photo.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Associated event not found")

    bucket_name = photo.storage_bucket or settings.R2_BOOTH_BUCKET or "spacepoint-booth"
    parts = photo.storage_path.split("/", 1)
    b = parts[0] if len(parts) > 1 else "photos"
    p = parts[1] if len(parts) > 1 else parts[0]

    try:
        image_bytes = await storage_r2.download_file(bucket=b, path=p, r2_bucket=bucket_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch photo from storage: {exc}")

    # If new user and never logged in, regenerate activation link
    activation_link = None
    if photo.is_new_lms_user and photo.user_id:
        user = await db.get(User, photo.user_id)
        if user and user.last_login_at is None:
            activation_link = build_set_password_link(user)

    captured_at_str = photo.created_at.strftime("%Y-%m-%d %H:%M")
    email_html = _build_photo_email_html(
        participant_name=photo.participant_name,
        photo_id=str(photo.id)[:8],
        captured_at_str=captured_at_str,
        activation_link=activation_link,
        event_name=event.name,
    )

    from app.services.booth import _build_photo_email_html
    subject = event.email_subject or f"Your CubeSat Photo — SpacePoint × {event.name}"

    from app.services.email import send_email
    try:
        await send_email(
            to=photo.participant_email,
            subject=subject,
            body=email_html,
            html=True,
            attachments=[(f"cubesat_{str(photo.id)[:8]}.jpg", image_bytes, "jpeg")],
            inline_images={"cubesat-photo": (image_bytes, "image", "jpeg")},
        )
        photo.email_sent = True
        photo.email_sent_at = datetime.now(timezone.utc)
        photo.email_error = None
        await db.commit()
    except Exception as exc:
        photo.email_error = str(exc)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to send email: {exc}")

    return {"success": True, "message": "Email resent successfully"}
