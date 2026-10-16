from datetime import date, datetime, time, timedelta, timezone
import secrets
from typing import List, Optional
import zoneinfo
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    AvailableSlotOut,
    MentorBookIn,
    MentorBookingOut,
    MentorProfileOut,
)

router = APIRouter(tags=["Public Mentors & Booking"])


def _serialize_public_mentor(mentor: MentorProfile) -> MentorProfileOut:
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
        google_meet_url=None,  # Hide raw Meet link on public listings
        status=mentor.status,
        is_active=mentor.is_active,
        session_duration_minutes=mentor.session_duration_minutes,
        total_completed_minutes=mentor.total_completed_minutes,
        completed_sessions_count=mentor.completed_sessions_count,
        domains=mentor.domains,
        created_at=mentor.created_at,
        user_full_name=mentor.user.full_name if mentor.user else None,
        user_email=None,  # Protect mentor email from public scraping
        contact_email=None,  # Protect contact email from public scraping
        show_contact_button=mentor.show_contact_button if mentor.show_contact_button is not None else True,
        linkedin_url=mentor.linkedin_url,
        photo_url=mentor.photo_url or (mentor.user.photo_url if mentor.user else None),
        user_photo_url=mentor.user.photo_url if mentor.user else None,
        user_country=mentor.user.country if mentor.user else None,
    )


# ── Public Mentors Directory ──────────────────────────────────────────────────

