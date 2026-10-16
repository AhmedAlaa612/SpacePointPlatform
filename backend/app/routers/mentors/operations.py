import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.mentors import MentorDomain, MentorProfile
from app.models.user import User
from app.schemas.mentors import (
    MentorCreateIn,
    MentorDomainCreateIn,
    MentorDomainOut,
    MentorDomainUpdateIn,
    MentorProfileOut,
    MentorReviewIn,
    MentorStatusUpdateIn,
)
from app.schemas.user import UserCreate
from app.services import user as user_service
from app.services.spine.identity import normalize_user_email, user_email_matches

router = APIRouter(prefix="/operations", tags=["Operations - Mentors"])


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


# ── Domain Tags Management ────────────────────────────────────────────────────

@router.get("/mentor-domains", response_model=list[MentorDomainOut])
async def list_mentor_domains(
    is_active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_operations),
):
    """List all dynamic space domain tags."""
    query = select(MentorDomain).order_by(
        MentorDomain.display_order.asc(), MentorDomain.name.asc()
    )
    if is_active is not None:
        query = query.where(MentorDomain.is_active == is_active)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/mentor-domains", response_model=MentorDomainOut, status_code=status.HTTP_201_CREATED)
async def create_mentor_domain(
    body: MentorDomainCreateIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_operations),
):
    """Create a new space domain tag."""
    slug = _slugify(body.slug or body.name)
    existing = await db.execute(select(MentorDomain).where(MentorDomain.slug == slug))
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Domain tag with slug '{slug}' already exists",
        )

    domain = MentorDomain(
        name=body.name.strip(),
        slug=slug,
        category=body.category.strip() if body.category else None,
        display_order=body.display_order,
        is_active=body.is_active,
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return domain


@router.put("/mentor-domains/{domain_id}", response_model=MentorDomainOut)
async def update_mentor_domain(
    domain_id: UUID,
    body: MentorDomainUpdateIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_operations),
):
    """Update a space domain tag."""
    domain = await db.get(MentorDomain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain tag not found")

    if body.name is not None:
        domain.name = body.name.strip()
    if body.slug is not None:
        new_slug = _slugify(body.slug)
        existing = await db.execute(
            select(MentorDomain).where(
                MentorDomain.slug == new_slug, MentorDomain.id != domain_id
            )
        )
        if existing.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Domain tag with slug '{new_slug}' already exists",
            )
        domain.slug = new_slug
    if body.category is not None:
        domain.category = body.category.strip() if body.category else None
    if body.display_order is not None:
        domain.display_order = body.display_order
    if body.is_active is not None:
        domain.is_active = body.is_active

    await db.commit()
    await db.refresh(domain)
    return domain


@router.delete("/mentor-domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mentor_domain(
    domain_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_operations),
):
    """Delete a space domain tag."""
    domain = await db.get(MentorDomain, domain_id)
    if not domain:
        raise HTTPException(status_code=404, detail="Domain tag not found")

    await db.delete(domain)
    await db.commit()
    return None


# ── Mentor Applications & Roster ──────────────────────────────────────────────

def _serialize_mentor_profile(mentor: MentorProfile) -> MentorProfileOut:
    return MentorProfileOut(
        id=mentor.id,
        user_id=mentor.user_id,
        slug=mentor.slug,
        headline=mentor.headline,
        company=mentor.company,
        bio=mentor.bio,
        missions_history=mentor.missions_history,
        contact_mode=mentor.contact_mode,
        google_meet_url=mentor.google_meet_url,
        status=mentor.status,
        is_active=mentor.is_active,
        is_published=mentor.is_published if mentor.is_published is not None else True,
        invite_code=mentor.invite_code,
        photo_url=mentor.photo_url or (mentor.user.photo_url if mentor.user else None),
        contact_email=mentor.contact_email,
        show_contact_button=mentor.show_contact_button if mentor.show_contact_button is not None else True,
        linkedin_url=mentor.linkedin_url,
        session_duration_minutes=mentor.session_duration_minutes,
        total_completed_minutes=mentor.total_completed_minutes,
        completed_sessions_count=mentor.completed_sessions_count,
        domains=mentor.domains,
        created_at=mentor.created_at,
        user_full_name=mentor.user.full_name if mentor.user else None,
        user_email=mentor.user.email if mentor.user else None,
        user_photo_url=mentor.user.photo_url if mentor.user else None,
        user_country=mentor.user.country if mentor.user else None,
    )


@router.get("/mentors/applications", response_model=list[MentorProfileOut])
async def list_mentor_applications(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_operations),
):
    """List pending mentor applications awaiting Ops review."""
    result = await db.execute(
        select(MentorProfile)
        .where(MentorProfile.status == "applied")
        .options(selectinload(MentorProfile.domains), selectinload(MentorProfile.user))
        .order_by(MentorProfile.created_at.asc())
    )
    mentors = result.scalars().all()
    return [_serialize_mentor_profile(m) for m in mentors]


