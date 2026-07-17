from datetime import datetime, timezone

import uuid as uuid_lib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from jose import JWTError, jwt
from sqlalchemy import func, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    Token,
    UpdateMeRequest,
    UserOut,
)
from app.models.enums import UserRole
from app.models.instructors.invitation_code import InvitationCode
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.video_submission import VideoSubmission
from app.models.instructors.application_review import ApplicationReview
from app.schemas.user import InstructorApply
from app.services.notification import create_notification as notify

router = APIRouter(prefix="/auth", tags=["auth"])


async def _user_out(user: User, profile: ApplicantProfile | None = None) -> dict:
    from app.services import storage
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "roles": user.role_values,
        "status": user.status,
        "must_change_password": user.must_change_password,
        "phone": user.phone,
        "country": user.country,
        "invite_code": user.invite_code,
        "photo_url": await storage.resolve_url("profile_pictures", user.photo_path, user.photo_url),
        "linkedin_url": user.linkedin_url,
        "created_at": user.created_at,
        # Applicant-profile fields — surfaced on Profile & Settings for
        # instructors/facilitators/applicants. None when no profile exists.
        "city_of_residence": profile.city_of_residence if profile else None,
        "deliver_cities": profile.deliver_cities if profile else None,
        "has_own_transportation": profile.has_own_transportation if profile else None,
    }


async def _load_applicant_profile(db: AsyncSession, user_id) -> ApplicantProfile | None:
    return (
        await db.execute(select(ApplicantProfile).where(ApplicantProfile.user_id == user_id))
    ).scalars().first()


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == data.email))).scalars().first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    roles = user.role_values
    if "admin" not in roles and user.status != "active":
        raise HTTPException(status_code=403, detail="Account is not active")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "access_token": create_access_token(user.id, roles),
        "refresh_token": create_refresh_token(user.id, roles),
        "token_type": "bearer",
        "user": await _user_out(user),
    }


