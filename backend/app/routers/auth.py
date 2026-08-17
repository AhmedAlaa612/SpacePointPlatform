from datetime import datetime, timedelta, timezone

import uuid as uuid_lib

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from jose import JWTError, jwt
from sqlalchemy import func, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user
from app.core.rate_limit import enforce_rate_limit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_password_set_token,
    get_password_hash,
    verify_password,
)
from app.db.session import get_db
from app.models.inventory.city import City
from app.models.spine.contact import Contact
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    SetPasswordRequest,
    StudentSignupRequest,
    Token,
    UpdateMeRequest,
    UserOut,
)
from app.models.enums import UserRole
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.video_submission import VideoSubmission
from app.models.instructors.application_review import ApplicationReview
from app.schemas.user import InstructorApply
from app.services.documents.id_card import ensure_card_number
from app.services.invitations import resolve_invite_code
from app.services.nicknames import assign_nickname, reroll_nickname
from app.services.notification import create_notification as notify
from app.services.spine.identity import ensure_guardian_relationship, resolve_or_create_contact

router = APIRouter(prefix="/auth", tags=["auth"])

# B6: the existing rate_limit.py brake is 1000 req/min/IP (deliberately
# generous — a whole school shares one IP), useless against password
# guessing. This is the real defence: a per-account counter, checked before
# the password itself so a locked account can't be probed during its window.
_MAX_FAILED_LOGIN_ATTEMPTS = 10
_LOCKOUT_MINUTES = 15


async def _user_out(db: AsyncSession, user: User, profile: ApplicantProfile | None = None) -> dict:
    from app.services import storage

    # Demographic fields (date_of_birth/grade, 2026-08-08) live on the
    # spine Contact, not on User — resolved here so every /auth response
    # (signup, login, /auth/me) can carry them for form-prefill purposes.
    # None for staff users without a linked contact_id.
    contact = await db.get(Contact, user.contact_id) if user.contact_id else None
    city = await db.get(City, user.city_id) if user.city_id else None

    # City NAMES alongside the ids (2026-08-09). Every consumer that displays
    # a user — the admin profile modal, the instructor directory — needs names,
    # and resolving them client-side meant every such surface separately
    # fetching /public/cities just to build an id->name map. Resolved in one
    # query here instead. Order follows deliver_city_ids so the printed list
    # matches whatever order the instructor picked.
    residence_city = (
        await db.get(City, profile.city_of_residence_id)
        if profile and profile.city_of_residence_id
        else None
    )
    deliver_ids = list(profile.deliver_city_ids or []) if profile else []
    deliver_names: list[str] = []
    if deliver_ids:
        found = (await db.execute(select(City).where(City.id.in_(deliver_ids)))).scalars().all()
        by_id = {c.id: c.name for c in found}
        # Skip ids whose city was deleted rather than emitting a null hole.
        deliver_names = [by_id[i] for i in deliver_ids if i in by_id]

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
        "nickname": user.nickname,
        "avatar": user.avatar,
        "invitation_code_used": user.invitation_code_used,
        "created_at": user.created_at,
        # SP-0000 identity number, shared across every role this person holds
        # (services/documents/id_card.py). Was entirely missing from this
        # response — public/admin profile views had no way to show or search
        # by it (bug fix, 2026-08-17).
        "card_number": user.card_number,
        "card_id": f"SP-{user.card_number:04d}-UAE" if user.card_number is not None else None,
        "date_of_birth": contact.date_of_birth if contact else None,
        "grade": contact.grade if contact else None,
        "city_id": user.city_id,
        "city_name": city.name if city else None,
        "city_other": user.city_other,
        # Applicant-profile fields — surfaced on Profile & Settings for
        # instructors/facilitators/applicants. None when no profile exists.
        "city_of_residence_id": profile.city_of_residence_id if profile else None,
        "city_of_residence_name": residence_city.name if residence_city else None,
        "deliver_city_ids": profile.deliver_city_ids if profile else None,
        "deliver_city_names": deliver_names or None,
        "has_own_transportation": profile.has_own_transportation if profile else None,
    }