@router.get("/mentors", response_model=list[MentorProfileOut])
async def list_public_mentors(
    domain: str | None = Query(default=None, description="Domain tag slug"),
    company: str | None = Query(default=None, description="Filter by space company/agency"),
    mode: str | None = Query(default=None, description="'email' or 'calendar'"),
    q: str | None = Query(default=None, description="Search keyword across name, bio, missions"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Browse verified satellite and space mentors. Gated to approved & active mentors only."""
    query = (
        select(MentorProfile)
        .where(
            MentorProfile.is_active.is_(True),
            MentorProfile.status == "approved",
            MentorProfile.is_published.is_(True),
        )
        .options(selectinload(MentorProfile.domains), selectinload(MentorProfile.user))
        .order_by(MentorProfile.total_completed_minutes.desc(), MentorProfile.created_at.desc())
    )

    if domain:
        query = query.join(MentorProfile.domains).where(MentorDomain.slug == domain.strip())
    if company:
        query = query.where(MentorProfile.company.ilike(f"%{company.strip()}%"))
    if mode:
        query = query.where(MentorProfile.contact_mode == mode.strip())
    if q:
        search = f"%{q.strip()}%"
        query = query.join(MentorProfile.user).where(
            or_(
                User.full_name.ilike(search),
                MentorProfile.headline.ilike(search),
                MentorProfile.bio.ilike(search),
                MentorProfile.missions_history.ilike(search),
            )
        )

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    mentors = result.scalars().all()
    return [_serialize_public_mentor(m) for m in mentors]


# ── Mentor Profile Detail ─────────────────────────────────────────────────────

@router.get("/mentors/{slug}", response_model=MentorProfileOut)
async def get_public_mentor_profile(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve an active mentor's public profile and stats."""
    result = await db.execute(
        select(MentorProfile)
        .where(
            MentorProfile.slug == slug.strip().lower(),
            MentorProfile.is_active.is_(True),
            MentorProfile.status == "approved",
        )
        .options(selectinload(MentorProfile.domains), selectinload(MentorProfile.user))
    )
    mentor = result.scalars().first()
    if not mentor:
        raise HTTPException(status_code=404, detail="Mentor not found or profile not active")
    return _serialize_public_mentor(mentor)


# ── Available Slots for a Given Date ──────────────────────────────────────────

@router.get("/mentors/{slug}/slots", response_model=list[AvailableSlotOut])
async def get_mentor_available_slots(
    slug: str,
    target_date: date = Query(..., alias="date", description="Target date YYYY-MM-DD"),
    tz: Optional[str] = Query(None, description="Client timezone, e.g. Africa/Cairo"),
    db: AsyncSession = Depends(get_db),
):
    """Compute open 30-min slots for a specific date, factoring in mentor rules in their timezone, client timezone, and existing bookings."""
    mentor = (
        await db.execute(
            select(MentorProfile).where(
                MentorProfile.slug == slug.strip().lower(),
                MentorProfile.is_active.is_(True),
                MentorProfile.status == "approved",
            )
        )
    ).scalars().first()

    if not mentor:
        raise HTTPException(status_code=404, detail="Mentor not found")
    if mentor.contact_mode != "calendar":
        return []

    try:
        client_tz = zoneinfo.ZoneInfo(tz) if tz else timezone.utc
    except Exception:
        client_tz = timezone.utc

    # Target window in client timezone: target_date 00:00:00 to target_date+1 00:00:00
    target_start_utc = datetime.combine(target_date, time.min, tzinfo=client_tz).astimezone(timezone.utc)
    target_end_utc = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=client_tz).astimezone(timezone.utc)

    # Fetch all active recurring or specific-date rules for this mentor
    availabilities = (
        await db.execute(
            select(MentorAvailability).where(
                MentorAvailability.mentor_id == mentor.id,
                MentorAvailability.is_active.is_(True),
            )
        )
    ).scalars().all()

    if not availabilities:
        return []

    slot_duration = timedelta(minutes=mentor.session_duration_minutes or 30)
    candidate_slots: list[tuple[datetime, datetime]] = []

    # Check candidate dates around target_date to handle cross-midnight timezone offsets
    check_dates = [target_date - timedelta(days=1), target_date, target_date + timedelta(days=1)]

    for rule in availabilities:
        try:
            rule_tz = zoneinfo.ZoneInfo(rule.timezone) if rule.timezone else timezone.utc
        except Exception:
            rule_tz = timezone.utc

        for cd in check_dates:
            applies = False
            if rule.specific_date is not None:
                applies = (rule.specific_date == cd)
            elif rule.day_of_week is not None:
                applies = (rule.day_of_week == cd.weekday())

            if not applies:
                continue

            rule_start_local = datetime.combine(cd, rule.start_time, tzinfo=rule_tz)
            rule_end_local = datetime.combine(cd, rule.end_time, tzinfo=rule_tz)
            if rule_end_local <= rule_start_local:
                rule_end_local += timedelta(days=1)

            rule_start_utc = rule_start_local.astimezone(timezone.utc)
            rule_end_utc = rule_end_local.astimezone(timezone.utc)

            curr = rule_start_utc
            while curr + slot_duration <= rule_end_utc:
                slot_start = curr
                slot_end = curr + slot_duration
                # Check if this slot starts on target_date in the client's timezone
                slot_client_dt = slot_start.astimezone(client_tz)
                if slot_client_dt.date() == target_date:
                    candidate_slots.append((slot_start, slot_end))
                curr += slot_duration

    # Deduplicate and sort candidate slots chronologically
    candidate_slots = sorted(list(set(candidate_slots)), key=lambda s: s[0])

    # Fetch existing non-cancelled bookings in the window
    booked_results = (
        await db.execute(
            select(MentorBooking).where(
                MentorBooking.mentor_id == mentor.id,
                MentorBooking.status != "cancelled",
                MentorBooking.scheduled_start >= target_start_utc - timedelta(hours=1),
                MentorBooking.scheduled_start <= target_end_utc + timedelta(hours=1),
            )
        )
    ).scalars().all()

    booked_starts = set()
    for b in booked_results:
        if b.scheduled_start:
            bs = b.scheduled_start
            if bs.tzinfo is None:
                bs = bs.replace(tzinfo=timezone.utc)
            booked_starts.add(bs.astimezone(timezone.utc))

    now_utc = datetime.now(timezone.utc)
    available_slots = []
    for s_start, s_end in candidate_slots:
        # Ignore slots in the past
        if s_start < now_utc:
            continue
        # Ignore already booked slots
        if s_start in booked_starts:
            continue
        available_slots.append(AvailableSlotOut(start=s_start, end=s_end, available=True))

    return available_slots


# ── Booking / Inquiry Submission ──────────────────────────────────────────────

@router.post("/mentors/{slug}/book", response_model=MentorBookingOut, status_code=status.HTTP_201_CREATED)
async def book_mentor_session(
    slug: str,
    body: MentorBookIn,
    db: AsyncSession = Depends(get_db),
):
    """Book a 1:1 session (Mode B) or send a direct inquiry (Mode A)."""
    mentor = (
        await db.execute(
            select(MentorProfile)
            .where(
                MentorProfile.slug == slug.strip().lower(),
                MentorProfile.is_active.is_(True),
                MentorProfile.status == "approved",
            )
            .options(selectinload(MentorProfile.user))
        )
    ).scalars().first()

    if not mentor:
        raise HTTPException(status_code=404, detail="Mentor not found or profile not active")

    gateway_token = secrets.token_urlsafe(32)
    cancel_token = secrets.token_urlsafe(32)

    scheduled_end = None
    if body.booking_type == "session":
        if not body.scheduled_start:
            raise HTTPException(
                status_code=400,
                detail="scheduled_start is required for calendar session bookings",
            )
        scheduled_end = body.scheduled_start + timedelta(minutes=mentor.session_duration_minutes or 30)

        # Conflict check in database
        conflict = await db.execute(
            select(MentorBooking.id).where(
                MentorBooking.mentor_id == mentor.id,
                MentorBooking.scheduled_start == body.scheduled_start,
                MentorBooking.status != "cancelled",
            )
        )
        if conflict.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This slot was just booked by someone else. Please pick another time.",
            )

    booking = MentorBooking(
        mentor_id=mentor.id,
        mentee_name=body.mentee_name.strip(),
        mentee_email=body.mentee_email.strip().lower(),
        topics=body.topics.strip(),
        booking_type=body.booking_type,
        scheduled_start=body.scheduled_start,
        scheduled_end=scheduled_end,
        google_meet_url=mentor.google_meet_url,  # Option A: Mentor's Meet link
        gateway_token=gateway_token,
        cancel_token=cancel_token,
        status="confirmed",
    )

    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    return MentorBookingOut(
        id=booking.id,
        mentor_id=booking.mentor_id,
        mentee_name=booking.mentee_name,
        mentee_email=booking.mentee_email,
        topics=booking.topics,
        booking_type=booking.booking_type,
        scheduled_start=booking.scheduled_start,
        scheduled_end=booking.scheduled_end,
        status=booking.status,
        created_at=booking.created_at,
        mentor_name=mentor.user.full_name if mentor.user else None,
    )