@router.get("/mentors", response_model=list[MentorProfileOut])
async def list_all_mentors(
    status_filter: str | None = Query(default=None, alias="status"),
    is_active: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_operations),
):
    """List all mentors in the system with optional status filters."""
    query = (
        select(MentorProfile)
        .options(selectinload(MentorProfile.domains), selectinload(MentorProfile.user))
        .order_by(MentorProfile.created_at.desc())
    )
    if status_filter:
        query = query.where(MentorProfile.status == status_filter)
    if is_active is not None:
        query = query.where(MentorProfile.is_active == is_active)

    result = await db.execute(query)
    mentors = result.scalars().all()
    return [_serialize_mentor_profile(m) for m in mentors]


@router.post("/mentors/{mentor_id}/review", response_model=MentorProfileOut)
async def review_mentor_application(
    mentor_id: UUID,
    body: MentorReviewIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_operations),
):
    """Approve or reject a mentor application.
    On approval: activates profile and assigns the 'mentor' role to the user.
    """
    result = await db.execute(
        select(MentorProfile)
        .where(MentorProfile.id == mentor_id)
        .options(selectinload(MentorProfile.domains), selectinload(MentorProfile.user))
    )
    mentor = result.scalars().first()
    if not mentor:
        raise HTTPException(status_code=404, detail="Mentor profile not found")

    if body.decision == "approved":
        mentor.status = "approved"
        mentor.is_active = True
        # Grant mentor role to user if not already granted
        if mentor.user:
            current_roles = list(mentor.user.roles or [])
            if UserRole.mentor not in current_roles:
                mentor.user.roles = current_roles + [UserRole.mentor]
    elif body.decision == "rejected":
        mentor.status = "rejected"
        mentor.is_active = False

    await db.commit()
    await db.refresh(mentor)
    return _serialize_mentor_profile(mentor)


@router.put("/mentors/{mentor_id}/status", response_model=MentorProfileOut)
async def update_mentor_status(
    mentor_id: UUID,
    body: MentorStatusUpdateIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_operations),
):
    """Toggle mentor active visibility or status (e.g. suspended)."""
    result = await db.execute(
        select(MentorProfile)
        .where(MentorProfile.id == mentor_id)
        .options(selectinload(MentorProfile.domains), selectinload(MentorProfile.user))
    )
    mentor = result.scalars().first()
    if not mentor:
        raise HTTPException(status_code=404, detail="Mentor profile not found")

    mentor.is_active = body.is_active
    if body.status:
        mentor.status = body.status

    await db.commit()
    await db.refresh(mentor)
    return _serialize_mentor_profile(mentor)


@router.post("/mentors", response_model=MentorProfileOut, status_code=status.HTTP_201_CREATED)
async def create_mentor_directly(
    body: MentorCreateIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_operations),
):
    """Directly create an approved mentor profile (and their user account if it doesn't exist).
    Used by Operations/Admin to onboard mentors without requiring a manual application review.
    """
    normalized_email = normalize_user_email(body.email)
    existing_user_result = await db.execute(
        select(User).where(user_email_matches(normalized_email))
    )
    user = existing_user_result.scalars().first()

    if user:
        existing_profile_result = await db.execute(
            select(MentorProfile).where(MentorProfile.user_id == user.id)
        )
        if existing_profile_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A mentor profile already exists for {body.email}",
            )
        current_roles = list(user.roles or [])
        if UserRole.mentor not in current_roles:
            user.roles = current_roles + [UserRole.mentor]
        if body.phone and not user.phone:
            user.phone = body.phone
        if body.country and not user.country:
            user.country = body.country
        target_user = user
    else:
        temp_pwd = body.password or "SpacePoint2026!"
        target_user = await user_service.create_user(
            db,
            UserCreate(
                full_name=body.full_name.strip(),
                email=normalized_email,
                password=temp_pwd,
                roles=[UserRole.mentor],
                phone=body.phone,
            ),
        )
        if body.country:
            target_user.country = body.country
        if not body.password:
            target_user.must_change_password = True

    slug = await _generate_unique_mentor_slug(db, body.full_name)
    mentor = MentorProfile(
        user_id=target_user.id,
        slug=slug,
        headline=body.headline.strip(),
        company=body.company.strip() if body.company else None,
        bio=body.bio.strip() if body.bio else None,
        missions_history=body.missions_history.strip() if body.missions_history else None,
        what_i_can_help_with=body.what_i_can_help_with.strip() if body.what_i_can_help_with else None,
        contact_mode=body.contact_mode,
        google_meet_url=body.google_meet_url.strip() if body.google_meet_url else None,
        contact_email=str(body.contact_email).strip().lower() if body.contact_email else None,
        show_contact_button=body.show_contact_button,
        linkedin_url=body.linkedin_url.strip() if body.linkedin_url else None,
        session_duration_minutes=body.session_duration_minutes or 30,
        status="approved",
        is_active=body.is_active,
        is_published=body.is_published,
    )

    if body.domain_ids:
        d_res = await db.execute(
            select(MentorDomain).where(MentorDomain.id.in_(body.domain_ids))
        )
        mentor.domains = list(d_res.scalars().all())

    db.add(mentor)
    await db.commit()

    full_mentor = (
        await db.execute(
            select(MentorProfile)
            .where(MentorProfile.id == mentor.id)
            .options(selectinload(MentorProfile.domains), selectinload(MentorProfile.user))
        )
    ).scalars().first()

    return _serialize_mentor_profile(full_mentor or mentor)