async def _load_applicant_profile(db: AsyncSession, user_id) -> ApplicantProfile | None:
    return (
        await db.execute(select(ApplicantProfile).where(ApplicantProfile.user_id == user_id))
    ).scalars().first()


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == data.email))).scalars().first()

    # Checked before the password compare, on purpose — a locked account
    # gets the same 429 regardless of whether this guess would've been
    # right, so lockout state itself can't be probed.
    if user and user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts — try again later",
        )

    if not user or not verify_password(data.password, user.password_hash):
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= _MAX_FAILED_LOGIN_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
            await db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Correct password proven — reset lockout state regardless of what the
    # active-status check below decides.
    user.failed_login_count = 0
    user.locked_until = None

    roles = user.role_values
    if "admin" not in roles and user.status != "active":
        await db.commit()
        raise HTTPException(status_code=403, detail="Account is not active")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "access_token": create_access_token(user.id, roles),
        "refresh_token": create_refresh_token(user.id, roles),
        "token_type": "bearer",
        "user": await _user_out(db, user),
    }


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=LoginResponse)
async def student_signup(data: StudentSignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """LMS student self-signup (LM1-4).

    B6 (2026-08-10): rate-limited the same way the public registration form
    is (`LMS_EXECUTION_PLAN.md` §8 Q6 closed this the same way and it was
    never wired up) — the generous per-IP brake, not a per-account counter
    (there's no account yet to key one on).

    Identity evaluate → find-or-create contact (`resolve_or_create_contact`, so
    a public-form registrant who never made an account gets *linked*, not
    duplicated) → create a `users` row with `roles=['student']` +
    `contact_id` → return the same JWT shape as /auth/login. Login/refresh are
    untouched: students log in through /auth/login like everyone else.

    A duplicate email is a 409 with a friendly "log in" prompt — never a raw
    IntegrityError. The email check runs *before* any contact work so a repeat
    signup can't churn the spine layer.

    invite_code/parent_* (2026-08-08) reuse the exact mechanisms
    instructor_apply and public_register already use — see
    services/invitations.py::resolve_invite_code and
    services/spine/identity.py::ensure_guardian_relationship.
    country/city_id (2026-08-08) live on `User` directly, not the Contact
    spine (too broad a field to restructure for this) — see
    models/user.py::User.city_id's docstring. The resolved city name is
    still gap-filled onto the Contact's free-text `city` too, so the CRM's
    existing Contact views show it without needing to know about the new
    structured field."""
    enforce_rate_limit(request)

    email = _lower_email(data.email)
    if await _email_taken(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists — log in instead.",
        )

    # Invite-code gate (2026-08-13, operator): student signup is invite-only,
    # ported from Madar where registration required a valid, active,
    # non-exhausted code and stamped it permanently onto the user
    # (MISSIONS_REPORT.md §155). Enforced here rather than only in the
    # schema so the message is a plain sentence rather than a 422 field
    # error, and so it can't be bypassed by a client that omits the key.
    code = data.invite_code.strip().upper() if data.invite_code else None
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An invite code is required to sign up. Ask your instructor for one.",
        )
    # kind='student': an instructor-pool code must not open student signup.
    # An ambassador's personal referral code still works (it's kind-agnostic
    # inside resolve_invite_code) — the operator's explicit call.
    invitation, ambassador = await resolve_invite_code(db, code, kind="student")
    referred_by_ambassador_id = ambassador.id if ambassador else None

    city = await db.get(City, data.city_id) if data.city_id else None

    contact, _ = await resolve_or_create_contact(
        db,
        full_name=data.full_name,
        phone=data.phone,
        email=email,
        contact_roles=["student"],
        role_event_source="lms_signup",
        date_of_birth=data.date_of_birth,
        country=data.country,
        city=city.name if city else (data.city_other or None),
    )

    if data.parent_name and data.parent_phone:
        guardian, _ = await resolve_or_create_contact(
            db,
            full_name=data.parent_name,
            phone=data.parent_phone,
            email=data.parent_email,
            contact_roles=["parent_guardian"],
        )
        await ensure_guardian_relationship(db, student_id=contact.id, guardian_id=guardian.id)

    user = User(
        full_name=data.full_name,
        email=email,
        password_hash=get_password_hash(data.password),
        roles=[UserRole.student],
        status="active",
        must_change_password=False,
        contact_id=contact.id,
        phone=data.phone,
        country=data.country,
        city_id=data.city_id,
        city_other=data.city_other,
        invited_by_id=referred_by_ambassador_id,
        invitation_code_used=code,
    )
    db.add(user)
    await db.flush()  # assign user.id
    await assign_nickname(db, user)
    await ensure_card_number(db, user)

    if invitation:
        invitation.used_count += 1
    if referred_by_ambassador_id:
        await notify(db, referred_by_ambassador_id, "New Student Signup",
                     f"{data.full_name} signed up as a student with your invite code.", type="student")

    await db.commit()
    await db.refresh(user)

    roles = user.role_values
    return {
        "access_token": create_access_token(user.id, roles),
        "refresh_token": create_refresh_token(user.id, roles),
        "token_type": "bearer",
        "user": await _user_out(db, user),
    }