@router.post("/refresh", response_model=Token)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(data.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != "refresh" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Re-validate against the DB so deactivated users / role changes take effect
    # within the refresh window.
    user = (await db.execute(select(User).where(User.id == payload["sub"]))).scalars().first()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    roles = user.role_values
    if "admin" not in roles and user.status != "active":
        raise HTTPException(status_code=401, detail="Account is no longer active")

    return {
        "access_token": create_access_token(user.id, roles),
        "refresh_token": create_refresh_token(user.id, roles),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserOut)
async def me(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _load_applicant_profile(db, current_user.id)
    return await _user_out(current_user, profile)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    try:
        uid = uuid_lib.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    user = (await db.execute(select(User).where(User.id == uid))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await _user_out(user)


@router.get("/users/{user_id}/stats")
async def get_user_stats(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Return role-specific stats for any user. Callable by any authenticated user."""
    try:
        uid = uuid_lib.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    user = (await db.execute(select(User).where(User.id == uid))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    roles = user.role_values
    result: dict = {}

    if "ambassador" in roles:
        from app.services.ambassadors import stats as stats_svc, achievements as ach_svc
        from app.services.points import lifetime_points
        from app.services.ambassadors.titles import resolve_title_progress

        overview = await stats_svc.ambassador_overview(db, uid)
        points = await lifetime_points(db, uid)
        season_pts = await lifetime_points(db, uid, since=stats_svc.season_start())
        title_info = await resolve_title_progress(db, points)
        badges = await ach_svc.list_for(db, uid)

        result["ambassador"] = {
            **overview,
            "points_balance": points,
            "season_points": season_pts,
            "achievements": badges,
            **title_info,
        }

    if "teacher" in roles:
        from app.models.ambassadors.teacher_session import TeacherSession
        from app.services.points import lifetime_points as lp
        from app.services.ambassadors.titles import resolve_title_progress as rtp
        from app.services.ambassadors import achievements as ach_svc2

        now = datetime.now(timezone.utc)

        sessions_done = await db.scalar(
            select(func.count()).select_from(TeacherSession)
            .where(and_(TeacherSession.teacher_id == uid, TeacherSession.status == "done")))
        students_reached = await db.scalar(
            select(func.coalesce(func.sum(TeacherSession.attended_students), 0))
            .where(and_(TeacherSession.teacher_id == uid, TeacherSession.status == "done")))
        upcoming = await db.scalar(
            select(func.count()).select_from(TeacherSession)
            .where(and_(
                TeacherSession.teacher_id == uid,
                TeacherSession.status == "approved",
                TeacherSession.date >= now,
            )))

        points = await lp(db, uid)
        title_info = await rtp(db, points, audience="teacher")
        badges = await ach_svc2.list_for(db, uid, audience="teacher")

        result["teacher"] = {
            "stats": {
                "sessions_done": int(sessions_done or 0),
                "students_reached": int(students_reached or 0),
                "upcoming": int(upcoming or 0),
            },
            "points_balance": points,
            "achievements": badges,
            **title_info,
        }

    if "instructor" in roles or "facilitator" in roles:
        from app.models.instructors.payment import PaymentLetter, PaymentSession
        from app.models.enums import PaymentLetterStatus
        from app.models.instructors.training import TrainingVideo, UserTrainingProgress

        letters = (await db.execute(
            select(PaymentLetter.id, PaymentLetter.status).where(
                PaymentLetter.instructor_user_id == uid,
                PaymentLetter.is_published.is_(True),
            )
        )).all()
        letter_ids = [l.id for l in letters]
        pending_sig = sum(1 for l in letters if l.status == PaymentLetterStatus.published)

        if letter_ids:
            totals = (await db.execute(
                select(
                    func.coalesce(func.sum(PaymentSession.compensation_aed), 0),
                    func.coalesce(func.sum(PaymentSession.duration_hours), 0),
                    func.count(PaymentSession.id),
                ).where(PaymentSession.payment_letter_id.in_(letter_ids))
            )).first()
            total_earned, total_hours, total_sessions = float(totals[0]), float(totals[1]), int(totals[2])
        else:
            total_earned = total_hours = 0.0
            total_sessions = 0

        total_videos = await db.scalar(select(func.count()).select_from(TrainingVideo)) or 0
        completed_videos = await db.scalar(
            select(func.count()).select_from(UserTrainingProgress)
            .where(UserTrainingProgress.user_id == uid, UserTrainingProgress.is_completed.is_(True))
        ) or 0

        result["instructor"] = {
            "total_earned_aed": total_earned,
            "total_hours": total_hours,
            "total_sessions": total_sessions,
            "pending_signature": pending_sig,
            "completed_videos": int(completed_videos),
            "total_videos": int(total_videos),
        }

    return result


@router.post("/me/photo", response_model=UserOut)
async def upload_my_photo(
    photo: UploadFile,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import storage
    ext = ("." + photo.filename.rsplit(".", 1)[-1]) if photo.filename and "." in photo.filename else ""
    data = await photo.read()
    photo_path = f"{current_user.id}{ext}"
    url = await storage.upload_file(
        "profile_pictures",
        photo_path,
        data,
        photo.content_type or "image/jpeg",
    )
    current_user.photo_url = url
    current_user.photo_path = photo_path
    await db.commit()
    return await _user_out(current_user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    data: UpdateMeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if data.full_name:
        current_user.full_name = data.full_name
    if data.phone is not None:
        current_user.phone = data.phone or None
    if data.country is not None:
        current_user.country = data.country or None
    if data.linkedin_url is not None:
        current_user.linkedin_url = data.linkedin_url or None

    # Applicant-profile fields (Profile & Settings for instructors/facilitators).
    # Only written when the user actually has an applicant_profile; otherwise the
    # scalar user fields above still save and these are silently ignored.
    profile = await _load_applicant_profile(db, current_user.id)
    if profile is not None:
        if data.city_of_residence is not None:
            profile.city_of_residence = data.city_of_residence or None
        if data.deliver_cities is not None:
            profile.deliver_cities = data.deliver_cities
        if data.has_own_transportation is not None:
            profile.has_own_transportation = data.has_own_transportation

    await db.commit()
    return await _user_out(current_user, profile)


@router.post("/logout")
async def logout():
    # Stateless JWT: the client discards its tokens. Endpoint kept for symmetry.
    return {"detail": "logged out"}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # First-login forced change skips the current-password check.
    if not current_user.must_change_password:
        if not data.current_password or not verify_password(
            data.current_password, current_user.password_hash
        ):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = get_password_hash(data.new_password)
    current_user.must_change_password = False
    await db.commit()
    return {"detail": "password updated"}


async def _email_taken(db: AsyncSession, email: str) -> bool:
    return (await db.execute(select(User.id).where(User.email == email))).first() is not None


@router.post("/instructor-apply", status_code=status.HTTP_201_CREATED, response_model=LoginResponse)
async def instructor_apply(
    payload_json: str = Form(..., alias="payload"),
    cv: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Public instructor application (PLAN §6/§9.2). Checks the invite code
    against BOTH the admin-managed invitation_codes table AND an ambassador's
    users.invite_code (referral). Creates roles=['applicant'] — promotion to
    'instructor' happens later via the admin review state machine
    (routers/instructors/admin.py), not here.

    Multipart: the InstructorApply fields ride in a `payload` JSON part so the
    CV file can be submitted in the same request (mirrors the unified /apply
    flow, which requires a CV for every role)."""
    try:
        payload = InstructorApply.model_validate_json(payload_json)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid application payload")

    if await _email_taken(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    code = payload.invite_code.strip().upper()
    referred_by_ambassador_id = None

    invitation = (await db.execute(
        select(InvitationCode).where(InvitationCode.code == code, InvitationCode.is_active.is_(True))
    )).scalars().first()
    if invitation:
        if invitation.expires_at and invitation.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invitation code has expired")
        if invitation.used_count >= invitation.max_uses:
            raise HTTPException(status_code=400, detail="Invitation code has reached its usage limit")
    else:
        amb = (await db.execute(
            select(User).where(
                User.invite_code == code,
                User.roles.any("ambassador"),
                User.status == "active",
            )
        )).scalars().first()
        if not amb:
            raise HTTPException(status_code=400, detail="Invalid or inactive invite code")
        referred_by_ambassador_id = amb.id

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        roles=[UserRole.applicant],
        country=payload.country,
        status="active",
        must_change_password=False,
        # Mirrors the teacher-apply pattern above (users.invited_by_id) so the
        # ambassadors domain's stats/leaderboard/network queries — which all
        # read users.invited_by_id, not applicant_profiles — count referred
        # instructors correctly. applicant_profiles.referred_by_ambassador_id
        # (below) stays the source of truth for the Phase 3 approval points hook.
        invited_by_id=referred_by_ambassador_id,
        # The exact code they typed — a distinct field from invite_code (an
        # ambassador's own sharable code). Mirrors the legacy portal's
        # users.invitation_code_used, shown on the admin applicant review page.
        invitation_code_used=code,
    )
    db.add(user)
    await db.flush()  # assign user.id

    # CV upload — same "cvs" bucket layout as the unified /apply flow
    cv_path = None
    if cv and cv.filename:
        from app.services import storage
        ext = ("." + cv.filename.rsplit(".", 1)[-1]) if "." in cv.filename else ""
        cv_path = f"instructor/{user.id}{ext}"
        await storage.upload_file("cvs", cv_path, await cv.read(), cv.content_type or "application/pdf")

    db.add(ApplicantProfile(
        user_id=user.id,
        cv_path=cv_path,
        university=payload.university,
        highest_degree=payload.highest_degree,
        highest_degree_other=payload.highest_degree_other,
        city_of_residence=payload.city_of_residence,
        deliver_cities=payload.deliver_cities,
        background_areas=payload.background_areas,
        background_other=payload.background_other,
        has_own_transportation=payload.has_own_transportation,
        country=payload.country,
    ))
    _VIDEO_URLS = [
        "https://youtu.be/6KcV1C1Ui5s",
        "https://youtu.be/qr1AvisQcV8",
        "https://youtu.be/5voQfQOTem8",
    ]
    for video_no, url in enumerate(_VIDEO_URLS, 1):
        db.add(VideoSubmission(user_id=user.id, video_no=video_no, youtube_url=url))
    db.add(ApplicationReview(user_id=user.id))

    if invitation:
        invitation.used_count += 1
    if referred_by_ambassador_id:
        await notify(db, referred_by_ambassador_id, "New Instructor Application",
                     f"{payload.full_name} applied as an instructor with your invite code.", type="instructor")

    await db.commit()
    await db.refresh(user)

    roles = user.role_values
    return {
        "access_token": create_access_token(user.id, roles),
        "refresh_token": create_refresh_token(user.id, roles),
        "token_type": "bearer",
        "user": await _user_out(user),
    }


@router.get("/invite/{code}")
async def validate_invite(code: str, db: AsyncSession = Depends(get_db)):
    normalized = code.strip().upper()
    invitation = (await db.execute(
        select(InvitationCode).where(InvitationCode.code == normalized, InvitationCode.is_active.is_(True))
    )).scalars().first()
    if invitation:
        if invitation.expires_at and invitation.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invitation code has expired")
        if invitation.used_count >= invitation.max_uses:
            raise HTTPException(status_code=400, detail="Invitation code has reached its usage limit")
        return {"ambassador_name": None, "valid": True}

    amb = (await db.execute(
        select(User).where(
            User.invite_code == code,
            User.roles.any("ambassador"),
            User.status == "active"
        )
    )).scalars().first()
    if not amb:
        raise HTTPException(status_code=404, detail="Invalid or inactive invite code")
    return {"ambassador_name": amb.full_name, "valid": True}