# ── Self-Service Cancellation ─────────────────────────────────────────────────

@router.post("/bookings/{cancel_token}/cancel")
async def cancel_booking(
    cancel_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Self-service cancellation for either mentor or mentee via their token."""
    result = await db.execute(
        select(MentorBooking).where(MentorBooking.cancel_token == cancel_token.strip())
    )
    booking = result.scalars().first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or invalid cancel link")

    if booking.status == "cancelled":
        return {"status": "cancelled", "message": "Booking was already cancelled"}

    booking.status = "cancelled"
    booking.cancelled_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "cancelled", "message": "Booking successfully cancelled"}


# ── Attendance Gateway & Meeting Launch ────────────────────────────────────────

@router.get("/meet/{gateway_token}")
async def attendance_gateway(
    gateway_token: str,
    launch: int = Query(default=0, description="1 if user clicked launch button"),
    db: AsyncSession = Depends(get_db),
):
    """Attendance gateway.
    - If launch == 0: Renders a minimal flat 1-button launch page (neutralizes email bots).
    - If launch == 1: Logs attendance timestamp, increments mentor impact hours, and 302-redirects to Google Meet.
    """
    result = await db.execute(
        select(MentorBooking)
        .where(MentorBooking.gateway_token == gateway_token.strip())
        .options(selectinload(MentorBooking.mentor).selectinload(MentorProfile.user))
    )
    booking = result.scalars().first()
    if not booking:
        raise HTTPException(status_code=404, detail="Session link not found or expired")

    mentor = booking.mentor
    target_meet_url = booking.google_meet_url or (mentor.google_meet_url if mentor else None) or "https://meet.google.com"

    # Minimal flat splash screen (zero gradients, minimal typography)
    if launch != 1:
        mentor_name = mentor.user.full_name if (mentor and mentor.user) else "Space Mentor"
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SpacePoint Mentorship — Launch Meeting</title>
  <style>
    body {{
      margin: 0;
      background: #05030A;
      color: #FFFFFF;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
    }}
    .box {{
      background: #110B18;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 8px;
      padding: 32px;
      max-width: 400px;
      width: 90%;
      text-align: center;
    }}
    h1 {{
      font-size: 18px;
      font-weight: 600;
      margin: 0 0 8px 0;
      letter-spacing: -0.02em;
    }}
    p {{
      color: #9CA3AF;
      font-size: 14px;
      margin: 0 0 24px 0;
    }}
    .btn {{
      display: inline-block;
      background: #A77DFF;
      color: #05030A;
      text-decoration: none;
      font-size: 14px;
      font-weight: 600;
      padding: 12px 24px;
      border-radius: 6px;
      transition: background 0.15s ease;
    }}
    .btn:hover {{
      background: #C0A0FF;
    }}
  </style>
</head>
<body>
  <div class="box">
    <h1>SpacePoint Mentorship</h1>
    <p>Session with {mentor_name}</p>
    <a class="btn" href="/meet/{gateway_token}?launch=1">Join Google Meet</a>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html_content, status_code=200)

    # User clicked the launch button: check attendance window and record telemetry
    now = datetime.now(timezone.utc)
    if booking.scheduled_start and booking.scheduled_end:
        valid_start = booking.scheduled_start - timedelta(hours=1)
        valid_end = booking.scheduled_end + timedelta(minutes=30)

        # Only mark completed if launched inside the valid window
        if valid_start <= now <= valid_end:
            if not booking.mentor_joined_at:
                booking.mentor_joined_at = now
            if booking.status == "confirmed":
                booking.status = "completed"
                duration = mentor.session_duration_minutes if mentor else 30
                if mentor:
                    mentor.total_completed_minutes += duration
                    mentor.completed_sessions_count += 1
                await db.commit()

    # Instant redirect to Google Meet
    return RedirectResponse(url=target_meet_url, status_code=status.HTTP_302_FOUND)