def _lower_email(email: str) -> str:
    """The same lowercase+strip key /auth/login compares on — see
    normalize_email in services/spine/identity.py for the canonical matched
    form (which also normalizes phone). Storing anything else here would let a
    duplicate slip past login's exact compare."""
    return email.strip().lower()


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
    return await _user_out(db, current_user, profile)


@router.post("/me/nickname/reroll", response_model=UserOut)
async def reroll_my_nickname(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Student self-service only (8-1/D2) — no staff override endpoint
    exists. 429s if called again within 7 days of the last reroll."""
    if "student" not in current_user.role_values:
        raise HTTPException(status_code=400, detail="Only student accounts have a nickname")
    await reroll_nickname(db, current_user)
    await db.commit()
    await db.refresh(current_user)
    profile = await _load_applicant_profile(db, current_user.id)
    return await _user_out(db, current_user, profile)


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
    # Load the applicant profile (2026-08-09) — without it _user_out reports
    # city_of_residence/deliver_city_ids as null for EVERY user, which is why
    # the admin profile modal could never show an instructor's residence or
    # open-to-work cities. /auth/me and login already passed it; this endpoint
    # was the outlier.
    return await _user_out(db, user, await _load_applicant_profile(db, uid))


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

    if "student" in roles:
        # A student's profile used to show only their program registration —
        # everything they had actually *done* on the platform was invisible on
        # the one screen meant to represent them. Courses and missions are the
        # substance of a learner's record; the registration is just how they
        # got in.
        from app.models.lms.course import Course
        from app.models.lms.enrollment import Enrollment
        from app.models.missions.mission import Mission, MissionAttempt
        from app.models.spine.contact import Contact
        from app.models.spine.organization import Organization
        from app.services.lms.admin_progress import DESIGN_STEP_LABELS, design_steps_for_attempts
        from app.services.lms.progress import batch_course_completion
        from app.services.points import lifetime_points as student_points

        enrollments = (await db.execute(
            select(Enrollment, Course)
            .join(Course, Course.id == Enrollment.course_id)
            .where(Enrollment.user_id == uid, Enrollment.status == "active")
            .order_by(Course.title)
        )).all()

        courses: list[dict] = []
        for enrollment, course in enrollments:
            # One course at a time, but batched over a single-element list so
            # the completion rule stays the one shared implementation rather
            # than a second copy that can drift from it.
            completion = (await batch_course_completion(
                db, user_ids=[uid], course_id=course.id,
            )).get(uid) or {"pct": 0, "modules_done": 0, "modules_total": 0}
            total = completion["modules_total"]
            done = completion["modules_done"]
            courses.append({
                "course_id": str(course.id),
                "title": course.title,
                "modules_total": total,
                "modules_completed": done,
                "percent": completion["pct"],
                "completed": total > 0 and done == total,
                "enrolled_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
            })

        attempt_rows = (await db.execute(
            select(MissionAttempt, Mission)
            .join(Mission, Mission.id == MissionAttempt.mission_id)
            .where(MissionAttempt.user_id == uid)
            .order_by(MissionAttempt.started_at.desc())
        )).all()

        # One entry per mission, showing its best outcome — a profile is a
        # record of what someone achieved, not a log of every retry.
        best: dict[str, dict] = {}
        for attempt, mission in attempt_rows:
            key = str(mission.id)
            score = float(attempt.score) if attempt.score is not None else None
            current = best.get(key)
            if current is None:
                best[key] = {
                    "mission_id": key, "title": mission.title, "kind": mission.kind,
                    "status": attempt.status, "score": score, "attempts": 1,
                    "phases": [],
                }
                continue
            current["attempts"] += 1
            if attempt.status == "passed" and current["status"] != "passed":
                current["status"] = "passed"
                current["score"] = score
            elif score is not None and (current["score"] is None or score > current["score"]):
                current["score"] = score

        # The phases behind each mission row. A status word alone ("in
        # progress") says a student is stuck without saying where — the
        # phases are what turn the profile into something an instructor can
        # act on. Design missions have real steps; other kinds report none
        # rather than inventing a fake sequence to look uniform.
        steps_by_attempt = await design_steps_for_attempts(
            db, [attempt.id for attempt, _ in attempt_rows],
        )
        for attempt, mission in attempt_rows:
            entry = best.get(str(mission.id))
            steps = steps_by_attempt.get(attempt.id)
            if entry is None or not steps:
                continue
            done = sum(1 for key, _ in DESIGN_STEP_LABELS if steps.get(key))
            # Keep the furthest-along attempt's phases, which is not always
            # the best-scoring one.
            if done <= len(entry.get("phases") or []) and entry.get("phases"):
                if done <= sum(1 for p in entry["phases"] if p["done"]):
                    continue
            entry["phases"] = [
                {"key": key, "label": label, "done": bool(steps.get(key))}
                for key, label in DESIGN_STEP_LABELS
            ]

        missions = list(best.values())

        # Personal details the profile shows beside the progress — school and
        # grade live on the contact behind the account, and the invite code is
        # the one on the user row (which code they actually typed at signup).
        contact = await db.get(Contact, user.contact_id) if user.contact_id else None
        organization = (
            await db.get(Organization, contact.organization_id)
            if contact is not None and contact.organization_id else None
        )

        result["student"] = {
            "points_balance": await student_points(db, uid),
            "photo_url": user.photo_url,
            "nickname": user.nickname,
            "invitation_code_used": user.invitation_code_used,
            "school_name": organization.name_latin if organization else None,
            "grade": contact.grade if contact else None,
            "courses": courses,
            "courses_completed": sum(1 for c in courses if c["completed"]),
            "missions": missions,
            "missions_passed": sum(1 for m in missions if m["status"] == "passed"),
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
    return await _user_out(db, current_user)


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
    if data.city_id is not None:
        current_user.city_id = data.city_id
    if data.city_other is not None:
        current_user.city_other = data.city_other or None

    # Applicant-profile fields (Profile & Settings for instructors/facilitators).
    # Used to silently no-op when the user had no applicant_profile row — true
    # for any instructor whose account wasn't created via the applicant
    # pipeline (seeded, invited directly, promoted pre-pipeline). City of
    # Residence and Delivery Cities would "save" in the UI and vanish on
    # refresh. Lazily create the row instead, same precedent as
    # InstructorProfile's own get-or-create (routers/instructors/instructor.py)
    # — every field here is nullable or has a default, so an empty row is safe.
    profile = await _load_applicant_profile(db, current_user.id)
    wants_applicant_fields = any(
        f is not None
        for f in (data.city_of_residence_id, data.deliver_city_ids, data.has_own_transportation)
    )
    if profile is None and wants_applicant_fields:
        profile = ApplicantProfile(user_id=current_user.id)
        db.add(profile)
        await db.flush()
    if profile is not None:
        if data.city_of_residence_id is not None:
            profile.city_of_residence_id = data.city_of_residence_id
        if data.deliver_city_ids is not None:
            profile.deliver_city_ids = data.deliver_city_ids
        if data.has_own_transportation is not None:
            profile.has_own_transportation = data.has_own_transportation

    await db.commit()
    return await _user_out(db, current_user, profile)


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


@router.post("/set-password")
async def set_password(
    data: SetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """LM1-7 — the ops-created-account invite link (§8 Q5). Token-authenticated
    (core/security.py's create_password_set_token, 24h), not a logged-in-user
    action — the whole point is the student doesn't have a working password yet."""
    try:
        user_id = decode_password_set_token(data.token)
    except JWTError:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired")

    user = await db.get(User, uuid_lib.UUID(user_id))
    if user is None:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired")

    user.password_hash = get_password_hash(data.new_password)
    user.must_change_password = False
    await db.commit()
    return {"detail": "password set"}


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

    code = payload.invite_code.strip().upper() if payload.invite_code else None
    # Code is optional (organic applicants have none) — but if one is
    # supplied it must be valid, so a typo'd/expired code doesn't silently
    # drop the referral. kind='instructor' (2026-08-13): a student batch code
    # must not open the instructor pipeline.
    invitation, ambassador = await resolve_invite_code(db, code, kind="instructor")
    referred_by_ambassador_id = ambassador.id if ambassador else None

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
    await ensure_card_number(db, user)

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
        city_of_residence_id=payload.city_of_residence_id,
        deliver_city_ids=payload.deliver_city_ids,
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
        "user": await _user_out(db, user),
    }


@router.get("/invite/{code}")
async def validate_invite(code: str, kind: str | None = None, db: AsyncSession = Depends(get_db)):
    # This endpoint's contract predates resolve_invite_code() and differs
    # from it slightly (404 "not found" rather than 400 "bad request", no
    # used_count/invited_by_id side effects — it's a read-only check) — reuse
    # the shared lookup/expiry/usage-limit logic, just remap the exceptions.
    #
    # `kind` is optional so the existing contract is unchanged for anything
    # already calling this; the signup screens pass their own pool so a
    # student batch code doesn't validate green on the instructor form.
    try:
        invitation, ambassador = await resolve_invite_code(db, code, kind=kind)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_400_BAD_REQUEST and exc.detail == "Invalid or inactive invite code":
            raise HTTPException(status_code=404, detail=exc.detail)
        raise
    if invitation:
        return {"ambassador_name": None, "valid": True}
    return {"ambassador_name": ambassador.full_name, "valid": True}
