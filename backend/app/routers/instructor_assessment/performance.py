"""Instructor Performance Profile — read-only aggregation, plus
certification-tag CRUD (the one writable piece of the profile besides
ratings themselves). `/instructor-assessment/performance/*`.

Gated to `require_operations` for now — this is the admin drill-down view
(`pages/instructors/admin/Instructors.tsx` -> "view full performance
history"); an instructor's own lightweight self-view continues to come from
the existing `getUserStatsApi`/`InstructorCard` surface untouched by this
domain.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.instructor_assessment.rating import InstructorCertificationTag
from app.models.user import User
from app.schemas.instructor_assessment import (
    CertificationTagIn,
    CertificationTagOut,
    InstructorPerformanceOut,
    QuizHistoryEntryOut,
    RatingHistoryEntryOut,
)
from app.services.instructor_assessment.performance import get_performance

router = APIRouter(
    prefix="/instructor-assessment/performance", tags=["instructor-assessment-performance"],
    dependencies=[Depends(require_operations)],
)


@router.get("/{user_id}", response_model=InstructorPerformanceOut)
async def get_instructor_performance(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    if await db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    data = await get_performance(db, user_id)
    return InstructorPerformanceOut(
        user_id=data["user_id"],
        total_sessions_delivered=data["total_sessions_delivered"],
        total_hours_delivered=data["total_hours_delivered"],
        programs_participated_in=data["programs_participated_in"],
        average_rating=data["average_rating"],
        recent_rating_trend=data["recent_rating_trend"],
        reliability_ratio=data["reliability_ratio"],
        certifications=[
            CertificationTagOut(id=c.id, label=c.label, created_at=c.created_at) for c in data["certifications"]
        ],
        quiz_history=[QuizHistoryEntryOut(**q) for q in data["quiz_history"]],
        rating_history=[RatingHistoryEntryOut(**r) for r in data["rating_history"]],
    )


@router.post("/{user_id}/certifications", response_model=CertificationTagOut, status_code=status.HTTP_201_CREATED)
async def add_certification(
    user_id: uuid.UUID, body: CertificationTagIn, db: AsyncSession = Depends(get_db),
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
