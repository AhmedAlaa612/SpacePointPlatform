import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_admin
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.enums import ApplicationStatus, UserRole
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.application_review import ApplicationReview
from app.models.instructors.instructor_profile import InstructorProfile
from app.models.instructors.presentation_submission import PresentationSubmission
from app.models.instructors.video_submission import VideoSubmission
from app.models.user import User
from app.schemas.instructors.admin import AdminReviewUpdate
from app.services import storage
from app.services.documents.contract import generate_contract_pdf
from app.services.email import send_approval_credentials_email, send_phase1_approval_email
from app.services.notification import create_notification as notify
from app.services.points import award_points

router = APIRouter(prefix="/admin", tags=["instructors-admin"])


@router.get("/applicants")
async def list_applicants(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = (await db.execute(
        select(User, ApplicationReview, ApplicantProfile)
        .join(ApplicationReview, ApplicationReview.user_id == User.id)
        .outerjoin(ApplicantProfile, ApplicantProfile.user_id == User.id)
        .where(User.roles.any("applicant"))
        .order_by(User.created_at.desc())
    )).all()
    return [
        {
            "id": str(u.id), "full_name": u.full_name, "email": u.email,
            "status": review.status, "feedback": review.feedback,
            "university": profile.university if profile else None,
            "referred_by_ambassador_id": str(profile.referred_by_ambassador_id) if profile and profile.referred_by_ambassador_id else None,
            "created_at": u.created_at,
        }
        for u, review, profile in rows
    ]


@router.get("/applicants/{user_id}")
async def applicant_detail(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    user = (await db.execute(select(User).where(User.id == user_id, User.roles.any("applicant")))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Applicant not found")
    profile = (await db.execute(select(ApplicantProfile).where(ApplicantProfile.user_id == user_id))).scalars().first()
    review = (await db.execute(select(ApplicationReview).where(ApplicationReview.user_id == user_id))).scalars().first()
    videos = (await db.execute(
        select(VideoSubmission).where(VideoSubmission.user_id == user_id).order_by(VideoSubmission.video_no)
    )).scalars().all()
    presentation = (await db.execute(
        select(PresentationSubmission).where(PresentationSubmission.user_id == user_id)
    )).scalars().first()
    return {
        "id": str(user.id), "full_name": user.full_name, "email": user.email,
        "profile": profile, "review": {"status": review.status, "feedback": review.feedback} if review else None,
        "videos": videos, "presentation_link": presentation.video_link if presentation else None,
    }


@router.put("/applicants/{user_id}/review")
async def review_applicant(
    user_id: uuid.UUID,
    body: AdminReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """The applicant pipeline state machine (instructors/HANDOFF.md §4).
    Admin may only move an application out of `under_review`."""
    user = (await db.execute(select(User).where(User.id == user_id, User.roles.any("applicant")))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Applicant not found")

    review = (await db.execute(select(ApplicationReview).where(ApplicationReview.user_id == user_id))).scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="Application review not found")
    if review.status != ApplicationStatus.under_review:
        raise HTTPException(status_code=400, detail="Can only review an application that is under review")

    review.status = body.status
    review.admin_id = current_user.id
    review.feedback = body.feedback
    review.reviewed_at = datetime.now(timezone.utc)

    email_sent = None

    if body.status == ApplicationStatus.phase_1_approved:
        email_sent = await send_phase1_approval_email(user.email, user.full_name)

    elif body.status == ApplicationStatus.approved:
        # Promote to instructor (replace 'applicant' — cleaner than keeping both, per PLAN §9.2)
        user.roles = [UserRole.instructor]
        temp_password = secrets.token_urlsafe(12)
        user.password_hash = get_password_hash(temp_password)
        user.must_change_password = True

        profile = (await db.execute(select(ApplicantProfile).where(ApplicantProfile.user_id == user_id))).scalars().first()
        living_area = (profile.city_of_residence if profile and profile.city_of_residence else None) or \
            (profile.country if profile else "United Arab Emirates")

        contract_bytes = generate_contract_pdf(user.full_name, living_area)
        contract_url = await storage.upload_file(
            "contracts", f"{user_id}/agreement.pdf", contract_bytes, "application/pdf"
        )

        inst_profile = (await db.execute(
            select(InstructorProfile).where(InstructorProfile.user_id == user_id)
        )).scalars().first()
        if inst_profile:
            inst_profile.contract_url = contract_url
        else:
            db.add(InstructorProfile(user_id=user_id, contract_url=contract_url))

        email_sent = await send_approval_credentials_email(
            user.email, user.full_name, temp_password, contract_pdf=contract_bytes
        )

        if profile and profile.referred_by_ambassador_id:
            await award_points(db, profile.referred_by_ambassador_id, 1000, f"Recruited instructor: {user.full_name}")
            await notify(db, profile.referred_by_ambassador_id, "Instructor Approved!",
                         f"{user.full_name}, whom you referred, was approved as an instructor — you earned points.")

    # rejected: no email, by design (matches source — applicant must check the portal)

    await db.commit()
    return {"status": review.status, "email_sent": email_sent}
