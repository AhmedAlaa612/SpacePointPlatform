from datetime import datetime, timezone
import re
import uuid
import time
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user, require_mentor
from app.db.session import get_db
from app.models.mentors import (
    MentorAvailability,
    MentorBooking,
    MentorDomain,
    MentorProfile,
    mentor_profile_domains,
)
from app.models.user import User
from app.schemas.mentors import (
    MentorApplyIn,
    MentorAvailabilityIn,
    MentorAvailabilityOut,
    MentorBookingOut,
    MentorPhotoUploadOut,
    MentorProfileOut,
    MentorProfileUpdateIn,
)
from app.services import storage

router = APIRouter(prefix="/mentor", tags=["Mentor Self-Service"])


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")


async def _generate_unique_mentor_slug(db: AsyncSession, base_name: str) -> str:
    base = _slugify(base_name) or "mentor"
    slug = base
    counter = 1
    while True:
        exists = await db.execute(select(MentorProfile.id).where(MentorProfile.slug == slug))
        if not exists.scalars().first():
            return slug
        slug = f"{base}-{counter}"
        counter += 1


def _serialize_mentor(mentor: MentorProfile, user: User) -> MentorProfileOut:
    return MentorProfileOut(
        id=mentor.id,
        user_id=mentor.user_id,
        slug=mentor.slug,
        headline=mentor.headline,
        company=mentor.company,
        bio=mentor.bio,
        missions_history=mentor.missions_history,
        what_i_can_help_with=mentor.what_i_can_help_with,
        contact_mode=mentor.contact_mode,
        google_meet_url=mentor.google_meet_url,
        status=mentor.status,
        is_active=mentor.is_active,
        is_published=mentor.is_published if mentor.is_published is not None else True,
        invite_code=mentor.invite_code,
        photo_url=mentor.photo_url or (user.photo_url if user else None),
        contact_email=mentor.contact_email,
        show_contact_button=mentor.show_contact_button if mentor.show_contact_button is not None else True,
        linkedin_url=mentor.linkedin_url,
        session_duration_minutes=mentor.session_duration_minutes,
        total_completed_minutes=mentor.total_completed_minutes,
        completed_sessions_count=mentor.completed_sessions_count,
        domains=mentor.domains,
        created_at=mentor.created_at,
        user_full_name=user.full_name,
        user_email=user.email,
        user_photo_url=user.photo_url if user else None,
        user_country=user.country if user else None,
    )


# ── Mentor Application ────────────────────────────────────────────────────────

@router.post("/apply", response_model=MentorProfileOut, status_code=status.HTTP_201_CREATED)
async def apply_to_be_mentor(
    body: MentorApplyIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Any registered user can apply to become a satellite & space mentor.
    Profile starts in 'applied' status with is_active=False until Ops approves it.
    """
    existing = await db.execute(
        select(MentorProfile)
        .where(MentorProfile.user_id == current_user.id)
        .options(selectinload(MentorProfile.domains))
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already submitted a mentor application or have a mentor profile",
        )

    slug = await _generate_unique_mentor_slug(db, current_user.full_name)

    profile = MentorProfile(
        user_id=current_user.id,
        slug=slug,
        headline=body.headline.strip(),
        company=body.company.strip(),
        bio=body.bio.strip(),
        missions_history=body.missions_history.strip() if body.missions_history else None,
        what_i_can_help_with=body.what_i_can_help_with.strip() if body.what_i_can_help_with else None,
        contact_mode=body.contact_mode,
        google_meet_url=body.google_meet_url.strip() if body.google_meet_url else None,
        invite_code=body.invite_code.strip() if body.invite_code else None,
        photo_url=body.photo_url.strip() if body.photo_url else None,
        contact_email=body.contact_email.strip().lower() if body.contact_email else None,
        show_contact_button=body.show_contact_button if body.show_contact_button is not None else True,
        linkedin_url=body.linkedin_url.strip() if body.linkedin_url else None,
        session_duration_minutes=body.session_duration_minutes or 30,
        status="applied",
        is_active=False,
        is_published=True,
    )

    if body.domain_ids:
        domains_result = await db.execute(
            select(MentorDomain).where(MentorDomain.id.in_(body.domain_ids))
        )
        profile.domains = list(domains_result.scalars().all())

    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return _serialize_mentor(profile, current_user)


# ── Mentor Profile Management ─────────────────────────────────────────────────

@router.get("/me", response_model=MentorProfileOut)
async def get_my_mentor_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Retrieve the logged-in user's mentor profile, domains, and stats."""
    result = await db.execute(
        select(MentorProfile)
        .where(MentorProfile.user_id == current_user.id)
        .options(selectinload(MentorProfile.domains))
    )
    mentor = result.scalars().first()
    if not mentor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mentor profile not found. Have you applied yet?",
        )
    return _serialize_mentor(mentor, current_user)


