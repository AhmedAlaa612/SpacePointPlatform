"""Instructor Performance Profile & Operations Directory (`/instructor-assessment/performance/*`).

Gated to `require_operations` — backs both the Operations Instructors Roster
(`/operations/instructors`) and the Comprehensive Instructor Profile
(`/operations/instructors/$userId`), plus Ops-controlled Certified toggle and
CR80 ID card preview without leaking admin-only documents/bank details.
"""

import base64
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.instructor_assessment.rating import InstructorCertificationTag
from app.models.user import User
from app.schemas.instructor_assessment import (
    CertificationTagIn,
    CertificationTagOut,
    CertifiedToggleIn,
    CertifiedToggleOut,
    InstructorCohortHistoryEntryOut,
    InstructorPerformanceOut,
    OpsInstructorRosterItemOut,
    QuizHistoryEntryOut,
    RatingHistoryEntryOut,
)
from app.schemas.instructors.instructor import IdCardOut
from app.services.documents.id_card import ensure_card_id, render_card_back_png, render_card_png
from app.services.instructor_assessment.performance import get_performance, list_ops_instructors

router = APIRouter(
    prefix="/instructor-assessment/performance",
    tags=["instructor-assessment-performance"],
    dependencies=[Depends(require_operations)],
)


@router.get("", response_model=list[OpsInstructorRosterItemOut])
async def list_instructors_for_ops(db: AsyncSession = Depends(get_db)):
    rows = await list_ops_instructors(db)
    return [
        OpsInstructorRosterItemOut(
            **{
                **row,
                "certifications": [
                    CertificationTagOut(id=c.id, label=c.label, created_at=c.created_at)
                    for c in row["certifications"]
                ],
            }
        )
        for row in rows
    ]


@router.get("/{user_id}", response_model=InstructorPerformanceOut)
async def get_instructor_performance(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    if await db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    data = await get_performance(db, user_id)
    return InstructorPerformanceOut(
        user_id=data["user_id"],
        full_name=data["full_name"],
        email=data["email"],
        phone=data["phone"],
        photo_url=data["photo_url"],
        linkedin_url=data["linkedin_url"],
        card_id=data["card_id"],
        city_id=data["city_id"],
        city_name=data["city_name"],
        deliver_city_ids=data["deliver_city_ids"],
        deliver_city_names=data["deliver_city_names"],
        has_own_transportation=data["has_own_transportation"],
        nationality=data["nationality"],
        graduated_university=data["graduated_university"],
        fluent_languages=data["fluent_languages"],
        docs_complete=data["docs_complete"],
        is_certified=data["is_certified"],
        certified_tag_id=data["certified_tag_id"],
        total_sessions_assigned=data["total_sessions_assigned"],
        total_sessions_delivered=data["total_sessions_delivered"],
        total_hours_delivered=data["total_hours_delivered"],
        programs_participated_in=data["programs_participated_in"],
        cohorts_participated_in=data["cohorts_participated_in"],
        unrated_cohorts_count=data["unrated_cohorts_count"],
        average_rating=data["average_rating"],
        recent_rating_trend=data["recent_rating_trend"],
        reliability_ratio=data["reliability_ratio"],
        dimension_averages=data["dimension_averages"],
        certifications=[
            CertificationTagOut(id=c.id, label=c.label, created_at=c.created_at)
            for c in data["certifications"]
        ],
        quiz_history=[QuizHistoryEntryOut(**q) for q in data["quiz_history"]],
        rating_history=[RatingHistoryEntryOut(**r) for r in data["rating_history"]],
        cohort_history=[InstructorCohortHistoryEntryOut(**c) for c in data["cohort_history"]],
    )


@router.put("/{user_id}/certified", response_model=CertifiedToggleOut)
async def set_instructor_certified(
    user_id: uuid.UUID,
    body: CertifiedToggleIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_operations),
):
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = (await db.execute(
        select(InstructorCertificationTag).where(
            InstructorCertificationTag.user_id == user_id,
            func.lower(func.trim(InstructorCertificationTag.label)) == "certified",
        )
    )).scalars().all()

    if body.certified:
        if existing:
            return CertifiedToggleOut(is_certified=True, certified_tag_id=existing[0].id)
        tag = InstructorCertificationTag(
            id=uuid.uuid4(),
            user_id=user_id,
            label="Certified",
            created_by=current.id,
        )
        db.add(tag)
        await db.commit()
        await db.refresh(tag)
        return CertifiedToggleOut(is_certified=True, certified_tag_id=tag.id)

    for tag in existing:
        await db.delete(tag)
    await db.commit()
    return CertifiedToggleOut(is_certified=False, certified_tag_id=None)


@router.get("/{user_id}/id-card", response_model=IdCardOut)
async def get_instructor_id_card(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """CR80 Front & Back ID card preview for Operations without admin-only dossier/ZIP endpoints."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    if UserRole.instructor.value not in target.role_values:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="User is not an instructor")

    card_row = await ensure_card_id(db, target.id, UserRole.instructor)
    await db.commit()

    from app.routers.instructors.instructor import _photo_bytes_for
    from app.services import storage

    photo_bytes = await _photo_bytes_for(target)
    await db.commit()

    photo_url = (
        await storage.resolve_url("profile_pictures", target.photo_path, target.photo_url)
        if (target.photo_path or target.photo_url)
        else None
    )
    front_png = render_card_png(UserRole.instructor, photo_bytes, target.linkedin_url, target.full_name)
    issue_date = card_row.generated_at or datetime.now(timezone.utc)
    back_png = render_card_back_png(UserRole.instructor, card_row.card_id, issue_date)

    return IdCardOut(
        card_id=card_row.card_id,
        front_b64=base64.b64encode(front_png).decode(),
        back_b64=base64.b64encode(back_png).decode(),
        generated_at=card_row.generated_at,
        has_photo=bool(photo_url),
        has_linkedin=bool(target.linkedin_url),
        photo_url=photo_url,
        linkedin_url=target.linkedin_url,
    )


@router.post("/{user_id}/certifications", response_model=CertificationTagOut, status_code=status.HTTP_201_CREATED)
async def add_certification(
    user_id: uuid.UUID,
    body: CertificationTagIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_operations),
):
    if await db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    tag = InstructorCertificationTag(id=uuid.uuid4(), user_id=user_id, label=body.label, created_by=current.id)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return CertificationTagOut(id=tag.id, label=tag.label, created_at=tag.created_at)


@router.delete("/certifications/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certification(tag_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    tag = await db.get(InstructorCertificationTag, tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Certification tag not found")
    await db.delete(tag)
    await db.commit()