@router.put("/profile", response_model=MentorProfileOut)
async def update_my_mentor_profile(
    body: MentorProfileUpdateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update headline, bio, satellite missions, tags, contact mode, or Meet URL."""
    result = await db.execute(
        select(MentorProfile)
        .where(MentorProfile.user_id == current_user.id)
        .options(selectinload(MentorProfile.domains))
    )
    mentor = result.scalars().first()
    if not mentor:
        raise HTTPException(status_code=404, detail="Mentor profile not found")

    if body.headline is not None:
        mentor.headline = body.headline.strip()
    if body.company is not None:
        mentor.company = body.company.strip()
    if body.bio is not None:
        mentor.bio = body.bio.strip()
    if body.missions_history is not None:
        mentor.missions_history = body.missions_history.strip() if body.missions_history else None
    if body.what_i_can_help_with is not None:
        mentor.what_i_can_help_with = body.what_i_can_help_with.strip() if body.what_i_can_help_with else None
    if body.contact_mode is not None:
        mentor.contact_mode = body.contact_mode
    if body.session_duration_minutes is not None:
        mentor.session_duration_minutes = body.session_duration_minutes
    if body.google_meet_url is not None:
        mentor.google_meet_url = body.google_meet_url.strip() if body.google_meet_url else None
    if body.is_published is not None:
        mentor.is_published = body.is_published
    if body.invite_code is not None:
        mentor.invite_code = body.invite_code.strip() if body.invite_code else None
    if body.photo_url is not None:
        mentor.photo_url = body.photo_url.strip() if body.photo_url else None
    if body.contact_email is not None:
        mentor.contact_email = body.contact_email.strip().lower() if body.contact_email.strip() else None
    if body.show_contact_button is not None:
        mentor.show_contact_button = body.show_contact_button
    if body.linkedin_url is not None:
        mentor.linkedin_url = body.linkedin_url.strip() if body.linkedin_url.strip() else None

    if body.domain_ids is not None:
        domains_result = await db.execute(
            select(MentorDomain).where(MentorDomain.id.in_(body.domain_ids))
        )
        mentor.domains = list(domains_result.scalars().all())

    await db.commit()
    await db.refresh(mentor)
    return _serialize_mentor(mentor, current_user)


@router.post("/photo", response_model=MentorPhotoUploadOut)
async def upload_my_mentor_photo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload a portrait picture for the mentor profile.
    Supports both existing mentors and users preparing a new application."""
    data = await file.read()
    ext = ("." + file.filename.rsplit(".", 1)[-1]) if file.filename and "." in file.filename else ".png"
    path = f"mentors/{current_user.id}/portrait_{int(time.time())}{ext}"
    url = await storage.upload_file("profile_pictures", path, data, file.content_type or "image/png")

    # If mentor profile already exists, update and commit photo_url
    result = await db.execute(
        select(MentorProfile).where(MentorProfile.user_id == current_user.id)
    )
    mentor = result.scalars().first()
    if mentor:
        mentor.photo_url = url
        await db.commit()

    return MentorPhotoUploadOut(photo_url=url)


# ── Mentor Availability & Slots ───────────────────────────────────────────────

@router.get("/availability", response_model=list[MentorAvailabilityOut])
async def get_my_availability(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get the current mentor's scheduled availability rules."""
    mentor = (
        await db.execute(
            select(MentorProfile).where(MentorProfile.user_id == current_user.id)
        )
    ).scalars().first()
    if not mentor:
        raise HTTPException(status_code=404, detail="Mentor profile not found")

    availabilities = (
        await db.execute(
            select(MentorAvailability)
            .where(MentorAvailability.mentor_id == mentor.id)
            .order_by(MentorAvailability.day_of_week.asc(), MentorAvailability.start_time.asc())
        )
    ).scalars().all()
    return availabilities


@router.put("/availability", response_model=list[MentorAvailabilityOut])
async def set_my_availability(
    rules: List[MentorAvailabilityIn],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Replace all availability rules with the new set (weekly or specific dates)."""
    mentor = (
        await db.execute(
            select(MentorProfile).where(MentorProfile.user_id == current_user.id)
        )
    ).scalars().first()
    if not mentor:
        raise HTTPException(status_code=404, detail="Mentor profile not found")

    # Clear existing rules and replace
    existing_rules = (
        await db.execute(
            select(MentorAvailability).where(MentorAvailability.mentor_id == mentor.id)
        )
    ).scalars().all()
    for rule in existing_rules:
        await db.delete(rule)

    new_objects = []
    for r in rules:
        obj = MentorAvailability(
            mentor_id=mentor.id,
            day_of_week=r.day_of_week,
            specific_date=r.specific_date,
            start_time=r.start_time,
            end_time=r.end_time,
            timezone=r.timezone or "UTC",
            is_active=r.is_active,
        )
        db.add(obj)
        new_objects.append(obj)

    await db.commit()
    for obj in new_objects:
        await db.refresh(obj)
    return new_objects


# ── Mentor Bookings List ──────────────────────────────────────────────────────

@router.get("/bookings", response_model=list[MentorBookingOut])
async def get_my_bookings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all sessions and inquiries received by this mentor."""
    mentor = (
        await db.execute(
            select(MentorProfile).where(MentorProfile.user_id == current_user.id)
        )
    ).scalars().first()
    if not mentor:
        raise HTTPException(status_code=404, detail="Mentor profile not found")

    result = await db.execute(
        select(MentorBooking)
        .where(MentorBooking.mentor_id == mentor.id)
        .order_by(MentorBooking.created_at.desc())
    )
    bookings = result.scalars().all()
    return [
        MentorBookingOut(
            id=b.id,
            mentor_id=b.mentor_id,
            mentee_name=b.mentee_name,
            mentee_email=b.mentee_email,
            affiliation=b.affiliation,
            topics=b.topics,
            booking_type=b.booking_type,
            scheduled_start=b.scheduled_start,
            scheduled_end=b.scheduled_end,
            status=b.status,
            created_at=b.created_at,
            mentor_name=current_user.full_name,
        )
        for b in bookings
    ]
