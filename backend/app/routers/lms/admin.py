"""LMS authoring routes (LM1-5) — `/lms/admin/*`, gated by `require_lms_content`
(operations + facilitator; admin passes automatically, core/dependencies.py).

Simple CRUD lives directly in the router, matching the established convention
(routers/sessions/programs.py). The one piece of business logic here is
content-shape validation per item kind — `content` is free-form JSONB in the
DB (LMS_EXECUTION_PLAN.md §2), but the author-facing shapes are fixed, so we
validate through the `AdminContent*` models before ever writing to the column.

This is also the API LM1-9's bulk-import script drives.
"""

import uuid
from pathlib import Path
from typing import Literal

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_lms_content
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.lms import Course, CourseModule, Enrollment, ModuleItem, VideoCheckpoint
from app.models.videos import Video
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.missions.mission import Mission
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.instructors.invitation_code import InvitationCode
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.team import Team
from app.schemas.lms import AttachmentUrlOut
from app.schemas.lms_admin import (
    AdminCheckpointNoteContent,
    AdminCheckpointQuizContent,
    AdminContentAttachment,
    AdminContentFlashcards,
    AdminContentMission,
    AdminContentQuiz,
    AdminContentText,
    AdminContentVideo,
    BulkGrantIn,
    BulkGrantOut,
    CourseAdminOut,
    CourseCreate,
    CourseUpdate,
    EnrollmentAdminOut,
    EnrollmentGrantIn,
    InstructorOptionOut,
    InviteCodeCreate,
    InviteCodeGrantCreate,
    InviteCodeGrantCreateOut,
    InviteCodeGrantOut,
    InviteCodeOut,
    InviteCodeUpdate,
    ItemAdminOut,
    ObserverTeamSummaryOut,
    TryAsObserverIn,
    ItemCreate,
    ItemReorderIn,
    ItemUpdate,
    LearningPathAdminOut,
    LearningPathCreate,
    LearningPathRosterRowOut,
    LearningPathStepIn,
    LearningPathStepOut,
    LearningPathUpdate,
    CohortPosterTemplateIn,
    LmsProgramCohortEffectiveOut,
    LmsProgramCreate,
    LmsProgramItemIn,
    LmsProgramItemOut,
    LmsProgramItemReorderIn,
    LmsProgramOut,
    LmsProgramUpdate,
    ModuleAdminOut,
    ModuleCreate,
    ModuleReorderIn,
    ModuleUpdate,
    StaffOptionOut,
    StudentProfileOut,
    StudentProgramOut,
    StudentSummaryOut,
    VideoCheckpointAdminOut,
    VideoCheckpointCreate,
    VideoCheckpointUpdate,
)
from app.schemas.lms_cohort_quiz import (
    CohortQuizTopicBreakdownOut,
)
from app.schemas.curriculum import PrerequisiteEdgeIn, PrerequisiteEdgeOut
from app.schemas.lms_progress_grid import (
    CourseOverviewRowOut, CourseProgressAllOut, MissionOverviewRowOut, MissionProgressAllOut, ProgressGridOut,
    StudentDesignRunsOut,
)
from app.services import curriculum as curriculum_service
from app.services import storage
from app.services.lms import enroll, enrollment_is_active
from app.services.lms.admin_progress import (
    cohort_progress_grid, course_progress_all, courses_overview, mission_progress_all, missions_overview,
    student_design_runs,
)
from app.services.lms import cohort_quiz as cohort_quiz_service
from app.services.lms.author_access import (
    check_checkpoint_access,
    check_course_access,
    check_course_publish_access,
    check_invite_code_access,
    check_item_access,
    check_learning_path_access,
    check_learning_path_publish_access,
    check_module_access,
    get_author_permissions,
)
from app.services.lms.invite_grants import grant_invite_code_access
from app.services.lms.my_programs import my_programs
from app.services.lms import students as student_search_service
from app.services.lms.program import (
    PROGRAM_ITEM_PDF_BUCKET, assign_lms_program, check_item_conflicts, effective_cohort_program_items,
    ensure_observer_team, fork_cohort_override,
    guard_locked_submission_scope, item_out, items_out, next_position, renumber_program_items, reorder_program_items,
    resolve_cohort_program, sync_cohort_assignments, sync_program_assignments, sync_team_mission_runs,
    validate_item_payload, validate_item_refs,
)
from app.services.teams import create_team, join_team, team_member_ids
from app.schemas.missions_component_config import ComponentConfigIn, ComponentConfigOut
from app.services.missions import component_config as component_config_service
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES
from app.services.video_service import attach_embed_link, attach_upload, enqueue_transcode, get_playback_info, get_video_for_owner
from app.services.video_service import delete as delete_video
from app.workers.settings import get_arq_redis

router = APIRouter(prefix="/lms/admin", tags=["lms-admin"])

COURSE_IMAGE_BUCKET = "lms-course-images"
LEARNING_PATH_IMAGE_BUCKET = "lms-learning-path-images"
PROGRAM_IMAGE_BUCKET = "lms-program-images"
MAX_IMAGE_BYTES = 4 * 1024 * 1024 * 1024  # 4GB — platform-wide upload cap
ATTACHMENT_BUCKET = "lms-attachments"
MAX_ATTACHMENT_BYTES = 4 * 1024 * 1024 * 1024  # 4GB — platform-wide upload cap


async def _course_admin_out(db: AsyncSession, course: Course, current: User | None = None) -> CourseAdminOut:
    """`CourseAdminOut` carries two derived fields (`image_url`,
    `instructor_name`, `created_by_name`) that aren't real columns on `Course` — Pydantic's
    `from_attributes` can't resolve those from the bare ORM object, so every
    course-returning endpoint goes through this instead of `return course`."""
    image_url = await storage.resolve_url(course.image_bucket, course.image_path)
    instructor_name = None
    if course.instructor_id:
        instructor = await db.get(User, course.instructor_id)
        instructor_name = instructor.full_name if instructor else None

    # Only admin and operations are allowed to view audit metadata (created_by, created_at)
    can_view_audit = bool(current and any(r in ("admin", "operations") for r in current.role_values))
    created_by = course.created_by if can_view_audit else None
    created_at = course.created_at if can_view_audit else None
    created_by_name = None
    if can_view_audit and course.created_by:
        creator = await db.get(User, course.created_by)
        created_by_name = creator.full_name if creator else None

    return CourseAdminOut(
        id=course.id, title=course.title, description=course.description, kind=course.kind,
        is_published=course.is_published, created_by=created_by,
        created_by_name=created_by_name, created_at=created_at,
        image_url=image_url, outcomes=course.outcomes or [], level=course.level, track=course.track,
        instructor_id=course.instructor_id, instructor_name=instructor_name,
        instructor_title=course.instructor_title,
        access_mode=course.access_mode, access_days=course.access_days,
        price_cents=course.price_cents, currency=course.currency,
        certificate_enabled=course.certificate_enabled,
    )



_CONTENT_MODEL = {
    "text": AdminContentText,
    "quiz": AdminContentQuiz,
    "flashcards": AdminContentFlashcards,
    "video": AdminContentVideo,
    "attachment": AdminContentAttachment,
    "mission": AdminContentMission,
}


def _validated_content(*, kind: str, content: dict) -> dict:
    model = _CONTENT_MODEL.get(kind)
    if model is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown item kind '{kind}'")
    try:
        parsed = model(**content)
    except ValidationError as exc:
        # include_context=False — a model_validator's raised ValueError
        # instance itself lands in ctx.error otherwise, which json.dumps
        # can't serialize (FastAPI's own exception handler runs input
        # through jsonable_encoder first; a manually-raised HTTPException
        # like this one does not, so it must already be JSON-safe).
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.errors(include_context=False))
    # mode="json": AdminContentMission's mission_id/variant_id are UUID
    # fields (the first content model with one) — plain model_dump() would
    # hand back UUID objects, which JSONB can't bind. mode="json" stringifies
    # them; every other kind's fields are already JSON-native, so this is a
    # no-op for them.
    return parsed.model_dump(mode="json")


_CHECKPOINT_CONTENT_MODEL = {
    "note": AdminCheckpointNoteContent,
    "quiz": AdminCheckpointQuizContent,
}


def _validated_checkpoint_content(*, kind: str, content: dict) -> dict:
    model = _CHECKPOINT_CONTENT_MODEL[kind]
    try:
        parsed = model(**content)
    except ValidationError as exc:
        # include_context=False: the custom model_validator's ValueError
        # objects land in `ctx.error` by default, and a raw exception isn't
        # JSON-serializable — without this, FastAPI's own error response
        # encoding blows up instead of returning a clean 400.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.errors(include_context=False))
    return parsed.model_dump()


# ── instructor picker (LMS redesign, 2026-08-06) ────────────────────────────

@router.get("/instructors", response_model=list[InstructorOptionOut])
async def list_instructor_options(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Who can be set as a course's public-facing instructor — deliberately
    broader than "who's allowed to author" (require_lms_content): an
    instructor role holder who never touches the authoring UI can still be
    the person shown on a course landing page."""
    rows = (await db.execute(
        select(User)
        .where(User.roles.overlap(["instructor", "facilitator", "operations", "admin"]))
        .order_by(User.full_name)
    )).scalars().all()
    return [InstructorOptionOut(id=u.id, full_name=u.full_name, photo_url=u.photo_url) for u in rows]


# ── staff assignment picker (2026-08-12) ────────────────────────────────────

@router.get("/users", response_model=list[StaffOptionOut])
async def search_staff(
    role: str | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Named-individual search for the course/mission assignment picker —
    any staff account (`student` excluded; that role self-enrols or is
    bulk-granted by cohort, never picked by name here). `role` narrows to one
    held role, `q` is a case-insensitive substring match on name or email.
    Capped at 25 rows — a picker, not a roster export."""
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        return []
    stmt = select(User).where(~User.roles.contains(["student"]))
    if role is not None:
        stmt = stmt.where(User.roles.any(role))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    rows = (await db.execute(stmt.order_by(User.full_name).limit(25))).scalars().all()
    return [StaffOptionOut(id=u.id, full_name=u.full_name, email=u.email, roles=u.role_values) for u in rows]


# ── student management (2026-08-12) ─────────────────────────────────────────
# require_admin's user list is admin-only and wrong for operations/facilitator
# here — same reasoning as `search_staff` above, mirrored for the `student`
# role instead of "every role but student".

@router.get("/students", response_model=list[StudentSummaryOut])
async def search_students(
    q: str | None = None,
    invite_code: str | None = None,
    login_status: Literal["all", "never", "has_logged_in"] = "all",
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Name/email substring search over student accounts, capped at 50 rows
    — the list view backing the student-management page.

    `invite_code` filters to one batch (2026-08-13). The literal string
    `none` selects students with no code at all — the ones who signed up
    before the gate existed; without it they'd be unreachable through the
    filter, since "no code" isn't a code you can type.

    `login_status` (2026-09-16) filters on whether the account has ever
    actually been logged into (`User.last_login_at`), not just whether it
    exists.

    The actual query lives in `services/lms/students.py` (extracted
    2026-09-14) — the Competition Judging Assign tab's cohort-scoped search
    reuses it rather than re-implementing this from scratch."""
    return await student_search_service.search_students(db, q=q, invite_code=invite_code, login_status=login_status)


# ── student invite codes (2026-08-13) ───────────────────────────────────────
# Ops-managed, distinct from the admin-only instructor codes at
# /instructors/admin/invitations — same table, split by `kind` so a school
# batch code can't open the instructor application pipeline.

async def _invite_code_out(db: AsyncSession, row: InvitationCode) -> InviteCodeOut:
    signups = await db.scalar(
        select(func.count()).select_from(User).where(User.invitation_code_used == row.code)
    )
    return InviteCodeOut(
        id=row.id, code=row.code, kind=row.kind, label=row.label, is_active=row.is_active,
        max_uses=row.max_uses, used_count=row.used_count, expires_at=row.expires_at,
        created_at=row.created_at, created_by=row.created_by, signups=signups or 0,
    )


@router.get("/invite-codes", response_model=list[InviteCodeOut])
async def list_invite_codes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lms_content),
):
    _, scope_all = await get_author_permissions(db, current_user)
    # Observer mode (2026-10): the ops list covers both learner batches —
    # student and observer codes alike.
    stmt = select(InvitationCode).where(InvitationCode.kind.in_(["student", "observer"]))
    if not scope_all:
        stmt = stmt.where(InvitationCode.created_by == current_user.id)
    stmt = stmt.order_by(InvitationCode.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [await _invite_code_out(db, r) for r in rows]


@router.post("/invite-codes", response_model=InviteCodeOut, status_code=status.HTTP_201_CREATED)
async def create_invite_code(
    body: InviteCodeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lms_content),
):
    code = body.code.strip().upper()
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Code can't be blank")
    # `code` is unique across both pools, so this has to check globally, not
    # just within kind='student' — otherwise the insert fails on the
    # constraint with an opaque 500 instead of this message.
    existing = (await db.execute(
        select(InvitationCode).where(InvitationCode.code == code)
    )).scalars().first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="That code already exists")

    row = InvitationCode(
        id=uuid.uuid4(), code=code, kind=body.kind, label=body.label,
        max_uses=body.max_uses, is_active=body.is_active, expires_at=body.expires_at,
        created_by=current_user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return await _invite_code_out(db, row)


@router.patch("/invite-codes/{code_id}", response_model=InviteCodeOut)
async def update_invite_code(
    code_id: uuid.UUID,
    body: InviteCodeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lms_content),
):
    row = await db.get(InvitationCode, code_id)
    if row is None or row.kind not in ("student", "observer"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite code not found")
    await check_invite_code_access(db, current_user, row)

    updates = body.model_dump(exclude_unset=True)
    if "code" in updates and updates["code"]:
        new_code = updates["code"].strip().upper()
        if new_code != row.code:
            clash = (await db.execute(
                select(InvitationCode).where(InvitationCode.code == new_code)
            )).scalars().first()
            if clash is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="That code already exists")
            # Renaming leaves already-signed-up students stamped with the old
            # string (users.invitation_code_used is a historical record of what
            # was typed, not a live FK) — so they'd drop out of this batch's
            # filter. Relabel instead of renaming once a code is in use.
            if await db.scalar(
                select(func.count()).select_from(User).where(User.invitation_code_used == row.code)
            ):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="This code has already been used to sign up — change its label instead of its code.",
                )
        updates["code"] = new_code

    for field, value in updates.items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return await _invite_code_out(db, row)


@router.delete("/invite-codes/{code_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invite_code(
    code_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lms_content),
):
    """Refuses once anyone has signed up on it — the code is the only record
    of which batch those students belong to (users.invitation_code_used is a
    plain string, not an FK, so deleting the row would silently orphan them
    from the filter rather than cascade). Deactivate it instead."""
    row = await db.get(InvitationCode, code_id)
    if row is None or row.kind not in ("student", "observer"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite code not found")
    await check_invite_code_access(db, current_user, row)
    signups = await db.scalar(
        select(func.count()).select_from(User).where(User.invitation_code_used == row.code)
    )
    if signups:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"{signups} student(s) signed up with this code. Deactivate it instead of deleting it.",
        )
    await db.delete(row)
    await db.commit()


# ── invite-code course/path grants (2026-08-21) ─────────────────────────────
# "This code batch gets these courses/paths free" — the code IS the batch,
# same users.invitation_code_used string-match the page above already uses.

async def _invite_code_grant_out(db: AsyncSession, grant: InvitationCodeGrant) -> InviteCodeGrantOut:
    course_title = None
    learning_path_title = None
    cohort_name = None
    lms_program_name = None
    if grant.course_id is not None:
        course = await db.get(Course, grant.course_id)
        course_title = course.title if course else None
    if grant.learning_path_id is not None:
        path = await db.get(LearningPath, grant.learning_path_id)
        learning_path_title = path.title if path else None
    if grant.cohort_id is not None:
        cohort = await db.get(Cohort, grant.cohort_id)
        cohort_name = cohort.name if cohort else None
        if cohort is not None:
            resolved = await resolve_cohort_program(db, grant.cohort_id)
            if resolved is not None:
                lms_program_name = resolved[0].name
    return InviteCodeGrantOut(
        id=grant.id, product_type=grant.product_type,
        course_id=grant.course_id, course_title=course_title,
        learning_path_id=grant.learning_path_id, learning_path_title=learning_path_title,
        cohort_id=grant.cohort_id, cohort_name=cohort_name, lms_program_name=lms_program_name,
        created_at=grant.created_at,
    )


@router.get("/invite-codes/{code_id}/grants", response_model=list[InviteCodeGrantOut])
async def list_invite_code_grants(
    code_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lms_content),
):
    code = await db.get(InvitationCode, code_id)
    if code is None or code.kind != "student":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite code not found")
    await check_invite_code_access(db, current_user, code)
    rows = (await db.execute(
        select(InvitationCodeGrant).where(InvitationCodeGrant.invitation_code_id == code_id)
        .order_by(InvitationCodeGrant.created_at)
    )).scalars().all()
    return [await _invite_code_grant_out(db, r) for r in rows]


@router.post(
    "/invite-codes/{code_id}/grants", response_model=InviteCodeGrantCreateOut, status_code=status.HTTP_201_CREATED,
)
async def create_invite_code_grant(
    code_id: uuid.UUID,
    body: InviteCodeGrantCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Applies immediately (§ model docstring) — every account that's ever
    used this code gets enrolled the moment this returns, not just future
    signups."""
    code = await db.get(InvitationCode, code_id)
    if code is None or code.kind != "student":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite code not found")
    await check_invite_code_access(db, current, code)

    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        if body.course_id is not None:
            c = await db.get(Course, body.course_id)
            if not c or c.created_by != current.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only grant access to courses you authored")
        elif body.learning_path_id is not None:
            lp = await db.get(LearningPath, body.learning_path_id)
            if not lp or lp.created_by != current.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only grant access to learning paths you authored")
        elif body.cohort_id is not None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Authors cannot grant access to cohorts")

    if body.course_id is not None:
        if await db.get(Course, body.course_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
        clash = (await db.execute(
            select(InvitationCodeGrant.id).where(
                InvitationCodeGrant.invitation_code_id == code_id, InvitationCodeGrant.course_id == body.course_id,
            )
        )).first()
    elif body.learning_path_id is not None:
        if await db.get(LearningPath, body.learning_path_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
        clash = (await db.execute(
            select(InvitationCodeGrant.id).where(
                InvitationCodeGrant.invitation_code_id == code_id,
                InvitationCodeGrant.learning_path_id == body.learning_path_id,
            )
        )).first()
    else:
        if await db.get(Cohort, body.cohort_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
        clash = (await db.execute(
            select(InvitationCodeGrant.id).where(
                InvitationCodeGrant.invitation_code_id == code_id, InvitationCodeGrant.cohort_id == body.cohort_id,
            )
        )).first()
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already granted to this code")

    grant, accounts_enrolled = await grant_invite_code_access(
        db, invitation_code=code, course_id=body.course_id, learning_path_id=body.learning_path_id,
        cohort_id=body.cohort_id,
    )
    await db.commit()
    return InviteCodeGrantCreateOut(
        grant=await _invite_code_grant_out(db, grant), accounts_enrolled=accounts_enrolled,
    )


@router.delete("/invite-codes/{code_id}/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invite_code_grant(
    code_id: uuid.UUID,
    grant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Stops the rule applying going forward only — never revokes access
    already granted, same posture as deleting a `LearningPath` leaving its
    students' enrollments untouched."""
    grant = await db.get(InvitationCodeGrant, grant_id)
    if grant is None or grant.invitation_code_id != code_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Grant not found")

    code = await db.get(InvitationCode, code_id)
    if code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite code not found")
    await check_invite_code_access(db, current, code)

    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        if grant.course_id is not None:
            c = await db.get(Course, grant.course_id)
            if not c or c.created_by != current.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only manage grants for courses you authored")
        elif grant.learning_path_id is not None:
            lp = await db.get(LearningPath, grant.learning_path_id)
            if not lp or lp.created_by != current.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only manage grants for learning paths you authored")
        elif grant.cohort_id is not None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Authors cannot manage cohort grants")

    await db.delete(grant)
    await db.commit()


@router.get("/students/{user_id}", response_model=StudentProfileOut)
async def student_profile(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Profile: nickname, programs attended. Current courses are a separate
    call — `GET /lms/admin/users/{user_id}/enrollments` already returns
    exactly that (per-student enrollments, built in P1-5), so this endpoint
    doesn't duplicate it."""
    user = await db.get(User, user_id)
    if user is None or not ({"student", "observer"} & set(user.role_values)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    programs = await my_programs(db, user=user)
    return StudentProfileOut(
        id=user.id, full_name=user.full_name, nickname=user.nickname, avatar=user.avatar,
        email=user.email, programs=[StudentProgramOut(**p) for p in programs],
    )


@router.get("/students/{user_id}/design-runs", response_model=StudentDesignRunsOut)
async def student_design_runs_route(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Every CubeSat design run this student has, most recent first — plural
    since 2026-08-15, a student can run several concurrently. Same dots data
    as the progress grid's mission table, `design_steps_for_attempts`, just
    one row per run instead of one row per student."""
    user = await db.get(User, user_id)
    if user is None or not ({"student", "observer"} & set(user.role_values)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    return await student_design_runs(db, user_id=user_id)


@router.get("/students/{user_id}/quiz-breakdown", response_model=CohortQuizTopicBreakdownOut)
async def student_quiz_breakdown(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Strengths/weaknesses by topic, summed live across every submitted
    cohort-quiz attempt this student has — see
    `services/lms/cohort_quiz.py::get_student_topic_breakdown`. Never
    cached, same posture as instructor_assessment's own performance read."""
    user = await db.get(User, user_id)
    if user is None or not ({"student", "observer"} & set(user.role_values)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    breakdown = await cohort_quiz_service.get_student_topic_breakdown(db, user_id)
    return CohortQuizTopicBreakdownOut(topic_breakdown=breakdown)


# ── progress grid (7B-1, Missions Phase 2B) ─────────────────────────────────
# Registered before /courses/{course_id} would matter if it shared a path
# segment — it doesn't ('progress-grid' is its own static prefix) — but kept
# up here, next to the other cross-cutting views, rather than buried among
# course CRUD.

@router.get("/progress-grid", response_model=ProgressGridOut)
async def progress_grid(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Every active student in one cohort x every course in its curriculum x
    every mission any of them has attempted. Scoped to one cohort at a time
    — see `services/lms/admin_progress.py` for why there's no
    platform-wide variant."""
    grid = await cohort_progress_grid(db, cohort_id=cohort_id)
    if grid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return grid


@router.get("/progress/courses", response_model=CourseProgressAllOut)
async def course_progress(
    course_id: uuid.UUID,
    cohort_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Every actively-enrolled student in one course, all-students by
    default, `cohort_id` an optional narrowing filter (2026-08-12) —
    the simple table the operator asked for, separate from the cohort-first
    combined grid above."""
    result = await course_progress_all(db, course_id=course_id, cohort_id=cohort_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    return result


@router.get("/progress/missions/{mission_id}", response_model=MissionProgressAllOut)
async def mission_progress(
    mission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Every student who has attempted one mission, across every cohort
    (2026-08-12) — click a mission, see everyone on it."""
    result = await mission_progress_all(db, mission_id=mission_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    return result


@router.get("/progress/courses-overview", response_model=list[CourseOverviewRowOut])
async def courses_progress_overview(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Every course with enrolled/completed counts (2026-08-14) — the landing
    list for the progress page's Courses tab, so picking a course doesn't
    start from a blind dropdown."""
    return await courses_overview(db)


@router.get("/progress/missions-overview", response_model=list[MissionOverviewRowOut])
async def missions_progress_overview(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Every mission with attempted/passed counts (2026-08-14) — the landing
    list for the progress page's Missions tab."""
    return await missions_overview(db)


# ── unified prerequisites (7B-2) ────────────────────────────────────────────
# One authoring surface for both item kinds — a course's prerequisites and a
# mission's prerequisites are edges in the same `prerequisites` table now
# (D2), so this lives here rather than duplicated under
# routers/missions/admin.py. Neither kind had an admin CRUD path before
# 7B-2 either; `mission_prerequisites` rows were only ever seeded directly.

async def _prerequisite_edge_out(db: AsyncSession, edge) -> PrerequisiteEdgeOut:
    return PrerequisiteEdgeOut(
        item_type=edge.item_type, item_id=edge.item_id,
        requires_type=edge.requires_type, requires_id=edge.requires_id,
        requires_title=await curriculum_service.item_title(
            db, item_type=edge.requires_type, item_id=edge.requires_id,
        ),
    )


@router.get("/prerequisites", response_model=list[PrerequisiteEdgeOut])
async def list_prerequisites(
    item_type: Literal["course", "mission"], item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    edges = await curriculum_service.prerequisites_of(db, item_type=item_type, item_id=item_id)
    return [await _prerequisite_edge_out(db, e) for e in edges]


@router.post("/prerequisites", response_model=PrerequisiteEdgeOut, status_code=status.HTTP_201_CREATED)
async def add_prerequisite(
    body: PrerequisiteEdgeIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    if body.item_type == "course":
        course = await db.get(Course, body.item_id)
        if course:
            await check_course_access(db, current, course)
    edge = await curriculum_service.add_prerequisite(
        db, item_type=body.item_type, item_id=body.item_id,
        requires_type=body.requires_type, requires_id=body.requires_id,
    )
    await db.commit()
    return await _prerequisite_edge_out(db, edge)


@router.delete("/prerequisites", status_code=status.HTTP_204_NO_CONTENT)
async def remove_prerequisite(
    item_type: Literal["course", "mission"], item_id: uuid.UUID,
    requires_type: Literal["course", "mission"], requires_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    if item_type == "course":
        course = await db.get(Course, item_id)
        if course:
            await check_course_access(db, current, course)
    await curriculum_service.remove_prerequisite(
        db, item_type=item_type, item_id=item_id, requires_type=requires_type, requires_id=requires_id,
    )
    await db.commit()


# ── courses ──────────────────────────────────────────────────────────────────

async def _check_instructor(db: AsyncSession, instructor_id: uuid.UUID | None) -> None:
    if instructor_id is None:
        return
    if await db.get(User, instructor_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Instructor not found")


class CourseVideoBackendOut(BaseModel):
    course_id: uuid.UUID
    title: str
    r2: int
    vps: int


# Registered before "/courses/{course_id}" (below) — FastAPI matches routes
# in registration order, and a path-param route registered first would
# swallow this literal path as course_id="video-backend-status" (a 422, not
# a 404, and this endpoint would never be reached).
@router.get("/courses/video-backend-status", response_model=list[CourseVideoBackendOut])
async def get_courses_video_backend_status(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """One row per course that has at least one module_item video, with a
    count of how many of its videos are on r2 vs. still on the VPS. A course
    with zero videos is omitted rather than shown as 0/0 — nothing to
    migrate there."""
    rows = (await db.execute(
        select(Course.id, Course.title, Video.storage_backend, func.count(Video.id))
        .join(CourseModule, CourseModule.course_id == Course.id)
        .join(ModuleItem, ModuleItem.module_id == CourseModule.id)
        .join(Video, (Video.owner_id == ModuleItem.id) & (Video.owner_type == "module_item"))
        .group_by(Course.id, Course.title, Video.storage_backend)
    )).all()

    counts: dict[uuid.UUID, dict[str, object]] = {}
    for course_id, title, backend, n in rows:
        entry = counts.setdefault(course_id, {"title": title, "r2": 0, "vps": 0})
        entry["r2" if backend == "r2" else "vps"] += n

    return [
        CourseVideoBackendOut(course_id=course_id, title=entry["title"], r2=entry["r2"], vps=entry["vps"])
        for course_id, entry in counts.items()
    ]


@router.get("/courses", response_model=list[CourseAdminOut])
async def list_courses(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _, scope_all = await get_author_permissions(db, current)
    stmt = select(Course)
    if not scope_all:
        stmt = stmt.where(Course.created_by == current.id)
    rows = (await db.execute(stmt.order_by(Course.created_at.desc()))).scalars().all()
    return [await _course_admin_out(db, c, current) for c in rows]


@router.post("/courses", response_model=CourseAdminOut, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CourseCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    await _check_instructor(db, body.instructor_id)
    course = Course(id=uuid.uuid4(), created_by=current.id, **body.model_dump())
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return await _course_admin_out(db, course, current)


@router.get("/courses/{course_id}", response_model=CourseAdminOut)
async def get_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)
    return await _course_admin_out(db, course, current)


@router.patch("/courses/{course_id}", response_model=CourseAdminOut)
async def update_course(
    course_id: uuid.UUID,
    body: CourseUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)
    changes = body.model_dump(exclude_unset=True)
    if "instructor_id" in changes:
        await _check_instructor(db, changes["instructor_id"])
    for field, value in changes.items():
        setattr(course, field, value)
    await db.commit()
    await db.refresh(course)
    return await _course_admin_out(db, course, current)


@router.post("/courses/{course_id}/publish", response_model=CourseAdminOut)
async def publish_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_publish_access(db, current, course)
    course.is_published = True
    await db.commit()
    await db.refresh(course)
    return await _course_admin_out(db, course, current)


@router.post("/courses/{course_id}/unpublish", response_model=CourseAdminOut)
async def unpublish_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_publish_access(db, current, course)
    course.is_published = False
    await db.commit()
    await db.refresh(course)
    return await _course_admin_out(db, course, current)



@router.post("/courses/{course_id}/submit-review")
async def submit_course_review(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)
    if course.is_published:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Course is already published")

    from app.services.notification import create_notification
    from app.services.email import send_course_review_submission_email
    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    who = current.full_name or current.email
    for admin in admins:
        await create_notification(
            db,
            user_id=admin.id,
            title="Course submitted for review",
            body=f"{who} submitted '{course.title}' for review and publishing.",
            type="course_review",
        )
        if admin.email:
            await send_course_review_submission_email(
                admin_email=admin.email,
                author_name=who,
                course_title=course.title,
                course_id=str(course.id),
            )
    await db.commit()
    return {"message": "Course submitted for review. Administrators have been notified."}




@router.post("/courses/{course_id}/image", response_model=CourseAdminOut)
async def upload_course_image(
    course_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image exceeds the 8MB limit")

    suffix = Path(file.filename or "cover.jpg").suffix or ".jpg"
    path = f"{course_id}/cover{suffix}"
    await storage.upload_to_path(COURSE_IMAGE_BUCKET, path, data, file.content_type or "image/jpeg")

    course.image_bucket = COURSE_IMAGE_BUCKET
    course.image_path = path
    await db.commit()
    await db.refresh(course)
    return await _course_admin_out(db, course, current)



# ── R2 migration visibility (2026-09) ───────────────────────────────────
# "Where does each course's video actually live right now" plus a button to
# move one course at a time — the per-video storage_backend column exists
# specifically to make this incremental, so the admin UI needs to expose it
# incrementally too, not just as a global on/off. See scripts/
# video_migrate_to_r2.py, whose --status/--reencode this mirrors as an API.

class MigrateCourseVideosOut(BaseModel):
    queued: int
    already_on_r2: int
    still_processing: int = 0


@router.post("/courses/{course_id}/videos/migrate-to-r2", response_model=MigrateCourseVideosOut)
async def migrate_course_videos_to_r2(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
    current: User = Depends(require_lms_content),
):
    """Re-encodes every not-yet-r2 video in this course onto R2, one course
    at a time — "migrate 3 courses today, the rest later" as a button
    instead of an SSH session. Deliberately does not touch `video.status` or
    `video.storage_backend` here: `run_encrypted_transcode` (via
    `enqueue_transcode`, target_backend="r2") owns that zero-downtime swap —
    an already-`ready` video keeps serving its current output for the whole
    re-encode and only swaps once the new output is verified in place."""
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)

    rows = (await db.execute(
        select(Video)
        .join(ModuleItem, ModuleItem.id == Video.owner_id)
        .join(CourseModule, CourseModule.id == ModuleItem.module_id)
        .where(
            Video.owner_type == "module_item", Video.upload_mode == "hls_encrypted",
            CourseModule.course_id == course_id,
        )
    )).scalars().all()

    # Mutually exclusive, in priority order — a still-processing row (a fresh
    # upload's own first-ever transcode) is reported as such even though a new
    # upload already defaults storage_backend="r2" at attach time
    # (_NEW_UPLOAD_BACKEND), well before that transcode ever runs. Counting it
    # in BOTH still_processing and already_on_r2 would let the three counts
    # sum to more than len(rows) and, worse, let the admin UI report "already
    # on R2 — nothing to migrate" for a course that actually has uploads still
    # in flight.
    still_processing_rows = [v for v in rows if v.status in ("pending", "processing")]
    settled_rows = [v for v in rows if v.status not in ("pending", "processing")]
    already_on_r2 = sum(1 for v in settled_rows if v.storage_backend == "r2")
    to_migrate = [v for v in settled_rows if v.storage_backend != "r2"]
    for video in to_migrate:
        await enqueue_transcode(arq_redis, video.id, target_backend="r2")

    return MigrateCourseVideosOut(
        queued=len(to_migrate), already_on_r2=already_on_r2,
        still_processing=len(still_processing_rows),
    )


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Refuses if any student has ever enrolled (LM1-5 spec). An unpublished,
    never-enrolled course cascades — nothing else references it."""
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)

    enrollment_count = await db.scalar(
        select(func.count()).select_from(Enrollment).where(Enrollment.course_id == course_id)
    )
    if enrollment_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"This course has {enrollment_count} enrollment(s) and can't be deleted. Unpublish it instead.",
        )

    # Same orphaned-row/storage-leak concern as delete_item — `Video` rows
    # have no DB-level FK to cascade off of ModuleItem, so every video-kind
    # item's row (and its storage objects) needs cleaning up explicitly
    # before the CourseModule/ModuleItem tree cascades away underneath it.
    video_item_ids = (await db.execute(
        select(ModuleItem.id)
        .join(CourseModule, ModuleItem.module_id == CourseModule.id)
        .where(CourseModule.course_id == course_id, ModuleItem.kind == "video")
    )).scalars().all()
    for item_id_ in video_item_ids:
        video = await get_video_for_owner(db, owner_type="module_item", owner_id=item_id_)
        if video is not None:
            await delete_video(db, video)

    await db.delete(course)
    await db.commit()


# ── modules ──────────────────────────────────────────────────────────────────

@router.get("/courses/{course_id}/modules", response_model=list[ModuleAdminOut])
async def list_modules(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)
    rows = (await db.execute(
        select(CourseModule).where(CourseModule.course_id == course_id).order_by(CourseModule.position)
    )).scalars().all()
    return rows


@router.post("/courses/{course_id}/modules", response_model=ModuleAdminOut, status_code=status.HTTP_201_CREATED)
async def create_module(
    course_id: uuid.UUID,
    body: ModuleCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)

    position = body.position
    if position is None:
        max_pos = await db.scalar(
            select(func.max(CourseModule.position)).where(CourseModule.course_id == course_id)
        )
        position = (max_pos or 0) + 1

    existing = (await db.execute(
        select(CourseModule.id).where(CourseModule.course_id == course_id, CourseModule.position == position)
    )).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Position {position} is already taken in this course")

    module = CourseModule(id=uuid.uuid4(), course_id=course_id, title=body.title, position=position)
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


@router.post("/courses/{course_id}/modules/reorder", response_model=list[ModuleAdminOut])
async def reorder_modules(
    course_id: uuid.UUID,
    body: ModuleReorderIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)

    modules = (await db.execute(
        select(CourseModule).where(CourseModule.course_id == course_id)
    )).scalars().all()
    by_id = {m.id: m for m in modules}
    if set(body.module_ids) != set(by_id) or len(body.module_ids) != len(by_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="module_ids must include every module in this course exactly once",
        )

    # The (course_id, position) unique constraint isn't deferrable, so a direct
    # swap can collide mid-transaction — offset to negative positions first,
    # then assign the final 1..N order.
    for offset, module_id in enumerate(body.module_ids, start=1):
        by_id[module_id].position = -offset
    await db.flush()
    for position, module_id in enumerate(body.module_ids, start=1):
        by_id[module_id].position = position
    await db.commit()

    rows = (await db.execute(
        select(CourseModule).where(CourseModule.course_id == course_id).order_by(CourseModule.position)
    )).scalars().all()
    return rows


@router.get("/modules/{module_id}", response_model=ModuleAdminOut)
async def get_module(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """The module-detail authoring page only has `module_id` in its URL (no
    `course_id` alongside it) — it needs this to show/rename the module
    itself, not just list the items inside it."""
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    await check_module_access(db, current, module)
    return module


@router.patch("/modules/{module_id}", response_model=ModuleAdminOut)
async def update_module(
    module_id: uuid.UUID,
    body: ModuleUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    await check_module_access(db, current, module)

    changes = body.model_dump(exclude_unset=True)
    if "position" in changes and changes["position"] != module.position:
        existing = (await db.execute(
            select(CourseModule.id).where(
                CourseModule.course_id == module.course_id, CourseModule.position == changes["position"]
            )
        )).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Position already taken in this course")

    for field, value in changes.items():
        setattr(module, field, value)
    await db.commit()
    await db.refresh(module)
    return module


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    await check_module_access(db, current, module)
    await db.delete(module)
    await db.commit()


# ── items ────────────────────────────────────────────────────────────────────

async def _item_admin_out(db: AsyncSession, item: ModuleItem) -> ItemAdminOut:
    """Video items store `content = {}` on the row — the real state (has the
    upload finished transcoding, is it watchable yet) lives on the standardized
    `Video` row (owner_type="module_item"), written asynchronously by the ARQ
    worker. Every item-returning admin endpoint goes through this so the
    authoring UI can show it instead of leaving the author to guess whether
    an upload actually finished."""
    content = dict(item.content)
    if item.kind == "video":
        video = await get_video_for_owner(db, owner_type="module_item", owner_id=item.id)
        content = {
            "transcode_status": video.status if video else None,
            "transcode_error": video.status_error if video else None,
            "duration_seconds": video.duration_seconds if video else None,
            "video_id": str(video.id) if video else None,
        }
    return ItemAdminOut(
        id=item.id, module_id=item.module_id, kind=item.kind, title=item.title,
        is_required=item.is_required, position=item.position, content=content,
    )


@router.get("/modules/{module_id}/items", response_model=list[ItemAdminOut])
async def list_items(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    await check_module_access(db, current, module)
    rows = (await db.execute(
        select(ModuleItem).where(ModuleItem.module_id == module_id).order_by(ModuleItem.position)
    )).scalars().all()
    return [await _item_admin_out(db, item) for item in rows]


@router.post("/modules/{module_id}/items", response_model=ItemAdminOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    module_id: uuid.UUID,
    body: ItemCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    await check_module_access(db, current, module)

    content = _validated_content(kind=body.kind, content=body.content)

    position = body.position
    if position is None:
        max_pos = await db.scalar(
            select(func.max(ModuleItem.position)).where(ModuleItem.module_id == module_id)
        )
        position = (max_pos or 0) + 1

    existing = (await db.execute(
        select(ModuleItem.id).where(ModuleItem.module_id == module_id, ModuleItem.position == position)
    )).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Position {position} is already taken in this module")

    item = ModuleItem(
        id=uuid.uuid4(), module_id=module_id, position=position, kind=body.kind,
        is_required=body.is_required, title=body.title, content=content,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return await _item_admin_out(db, item)


@router.post("/modules/{module_id}/items/reorder", response_model=list[ItemAdminOut])
async def reorder_items(
    module_id: uuid.UUID,
    body: ItemReorderIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    await check_module_access(db, current, module)

    items = (await db.execute(
        select(ModuleItem).where(ModuleItem.module_id == module_id)
    )).scalars().all()
    by_id = {i.id: i for i in items}
    if set(body.item_ids) != set(by_id) or len(body.item_ids) != len(by_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="item_ids must include every item in this module exactly once",
        )

    for offset, item_id in enumerate(body.item_ids, start=1):
        by_id[item_id].position = -offset
    await db.flush()
    for position, item_id in enumerate(body.item_ids, start=1):
        by_id[item_id].position = position
    await db.commit()

    rows = (await db.execute(
        select(ModuleItem).where(ModuleItem.module_id == module_id).order_by(ModuleItem.position)
    )).scalars().all()
    return [await _item_admin_out(db, item) for item in rows]


@router.patch("/items/{item_id}", response_model=ItemAdminOut)
async def update_item(
    item_id: uuid.UUID,
    body: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    item = await db.get(ModuleItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    await check_item_access(db, current, item)

    changes = body.model_dump(exclude_unset=True)
    if "content" in changes:
        changes["content"] = _validated_content(kind=item.kind, content=changes["content"])
    if "position" in changes and changes["position"] != item.position:
        existing = (await db.execute(
            select(ModuleItem.id).where(
                ModuleItem.module_id == item.module_id, ModuleItem.position == changes["position"]
            )
        )).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Position already taken in this module")

    for field, value in changes.items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return await _item_admin_out(db, item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    item = await db.get(ModuleItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    await check_item_access(db, current, item)
    # `Video.owner_id` carries no DB-level FK (service-layer-enforced, like
    # every other owner_type/owner_id pair) — unlike the old ModuleVideo's
    # item_id FK (ON DELETE CASCADE), deleting the item alone would leave an
    # orphaned Video row and its storage objects behind.
    if item.kind == "video":
        video = await get_video_for_owner(db, owner_type="module_item", owner_id=item.id)
        if video is not None:
            await delete_video(db, video)
    await db.delete(item)
    await db.commit()


# ── attachments (PDF reader, 2026-08-09) ─────────────────────────────────────
# Same two-step shape as video (create the empty item, then upload the file),
# but synchronous — a PDF has no transcode step, so the file reference alone
# (bucket/path/filename/size_bytes) is the whole story, written straight into
# `content` with no separate state table.

@router.post("/items/{item_id}/attachment", response_model=ItemAdminOut)
async def upload_attachment(
    item_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    item = await db.get(ModuleItem, item_id)
    if item is None or item.kind != "attachment":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment item not found")
    await check_item_access(db, current, item)

    if file.content_type != "application/pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF exceeds the 25MB limit")

    filename = Path(file.filename or "document.pdf").name
    path = f"{item_id}/{filename}"
    await storage.upload_to_path(ATTACHMENT_BUCKET, path, data, "application/pdf")

    item.content = {
        "bucket": ATTACHMENT_BUCKET, "path": path, "filename": filename, "size_bytes": len(data),
    }
    await db.commit()
    await db.refresh(item)
    return await _item_admin_out(db, item)


@router.get("/items/{item_id}/attachment/url", response_model=AttachmentUrlOut)
async def get_admin_attachment_url(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Generates a signed URL for author-side preview of course module attachment PDFs."""
    item = await db.get(ModuleItem, item_id)
    if item is None or item.kind != "attachment":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment item not found")
    await check_item_access(db, current, item)
    bucket = item.content.get("bucket") if item.content else None
    path = item.content.get("path") if item.content else None
    if not bucket or not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No file uploaded for this attachment yet")
    url = await storage.get_signed_url(bucket, path)
    return AttachmentUrlOut(url=url, filename=item.content.get("filename"))


@router.get("/items/{item_id}/video/playback")
async def get_admin_video_playback(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
) -> dict:
    """Author-side preview for course module videos."""
    item = await db.get(ModuleItem, item_id)
    if item is None or item.kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video item not found")
    await check_item_access(db, current, item)
    video = await get_video_for_owner(db, owner_type="module_item", owner_id=item_id)
    if video is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No video uploaded for this item yet")
    info = await get_playback_info(db, video)
    return {"url": info.get("url") or "", "video_info": info}


# ── video checkpoints (timeline notes + mid-video quizzes, 2026-08-07) ───────
# Belong to the video item they're drawn on — see the video_checkpoints
# migration docstring for why this replaced the old quiz-item +
# mid_video_at_seconds indirection.

async def _video_item(db: AsyncSession, item_id: uuid.UUID) -> ModuleItem:
    item = await db.get(ModuleItem, item_id)
    if item is None or item.kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video item not found")
    return item


def _apply_checkpoint_content_rules(
    kind: str, start_seconds: float, end_seconds: float | None, content: dict,
) -> tuple[float | None, dict]:
    validated = _validated_checkpoint_content(kind=kind, content=content)
    if kind == "note":
        if end_seconds is None or end_seconds <= start_seconds:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Notes need an end_seconds greater than start_seconds",
            )
        return end_seconds, validated
    # quiz — a single moment, not a window, whatever end_seconds was passed is ignored
    return None, validated


@router.get("/items/{video_item_id}/checkpoints", response_model=list[VideoCheckpointAdminOut])
async def list_checkpoints(
    video_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    item = await _video_item(db, video_item_id)
    await check_item_access(db, current, item)
    rows = (await db.execute(
        select(VideoCheckpoint)
        .where(VideoCheckpoint.item_id == video_item_id)
        .order_by(VideoCheckpoint.start_seconds)
    )).scalars().all()
    return rows


@router.post(
    "/items/{video_item_id}/checkpoints", response_model=VideoCheckpointAdminOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkpoint(
    video_item_id: uuid.UUID,
    body: VideoCheckpointCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    item = await _video_item(db, video_item_id)
    await check_item_access(db, current, item)
    end_seconds, content = _apply_checkpoint_content_rules(
        body.kind, body.start_seconds, body.end_seconds, body.content,
    )
    checkpoint = VideoCheckpoint(
        id=uuid.uuid4(), item_id=video_item_id, start_seconds=body.start_seconds,
        end_seconds=end_seconds, kind=body.kind, content=content,
    )
    db.add(checkpoint)
    await db.commit()
    await db.refresh(checkpoint)
    return checkpoint


@router.patch("/checkpoints/{checkpoint_id}", response_model=VideoCheckpointAdminOut)
async def update_checkpoint(
    checkpoint_id: uuid.UUID,
    body: VideoCheckpointUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    checkpoint = await db.get(VideoCheckpoint, checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
    await check_checkpoint_access(db, current, checkpoint)

    changes = body.model_dump(exclude_unset=True)
    start_seconds = changes.get("start_seconds", checkpoint.start_seconds)
    end_seconds = changes.get("end_seconds", checkpoint.end_seconds)
    content = changes.get("content", checkpoint.content)
    end_seconds, content = _apply_checkpoint_content_rules(checkpoint.kind, start_seconds, end_seconds, content)

    checkpoint.start_seconds = start_seconds
    checkpoint.end_seconds = end_seconds
    checkpoint.content = content
    await db.commit()
    await db.refresh(checkpoint)
    return checkpoint


@router.delete("/checkpoints/{checkpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checkpoint(
    checkpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    checkpoint = await db.get(VideoCheckpoint, checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
    await check_checkpoint_access(db, current, checkpoint)
    await db.delete(checkpoint)
    await db.commit()


# ── LMS Program checklist (2026-08-21 redesign) ─────────────────────────────
# Replaces the old flat program_curriculum/cohort_curriculum course list —
# see models/lms/program.py's module docstring for the full shape. A cohort
# override (below) with ANY item rows overrides its program's checklist
# outright, same nearest-wins idiom the old tables used.

async def _items_for_owner(db: AsyncSession, *, owner_type: str, owner_id: uuid.UUID) -> list[LmsProgramItem]:
    items = list((await db.execute(
        select(LmsProgramItem)
        .where(LmsProgramItem.owner_type == owner_type, LmsProgramItem.owner_id == owner_id)
        .order_by(LmsProgramItem.position)
    )).scalars().all())
    if items and [i.position for i in items] != list(range(1, len(items) + 1)):
        items = await renumber_program_items(db, owner_type=owner_type, owner_id=owner_id, commit=True)
    return items


async def program_out(db: AsyncSession, program: LmsProgram) -> LmsProgramOut:
    items = await _items_for_owner(db, owner_type="program", owner_id=program.id)
    poster_url = program.poster_template_url
    if not poster_url and program.program_id is not None:
        sp = await db.get(Program, program.program_id)
        if sp and sp.poster_template_url:
            poster_url = sp.poster_template_url
    return LmsProgramOut(
        id=program.id, program_id=program.program_id, name=program.name,
        description=program.description, certificate_required=program.certificate_required,
        poster_template_url=poster_url,
        image_url=await storage.resolve_url(program.image_bucket, program.image_path),
        items=await items_out(db, items),
    )


@router.get("/programs", response_model=list[LmsProgramOut])
async def list_lms_programs(
    program_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    """`?program_id=` is how the authoring UI finds "does this Sessions
    Program already have a checklist" without a dedicated lookup endpoint —
    there's no `UNIQUE(program_id)` violation to catch client-side since a
    fresh page load has no id to retry with."""
    query = select(LmsProgram)
    if program_id is not None:
        query = query.where(LmsProgram.program_id == program_id)
    programs = (await db.execute(query.order_by(LmsProgram.name))).scalars().all()
    return [await program_out(db, p) for p in programs]


@router.post("/programs", response_model=LmsProgramOut, status_code=status.HTTP_201_CREATED)
async def create_lms_program(
    body: LmsProgramCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    if body.program_id is not None:
        program = await db.get(Program, body.program_id)
        if program is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
        dup = await db.scalar(select(LmsProgram.id).where(LmsProgram.program_id == body.program_id))
        if dup:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This program already has an LMS checklist")
    entry = LmsProgram(
        id=uuid.uuid4(), program_id=body.program_id, name=body.name,
        description=body.description, certificate_required=body.certificate_required,
        poster_template_url=body.poster_template_url,
    )
    if body.poster_template_url and body.program_id is not None:
        sp = await db.get(Program, body.program_id)
        if sp:
            sp.poster_template_url = body.poster_template_url
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return await program_out(db, entry)


@router.get("/programs/{lms_program_id}", response_model=LmsProgramOut)
async def get_lms_program(
    lms_program_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    entry = await db.get(LmsProgram, lms_program_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LMS Program not found")
    return await program_out(db, entry)


@router.patch("/programs/{lms_program_id}", response_model=LmsProgramOut)
async def update_lms_program(
    lms_program_id: uuid.UUID, body: LmsProgramUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    entry = await db.get(LmsProgram, lms_program_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LMS Program not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    if "poster_template_url" in body.model_dump(exclude_unset=True) and entry.program_id is not None:
        sp = await db.get(Program, entry.program_id)
        if sp:
            sp.poster_template_url = body.poster_template_url
    await db.commit()
    await db.refresh(entry)
    return await program_out(db, entry)


@router.delete("/programs/{lms_program_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lms_program(
    lms_program_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    entry = await db.get(LmsProgram, lms_program_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LMS Program not found")
    await db.delete(entry)
    await db.commit()


@router.post("/programs/{lms_program_id}/image", response_model=LmsProgramOut)
async def upload_lms_program_image(
    lms_program_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    program = await db.get(LmsProgram, lms_program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LMS Program not found")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image exceeds the 8MB limit")

    suffix = Path(file.filename or "cover.jpg").suffix or ".jpg"
    image_path = f"{lms_program_id}/cover{suffix}"
    await storage.upload_to_path(PROGRAM_IMAGE_BUCKET, image_path, data, file.content_type or "image/jpeg")

    program.image_bucket = PROGRAM_IMAGE_BUCKET
    program.image_path = image_path
    await db.commit()
    await db.refresh(program)
    return await program_out(db, program)


@router.post("/programs/{lms_program_id}/items", response_model=LmsProgramItemOut, status_code=status.HTTP_201_CREATED)
async def add_lms_program_item(
    lms_program_id: uuid.UUID, body: LmsProgramItemIn,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    program = await db.get(LmsProgram, lms_program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LMS Program not found")
    validate_item_payload(body)
    await validate_item_refs(db, body)
    await check_item_conflicts(db, owner_type="program", owner_id=program.id, body=body)
    position = body.position or await next_position(db, owner_type="program", owner_id=program.id)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=program.id, position=position,
        **body.model_dump(exclude={"position"}),
    )
    db.add(item)
    await db.flush()
    await sync_program_assignments(db, lms_program_id=program.id)
    await db.commit()
    await db.refresh(item)
    return await item_out(db, item)


@router.patch("/programs/{lms_program_id}/items/{item_id}", response_model=LmsProgramItemOut)
async def update_lms_program_item(
    lms_program_id: uuid.UUID, item_id: uuid.UUID, body: LmsProgramItemIn,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    item = (await db.execute(
        select(LmsProgramItem).where(
            LmsProgramItem.id == item_id, LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == lms_program_id,
        )
    )).scalars().first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    guard_locked_submission_scope(item, body)
    validate_item_payload(body)
    await validate_item_refs(db, body, require_active_quiz=False)
    await check_item_conflicts(db, owner_type="program", owner_id=lms_program_id, body=body, exclude_item_id=item.id)
    for field, value in body.model_dump(exclude={"position"}).items():
        setattr(item, field, value)
    if body.position is not None:
        item.position = body.position
    await db.commit()
    await db.refresh(item)
    return await item_out(db, item)


@router.delete("/programs/{lms_program_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lms_program_item(
    lms_program_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    item = (await db.execute(
        select(LmsProgramItem).where(
            LmsProgramItem.id == item_id, LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == lms_program_id,
        )
    )).scalars().first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    if item.pdf_path:
        await storage.delete_file(PROGRAM_ITEM_PDF_BUCKET, item.pdf_path)
    await db.delete(item)
    await db.flush()
    await renumber_program_items(db, owner_type="program", owner_id=lms_program_id)
    await db.commit()


# ── pdf items (2026-08-31) — same two-step create-then-upload shape as a
# module `attachment` item: the item itself (title/description/etc.) is
# created through the generic item endpoints above like any other type,
# then the file is attached here, flat by item_id since it's the same
# LmsProgramItem row regardless of whether it's program- or
# cohort-override-owned. ────────────────────────────────────────────────────

@router.post("/items/{item_id}/pdf", response_model=LmsProgramItemOut)
async def upload_program_item_pdf(
    item_id: uuid.UUID, file: UploadFile,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    # A pdf-type item's own content is a PDF; any other item type can
    # instead carry a `pdf` guideline (the Roadmap board's "view the
    # guideline" step) — either way it's the same file, same pdf_path.
    item = await db.get(LmsProgramItem, item_id)
    if item is None or (item.item_type != "pdf" and item.guideline_kind != "pdf"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="PDF item not found")

    if file.content_type != "application/pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF exceeds the 25MB limit")

    if item.pdf_path:
        await storage.delete_file(PROGRAM_ITEM_PDF_BUCKET, item.pdf_path)
    filename = Path(file.filename or "document.pdf").name
    path = f"program-items/{item_id}/{filename}"
    item.pdf_path = await storage.upload_to_path(PROGRAM_ITEM_PDF_BUCKET, path, data, "application/pdf")
    await db.commit()
    await db.refresh(item)
    return await item_out(db, item)


@router.delete("/items/{item_id}/pdf", response_model=LmsProgramItemOut)
async def delete_program_item_pdf(
    item_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    item = await db.get(LmsProgramItem, item_id)
    if item is None or (item.item_type != "pdf" and item.guideline_kind != "pdf"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="PDF item not found")
    if item.pdf_path:
        await storage.delete_file(PROGRAM_ITEM_PDF_BUCKET, item.pdf_path)
        item.pdf_path = None
        await db.commit()
        await db.refresh(item)
    return await item_out(db, item)


@router.get("/items/{item_id}/pdf-url")
async def get_program_item_pdf_url(
    item_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
) -> dict[str, str]:
    """Authoring-side preview — same resolve-fresh posture as the student
    endpoint (routers/lms/student.py::program_item_pdf_url)."""
    item = await db.get(LmsProgramItem, item_id)
    if item is None or (item.item_type != "pdf" and item.guideline_kind != "pdf") or not item.pdf_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No PDF uploaded for this item yet")
    url = await storage.get_signed_url(PROGRAM_ITEM_PDF_BUCKET, item.pdf_path)
    return {"url": url}


# ── A `video` guideline: link (any item type) or upload (2026-09) ──────────
# Same two-step create-item-then-attach-video shape as the PDF endpoints
# above, through the standardized video service instead of a bespoke path —
# this is the actual "attach a real uploaded video anywhere" capability
# closing (previously link-only). Reuses the platform-wide 4GB upload cap
# (MAX_ATTACHMENT_BYTES, PR #41) rather than inventing a new one.

class GuidelineVideoEmbedIn(BaseModel):
    url: str


@router.post("/items/{item_id}/guideline/video/embed", response_model=LmsProgramItemOut)
async def attach_program_item_guideline_video_embed(
    item_id: uuid.UUID, body: GuidelineVideoEmbedIn,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    item = await db.get(LmsProgramItem, item_id)
    if item is None or item.guideline_kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video guideline item not found")
    try:
        await attach_embed_link(db, owner_type="program_item_guideline", owner_id=item_id, url=body.url)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return await item_out(db, item)


@router.post(
    "/items/{item_id}/guideline/video/upload", response_model=LmsProgramItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_program_item_guideline_video(
    item_id: uuid.UUID, file: UploadFile,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    item = await db.get(LmsProgramItem, item_id)
    if item is None or item.guideline_kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video guideline item not found")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Video exceeds the 4GB limit")

    # Compressed HLS, same pipeline every LMS course module video already
    # goes through — a short self-check clip is still someone's phone
    # recording, easily 4K, and "direct" never compressed anything, it only
    # ever made a raw file seekable.
    video = await attach_upload(
        db, owner_type="program_item_guideline", owner_id=item_id, file_bytes=data,
        filename=file.filename or "video", content_type=file.content_type, mode="hls_encrypted",
        created_by=current.id,
    )
    await enqueue_transcode(arq_redis, video.id)
    return await item_out(db, item)


@router.delete("/items/{item_id}/guideline/video", response_model=LmsProgramItemOut)
async def delete_program_item_guideline_video(
    item_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    item = await db.get(LmsProgramItem, item_id)
    if item is None or item.guideline_kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video guideline item not found")
    video = await get_video_for_owner(db, owner_type="program_item_guideline", owner_id=item_id)
    if video is not None:
        await delete_video(db, video)
    return await item_out(db, item)


@router.get("/items/{item_id}/guideline/video/url")
async def get_program_item_guideline_video_url(
    item_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    """Authoring-side preview for an *uploaded* video guideline — same
    resolve-fresh posture as pdf-url above. Not needed for an embed-link
    guideline: item_out already returns the real (public) URL for those.

    Finding #4: Returns video_info for all upload modes, matching student-facing
    endpoints. HLS-encrypted videos have no "url" key in playback_info, only
    video_id/status for token-gated playlist fetch."""
    item = await db.get(LmsProgramItem, item_id)
    if item is None or item.guideline_kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video guideline item not found")
    video = await get_video_for_owner(db, owner_type="program_item_guideline", owner_id=item_id)
    if video is None or video.provider != "upload":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No video uploaded for this item yet")
    info = await get_playback_info(db, video)
    return {"url": info.get("url") or "", "video_info": info}


@router.post("/programs/{lms_program_id}/items/reorder", response_model=list[LmsProgramItemOut])
async def reorder_lms_program_items(
    lms_program_id: uuid.UUID, body: LmsProgramItemReorderIn,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    program = await db.get(LmsProgram, lms_program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LMS Program not found")
    reordered = await reorder_program_items(db, owner_type="program", owner_id=program.id, item_ids=body.item_ids)
    if reordered is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="item_ids must include every item on this checklist exactly once",
        )
    return await items_out(db, reordered)


@router.get("/cohorts/{cohort_id}/program-override", response_model=LmsProgramCohortEffectiveOut)
async def get_cohort_program_override(
    cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    """Always 200s with *something* to edit — the cohort's own override
    once it has real items, else its program's checklist shown as the
    editable starting point (`is_inherited`). Only 404s when there's
    nothing at all to fork from (cohort missing, or its program has no
    checklist)."""
    resolved = await effective_cohort_program_items(db, cohort_id)
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort's program has no LMS checklist yet")
    program, items, is_inherited = resolved
    cohort = await db.get(Cohort, cohort_id)
    cohort_poster_url = cohort.poster_template_url if cohort else None
    inherited_poster_url = None
    if cohort and cohort.program_id:
        sp = await db.get(Program, cohort.program_id)
        if sp and sp.poster_template_url:
            inherited_poster_url = sp.poster_template_url
    if not inherited_poster_url and program.poster_template_url:
        inherited_poster_url = program.poster_template_url
    if not inherited_poster_url and program.program_id:
        sp2 = await db.get(Program, program.program_id)
        if sp2 and sp2.poster_template_url:
            inherited_poster_url = sp2.poster_template_url

    return LmsProgramCohortEffectiveOut(
        cohort_id=cohort_id,
        lms_program_id=program.id,
        is_inherited=is_inherited,
        items=await items_out(db, items),
        poster_template_url=cohort_poster_url,
        inherited_poster_template_url=inherited_poster_url,
    )


@router.patch("/cohorts/{cohort_id}/poster-template", response_model=LmsProgramCohortEffectiveOut)
async def update_cohort_poster_template(
    cohort_id: uuid.UUID, body: CohortPosterTemplateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    """Ops endpoint to override or clear the cohort-level poster template."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    cohort.poster_template_url = body.poster_template_url
    await db.commit()
    return await get_cohort_program_override(cohort_id, db=db, _=current)


@router.post("/cohorts/{cohort_id}/program-override/resync")
async def resync_cohort_program_assignments(
    cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    """One-off catch-up for a cohort whose checklist was edited before
    2026-08-27, or whose checklist didn't exist yet when a team advanced
    into it — both now backfill automatically going forward (see
    `sync_cohort_assignments`'s own docstring), but this catches up
    whatever already happened before either fix shipped. Safe to call
    any time; a cohort with nothing missing just reports 0."""
    if await db.get(Cohort, cohort_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    added = await sync_cohort_assignments(db, cohort_id=cohort_id)
    await db.commit()
    return {"items_added": added}


@router.post("/cohorts/{cohort_id}/try-as-observer")
async def try_as_observer(
    cohort_id: uuid.UUID,
    body: TryAsObserverIn | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Staff authoring access (2026-10, observer mode) — "Try as Observer".
    Creates (or reuses) the caller's own `mode="observer"` program assignment
    for this cohort. Optionally attaches to an observer team or creates a
    fresh observer sandbox team if requested, or proceeds without a team to
    test the pure unassigned student onboarding flow. Returns the assignment
    id and team id.

    Auth: `require_lms_content` staff (operations/facilitator/lms_author,
    admin passes) OR an instructor assigned to this cohort. Students and
    unassigned accounts 403 — external testers use an observer invite
    code via `/learn/signup` instead."""
    from app.models.lms.program import LmsProgramAssignment

    roles = set(current.role_values)
    staff = (
        "admin" in roles
        or bool({"operations", "facilitator", "lms_author"} & roles)
    )
    if not staff:
        if "instructor" not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Operation not permitted")
        from app.services.missions.cohort_access import require_cohort_access
        await require_cohort_access(db, cohort_id=cohort_id, user=current)

    if await db.get(Cohort, cohort_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    existing = await db.scalar(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == current.id, LmsProgramAssignment.cohort_id == cohort_id,
        )
    )
    if existing is not None and (getattr(existing, "mode", "participant") or "participant") != "observer":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="You already have a participant assignment in this cohort — observers need a separate account",
        )

    if "observer" not in current.role_values:
        current.roles = [*current.roles, UserRole.observer]
        await db.flush()

    assignment = await assign_lms_program(db, user_id=current.id, cohort_id=cohort_id, mode="observer")
    if assignment is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This cohort has no LMS checklist to observe yet — create one first",
        )

    assigned_team = None
    if body and body.team_action == "join" and body.team_id:
        team = await db.get(Team, body.team_id)
        if team is None or team.cohort_id != cohort_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found in this cohort")
        if not getattr(team, "is_observer", False):
            team.is_observer = True
            await db.flush()
        await join_team(db, team_id=team.id, user_id=current.id)
        await sync_team_mission_runs(db, team=team)
        assigned_team = team
    elif body and body.team_action == "create":
        existing_count = await db.scalar(
            select(func.count(Team.id)).where(Team.cohort_id == cohort_id)
        ) or 0
        name = (body.team_name or "").strip() or f"[Observer] Team {existing_count + 1}"
        team = await create_team(db, name=name, cohort_id=cohort_id, created_by=current.id, is_observer=True)
        await sync_team_mission_runs(db, team=team)
        assigned_team = team

    await db.commit()
    return {
        "assignment_id": str(assignment.id),
        "team_id": str(assigned_team.id) if assigned_team else None,
    }


@router.get("/cohorts/{cohort_id}/observer-teams", response_model=list[ObserverTeamSummaryOut])
async def list_cohort_observer_teams(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Lists observer sandbox teams for a cohort so observers can join an
    existing test team or create a new one."""
    if await db.get(Cohort, cohort_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    teams = list((await db.execute(
        select(Team).where(Team.cohort_id == cohort_id, Team.is_observer.is_(True)).order_by(Team.name)
    )).scalars().all())
    out = []
    for t in teams:
        member_ids = await team_member_ids(db, team_id=t.id)
        members = (await db.execute(select(User).where(User.id.in_(member_ids)))).scalars().all() if member_ids else []
        out.append(ObserverTeamSummaryOut(
            id=t.id,
            name=t.name,
            member_count=len(member_ids),
            member_names=[m.full_name for m in members if m and m.full_name],
            is_my_team=current.id in member_ids,
        ))
    return out


@router.post(
    "/cohorts/{cohort_id}/program-override/items", response_model=LmsProgramItemOut, status_code=status.HTTP_201_CREATED,
)
async def add_cohort_override_item(
    cohort_id: uuid.UUID, body: LmsProgramItemIn,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    """Forks the cohort's override off its program's current checklist on
    the first write (`fork_cohort_override`) — so adding one new item
    never means losing the rest of what the program already lists — then
    adds this item on top of the (now-populated) override."""
    forked = await fork_cohort_override(db, cohort_id=cohort_id)
    if forked is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This cohort's program has no LMS checklist to override yet — create one first",
        )
    override, _id_map = forked

    validate_item_payload(body)
    await validate_item_refs(db, body)
    await check_item_conflicts(db, owner_type="cohort_override", owner_id=override.id, body=body)
    position = body.position or await next_position(db, owner_type="cohort_override", owner_id=override.id)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="cohort_override", owner_id=override.id, position=position,
        **body.model_dump(exclude={"position"}),
    )
    db.add(item)
    await db.flush()
    await sync_cohort_assignments(db, cohort_id=cohort_id)
    await db.commit()
    await db.refresh(item)
    return await item_out(db, item)


@router.patch("/cohorts/{cohort_id}/program-override/items/{item_id}", response_model=LmsProgramItemOut)
async def update_cohort_override_item(
    cohort_id: uuid.UUID, item_id: uuid.UUID, body: LmsProgramItemIn,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    """`item_id` may be a not-yet-forked program item's id (the "inherited"
    list the GET above serves) — `fork_cohort_override`'s id map translates
    it to the override's own freshly-copied item on exactly the call that
    triggers the fork; every edit after that is against a real override
    item id once the frontend refetches."""
    forked = await fork_cohort_override(db, cohort_id=cohort_id)
    if forked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort has no checklist to override")
    override, id_map = forked
    resolved_item_id = id_map.get(item_id, item_id)

    item = (await db.execute(
        select(LmsProgramItem).where(
            LmsProgramItem.id == resolved_item_id,
            LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == override.id,
        )
    )).scalars().first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    guard_locked_submission_scope(item, body)
    validate_item_payload(body)
    await validate_item_refs(db, body, require_active_quiz=False)
    await check_item_conflicts(db, owner_type="cohort_override", owner_id=override.id, body=body, exclude_item_id=item.id)
    for field, value in body.model_dump(exclude={"position"}).items():
        setattr(item, field, value)
    if body.position is not None:
        item.position = body.position
    await db.commit()
    await db.refresh(item)
    return await item_out(db, item)


@router.delete("/cohorts/{cohort_id}/program-override/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cohort_override_item(
    cohort_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    """Same fork-then-translate as the update route above — "removing" an
    inherited item forks everything else in, then deletes just this one
    copy, which is exactly what "start from the program's list and edit
    it down" means for a delete."""
    forked = await fork_cohort_override(db, cohort_id=cohort_id)
    if forked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort has no checklist to override")
    override, id_map = forked
    resolved_item_id = id_map.get(item_id, item_id)

    item = (await db.execute(
        select(LmsProgramItem).where(
            LmsProgramItem.id == resolved_item_id,
            LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == override.id,
        )
    )).scalars().first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    if item.pdf_path:
        await storage.delete_file(PROGRAM_ITEM_PDF_BUCKET, item.pdf_path)
    await db.delete(item)
    await db.flush()
    await renumber_program_items(db, owner_type="cohort_override", owner_id=override.id)
    await db.commit()


@router.post("/cohorts/{cohort_id}/program-override/items/reorder", response_model=list[LmsProgramItemOut])
async def reorder_cohort_override_items(
    cohort_id: uuid.UUID, body: LmsProgramItemReorderIn,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    """Same fork-then-translate as edit/delete above — dragging an
    "inherited" list forks it first, translating every dragged id through
    the fresh id map before handing the (now real) ids to `reorder_program_items`."""
    forked = await fork_cohort_override(db, cohort_id=cohort_id)
    if forked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort has no checklist to override")
    override, id_map = forked
    resolved_ids = [id_map.get(i, i) for i in body.item_ids]
    reordered = await reorder_program_items(db, owner_type="cohort_override", owner_id=override.id, item_ids=resolved_ids)
    if reordered is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="item_ids must include every item on this checklist exactly once",
        )
    return await items_out(db, reordered)


# ── LMS Program & Cohort CubeSat Component Configuration ─────────────────

@router.get("/programs/{lms_program_id}/components", response_model=ComponentConfigOut)
async def get_lms_program_components(
    lms_program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    program = await db.get(LmsProgram, lms_program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LMS Program not found")
    return await component_config_service.build_component_config_out(db, owner_type="program", owner_id=lms_program_id)


@router.put("/programs/{lms_program_id}/components", response_model=ComponentConfigOut)
async def update_lms_program_components(
    lms_program_id: uuid.UUID,
    body: ComponentConfigIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    program = await db.get(LmsProgram, lms_program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LMS Program not found")
    await component_config_service.save_component_config(
        db,
        owner_type="program",
        owner_id=lms_program_id,
        disabled_subsystems=body.disabled_subsystems,
        disabled_tags=body.disabled_tags,
        disabled_component_ids=body.disabled_component_ids,
        user_id=current.id,
    )
    await db.commit()
    return await component_config_service.build_component_config_out(db, owner_type="program", owner_id=lms_program_id)


@router.delete("/programs/{lms_program_id}/components", response_model=ComponentConfigOut)
async def reset_lms_program_components(
    lms_program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    program = await db.get(LmsProgram, lms_program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="LMS Program not found")
    await component_config_service.reset_component_config(db, owner_type="program", owner_id=lms_program_id)
    await db.commit()
    return await component_config_service.build_component_config_out(db, owner_type="program", owner_id=lms_program_id)


@router.get("/cohorts/{cohort_id}/components", response_model=ComponentConfigOut)
async def get_cohort_components(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return await component_config_service.build_component_config_out(db, owner_type="cohort", owner_id=cohort_id)


@router.put("/cohorts/{cohort_id}/components", response_model=ComponentConfigOut)
async def update_cohort_components(
    cohort_id: uuid.UUID,
    body: ComponentConfigIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    await component_config_service.save_component_config(
        db,
        owner_type="cohort",
        owner_id=cohort_id,
        disabled_subsystems=body.disabled_subsystems,
        disabled_tags=body.disabled_tags,
        disabled_component_ids=body.disabled_component_ids,
        user_id=current.id,
    )
    await db.commit()
    return await component_config_service.build_component_config_out(db, owner_type="cohort", owner_id=cohort_id)


@router.delete("/cohorts/{cohort_id}/components", response_model=ComponentConfigOut)
async def reset_cohort_components(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    await component_config_service.reset_component_config(db, owner_type="cohort", owner_id=cohort_id)
    await db.commit()
    return await component_config_service.build_component_config_out(db, owner_type="cohort", owner_id=cohort_id)


@router.get("/cohorts/{cohort_id}/quiz-analysis")
async def cohort_quiz_analysis(
    cohort_id: uuid.UUID,
    include_observers: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Live topic strength and weakness analysis across all submitted quizzes for a cohort.

    Observer mode (2026-10): observer test attempts are excluded from the
    cohort average and topic mastery by default (`include_observers=false`)."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return await cohort_quiz_service.get_cohort_quiz_analysis(
        db, cohort_id=cohort_id, include_observers=include_observers,
    )


# ── learning paths (self-paced ordered course sequences, 2026-08-08) ───────

async def _learning_path_admin_out(db: AsyncSession, path: LearningPath, current: User | None = None) -> LearningPathAdminOut:
    can_view_audit = bool(current and any(r in ("admin", "operations") for r in current.role_values))
    created_by = path.created_by if can_view_audit else None
    created_at = path.created_at if can_view_audit else None
    created_by_name = None
    if can_view_audit and path.created_by:
        creator = await db.get(User, path.created_by)
        created_by_name = creator.full_name if creator else None
    return LearningPathAdminOut(
        id=path.id, title=path.title, description=path.description,
        is_published=path.is_published, created_by=created_by,
        created_by_name=created_by_name, created_at=created_at,
        image_url=await storage.resolve_url(path.image_bucket, path.image_path),
        access_mode=path.access_mode, price_cents=path.price_cents, currency=path.currency,
    )



@router.get("/learning-paths", response_model=list[LearningPathAdminOut])
async def list_learning_paths(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _, scope_all = await get_author_permissions(db, current)
    stmt = select(LearningPath)
    if not scope_all:
        stmt = stmt.where(LearningPath.created_by == current.id)
    rows = (await db.execute(stmt.order_by(LearningPath.created_at.desc()))).scalars().all()
    return [await _learning_path_admin_out(db, p, current) for p in rows]


@router.post("/learning-paths", response_model=LearningPathAdminOut, status_code=status.HTTP_201_CREATED)
async def create_learning_path(
    body: LearningPathCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    can_publish, _ = await get_author_permissions(db, current)
    data = body.model_dump()
    if not can_publish and data.get("is_published"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You do not have direct publishing permissions. Please create the learning path as draft.",
        )
    path = LearningPath(id=uuid.uuid4(), created_by=current.id, **data)
    db.add(path)
    await db.commit()
    await db.refresh(path)
    return await _learning_path_admin_out(db, path, current)


@router.get("/learning-paths/{path_id}", response_model=LearningPathAdminOut)
async def get_learning_path(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)
    return await _learning_path_admin_out(db, path, current)


@router.patch("/learning-paths/{path_id}", response_model=LearningPathAdminOut)
async def update_learning_path(
    path_id: uuid.UUID,
    body: LearningPathUpdate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)

    changes = body.model_dump(exclude_unset=True)
    if "is_published" in changes and changes["is_published"] != path.is_published:
        can_publish, _ = await get_author_permissions(db, current)
        if not can_publish:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="You do not have direct publishing permissions. Please contact an administrator to review and publish this learning path.",
            )

    for field, value in changes.items():
        setattr(path, field, value)
    await db.commit()
    await db.refresh(path)
    return await _learning_path_admin_out(db, path, current)


@router.post("/learning-paths/{path_id}/image", response_model=LearningPathAdminOut)
async def upload_learning_path_image(
    path_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image exceeds the 8MB limit")

    suffix = Path(file.filename or "cover.jpg").suffix or ".jpg"
    image_path = f"{path_id}/cover{suffix}"
    await storage.upload_to_path(LEARNING_PATH_IMAGE_BUCKET, image_path, data, file.content_type or "image/jpeg")

    path.image_bucket = LEARNING_PATH_IMAGE_BUCKET
    path.image_path = image_path
    await db.commit()
    await db.refresh(path)
    return await _learning_path_admin_out(db, path, current)



@router.post("/learning-paths/{path_id}/submit-review")
async def submit_learning_path_review(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)
    if path.is_published:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Learning path is already published")

    from app.services.notification import create_notification
    from app.services.email import send_learning_path_review_submission_email
    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    who = current.full_name or current.email
    for admin in admins:
        await create_notification(
            db,
            user_id=admin.id,
            title="Learning path submitted for review",
            body=f"{who} submitted '{path.title}' for review and publishing.",
            type="learning_path_review",
        )
        if admin.email:
            await send_learning_path_review_submission_email(
                admin_email=admin.email,
                author_name=who,
                path_title=path.title,
                path_id=str(path.id),
            )
    await db.commit()
    return {"message": "Learning path submitted for review. Administrators have been notified."}




@router.delete("/learning-paths/{path_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_learning_path(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """No enrollment check like `delete_course` — a path itself grants no
    access (its steps' courses do, independently), so deleting one never
    strands a student mid-course. It only removes the curated grouping."""
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)
    await db.delete(path)
    await db.commit()


@router.get("/learning-paths/{path_id}/steps", response_model=list[LearningPathStepOut])
async def list_learning_path_steps(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)
    rows = (await db.execute(
        select(LearningPathStep)
        .where(LearningPathStep.learning_path_id == path_id)
        .order_by(LearningPathStep.position)
    )).scalars().all()
    return rows


@router.post(
    "/learning-paths/{path_id}/steps",
    response_model=LearningPathStepOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_learning_path_step(
    path_id: uuid.UUID,
    body: LearningPathStepIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)
    course = await db.get(Course, body.course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all and course.created_by != current.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

    dup = (await db.execute(
        select(LearningPathStep.id).where(
            LearningPathStep.learning_path_id == path_id, LearningPathStep.course_id == body.course_id
        )
    )).first()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This course is already a step in this path")

    position = body.position
    if position is None:
        max_pos = await db.scalar(
            select(func.max(LearningPathStep.position)).where(LearningPathStep.learning_path_id == path_id)
        )
        position = (max_pos or 0) + 1
    else:
        taken = (await db.execute(
            select(LearningPathStep.id).where(
                LearningPathStep.learning_path_id == path_id, LearningPathStep.position == position
            )
        )).first()
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Position {position} is already taken in this path")

    step = LearningPathStep(id=uuid.uuid4(), learning_path_id=path_id, course_id=body.course_id, position=position)
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


@router.delete("/learning-paths/{path_id}/steps/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_learning_path_step(
    path_id: uuid.UUID,
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)

    step = (await db.execute(
        select(LearningPathStep).where(
            LearningPathStep.learning_path_id == path_id, LearningPathStep.course_id == course_id
        )
    )).scalars().first()
    if step is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Step not found")
    await db.delete(step)
    await db.commit()


# ── enrollment admin (P1-5, Phase 2 Stage 1) ─────────────────────────────────

async def enrollment_admin_out(db: AsyncSession, enrollment: Enrollment) -> EnrollmentAdminOut:
    student = await db.get(User, enrollment.user_id)
    return EnrollmentAdminOut(
        id=enrollment.id, user_id=enrollment.user_id,
        student_name=student.full_name if student else "(deleted user)",
        student_email=student.email if student else "",
        course_id=enrollment.course_id, source=enrollment.source, status=enrollment.status,
        granted_by=enrollment.granted_by, expires_at=enrollment.expires_at, created_at=enrollment.created_at,
    )


@router.get("/courses/{course_id}/roster", response_model=list[EnrollmentAdminOut])
async def course_roster(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        return []
    rows = (await db.execute(
        select(Enrollment).where(Enrollment.course_id == course_id).order_by(Enrollment.created_at.desc())
    )).scalars().all()
    return [await enrollment_admin_out(db, e) for e in rows]


@router.post(
    "/courses/{course_id}/enrollments", response_model=EnrollmentAdminOut, status_code=status.HTTP_201_CREATED,
)
async def grant_enrollment(
    course_id: uuid.UUID,
    body: EnrollmentGrantIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Put a named person into a named course from the UI (P1-5) — works
    regardless of the course's access_mode; that field only gates
    *self*-enrol (P1-4). An ops grant is always allowed."""
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Assigned access is restricted to full access authors")
    student = await db.get(User, body.user_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    enrollment = await enroll(
        db, user_id=body.user_id, course_id=course_id, source="ops", granted_by=current.id,
    )
    await db.commit()
    return await enrollment_admin_out(db, enrollment)


@router.post("/enrollments/{enrollment_id}/revoke", response_model=EnrollmentAdminOut)
async def revoke_enrollment(
    enrollment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Sets status='inactive', never deletes (P1-5) — the row, and whatever
    progress/points hang off it later, survive; enroll() reactivates it in
    place if access is ever restored."""
    enrollment = await db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    course = await db.get(Course, enrollment.course_id)
    if course is not None:
        await check_course_access(db, current, course)
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Assigned access is restricted to full access authors")
    enrollment.status = "inactive"
    await db.commit()
    return await enrollment_admin_out(db, enrollment)


@router.get("/users/{user_id}/enrollments", response_model=list[EnrollmentAdminOut])
async def student_enrollments(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Per-student view (P1-5) — every course this account has ever been
    enrolled in, active or not. The richer contact-centric panel (linked
    account, registrations, cohorts, points) is Stage 3's P3-1; this is the
    narrower building block the roster/grant UI needs today."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == user_id).order_by(Enrollment.created_at.desc())
    )).scalars().all()
    out = []
    for e in rows:
        row = await enrollment_admin_out(db, e)
        course = await db.get(Course, e.course_id)
        row.course_title = course.title if course else None
        out.append(row)
    return out


async def _resolve_bulk_grant_user_ids(db: AsyncSession, body: BulkGrantIn) -> tuple[list[uuid.UUID], int]:
    """Shared roster/role resolution for the course and learning-path bulk
    grants — one-shot iteration (§3), not a live membership rule. cohort_id:
    every contact with an active registration in that cohort who already has
    a linked LMS account (bulk-grant doesn't create accounts — see
    BulkGrantOut.skipped_no_account's docstring). role: every user holding
    that role, D2's "staff can take LMS courses too" made concrete. Returns
    (user_ids, skipped_no_account)."""
    if body.role is not None:
        user_ids = list((await db.execute(
            select(User.id).where(User.roles.any(body.role))
        )).scalars().all())
        return user_ids, 0

    contact_ids = list((await db.execute(
        select(Registration.contact_id).where(
            Registration.cohort_id == body.cohort_id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )).scalars().all())
    user_ids = list((await db.execute(
        select(User.id).where(User.contact_id.in_(contact_ids))
    )).scalars().all())
    return user_ids, len(set(contact_ids)) - len(set(user_ids))


@router.post("/courses/{course_id}/enrollments/bulk", response_model=BulkGrantOut)
async def bulk_grant_enrollment(
    course_id: uuid.UUID,
    body: BulkGrantIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await check_course_access(db, current, course)
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Assigned access is restricted to full access authors")

    user_ids, skipped_no_account = await _resolve_bulk_grant_user_ids(db, body)

    granted = already_enrolled = 0
    for user_id in user_ids:
        existing = (await db.execute(
            select(Enrollment.id).where(
                Enrollment.user_id == user_id, Enrollment.course_id == course_id, *enrollment_is_active(),
            )
        )).first()
        if existing is not None:
            already_enrolled += 1
            continue
        await enroll(db, user_id=user_id, course_id=course_id, source="ops", granted_by=current.id)
        granted += 1

    await db.commit()
    return BulkGrantOut(granted=granted, already_enrolled=already_enrolled, skipped_no_account=skipped_no_account)


async def _learning_path_step_course_ids(db: AsyncSession, path_id: uuid.UUID) -> list[uuid.UUID]:
    return list((await db.execute(
        select(LearningPathStep.course_id).where(LearningPathStep.learning_path_id == path_id)
    )).scalars().all())


@router.get("/learning-paths/{path_id}/roster", response_model=list[LearningPathRosterRowOut])
async def learning_path_roster(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """The named-individual assignment roster (2026-09-15) — courses have
    had this (`course_roster`/`grant_enrollment`) since P1-5; paths only
    had the cohort/role bulk grant. One row per user with at least one
    ops-sourced enrollment among the path's current steps, `steps_owned`
    tracking partial vs. full grants (mirrors `bulk_grant_path_enrollment`'s
    own "block only when fully owned" reading of ownership)."""
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        return []
    step_course_ids = await _learning_path_step_course_ids(db, path_id)
    if not step_course_ids:
        return []

    rows = (await db.execute(
        select(Enrollment.user_id, Enrollment.course_id).where(
            Enrollment.course_id.in_(step_course_ids), Enrollment.source == "ops", *enrollment_is_active(),
        )
    )).all()
    owned_by_user: dict[uuid.UUID, set[uuid.UUID]] = {}
    for user_id, course_id in rows:
        owned_by_user.setdefault(user_id, set()).add(course_id)

    users = {
        u.id: u for u in
        (await db.execute(select(User).where(User.id.in_(owned_by_user.keys())))).scalars().all()
    }
    out = []
    for user_id, owned in owned_by_user.items():
        user = users.get(user_id)
        out.append(LearningPathRosterRowOut(
            user_id=user_id,
            student_name=user.full_name if user else "(deleted user)",
            student_email=user.email if user else "",
            status="active",
            steps_owned=len(owned), steps_total=len(step_course_ids),
        ))
    return out


@router.post(
    "/learning-paths/{path_id}/enrollments", response_model=LearningPathRosterRowOut,
    status_code=status.HTTP_201_CREATED,
)
async def grant_path_enrollment(
    path_id: uuid.UUID,
    body: EnrollmentGrantIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Put a named person into every one of a path's current courses at
    once (2026-09-15) — the path equivalent of `grant_enrollment`, so a
    single staff account can be handed a whole path the same way it can
    already be handed one course. Re-granting an already-fully-owned path
    is a no-op per step (`enroll` reactivates/dedupes on its own)."""
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Assigned access is restricted to full access authors")
    student = await db.get(User, body.user_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    step_course_ids = await _learning_path_step_course_ids(db, path_id)
    if not step_course_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This path has no courses yet")

    for course_id in step_course_ids:
        await enroll(db, user_id=body.user_id, course_id=course_id, source="ops", granted_by=current.id)
    await db.commit()

    return LearningPathRosterRowOut(
        user_id=student.id, student_name=student.full_name, student_email=student.email,
        status="active", steps_owned=len(step_course_ids), steps_total=len(step_course_ids),
    )


@router.post("/learning-paths/{path_id}/enrollments/{user_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_path_enrollment(
    path_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Deactivates every ops-sourced enrollment this user holds among the
    path's current steps — the path has no row of its own to flip, so
    revoke fans out across its courses the same way grant does. 404s if
    nothing matched (never granted, or a stale/wrong user_id) rather than
    silently no-op'ing — same "revoke a specific real thing, else 404"
    posture the course version gets from `db.get(Enrollment, ...)`."""
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Assigned access is restricted to full access authors")
    step_course_ids = await _learning_path_step_course_ids(db, path_id)
    rows = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user_id, Enrollment.course_id.in_(step_course_ids),
            Enrollment.source == "ops", *enrollment_is_active(),
        )
    )).scalars().all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No path enrollment found for this user")
    for enrollment in rows:
        enrollment.status = "inactive"
    await db.commit()


@router.post("/learning-paths/{path_id}/enrollments/bulk", response_model=BulkGrantOut)
async def bulk_grant_path_enrollment(
    path_id: uuid.UUID,
    body: BulkGrantIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """Same one-shot cohort/role grant as the course version, but enrols
    every one of the path's current steps at once — mirrors what buying the
    bundle itself grants (`services/lms/checkout.py::fulfill`), just without
    Stripe. `already_enrolled` counts a user only once even if they already
    held some (not all) of the steps, matching how the bundle purchase's own
    "block only when fully owned" rule reads ownership."""
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await check_learning_path_access(db, current, path)
    _, scope_all = await get_author_permissions(db, current)
    if not scope_all:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Assigned access is restricted to full access authors")
    step_course_ids = await _learning_path_step_course_ids(db, path_id)
    if not step_course_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This path has no courses yet")

    user_ids, skipped_no_account = await _resolve_bulk_grant_user_ids(db, body)

    granted = already_enrolled = 0
    for user_id in user_ids:
        owned = (await db.execute(
            select(Enrollment.course_id).where(
                Enrollment.user_id == user_id, Enrollment.course_id.in_(step_course_ids), *enrollment_is_active(),
            )
        )).scalars().all()
        if set(owned) >= set(step_course_ids):
            already_enrolled += 1
            continue
        for course_id in step_course_ids:
            await enroll(db, user_id=user_id, course_id=course_id, source="ops", granted_by=current.id)
        granted += 1

    await db.commit()
    return BulkGrantOut(granted=granted, already_enrolled=already_enrolled, skipped_no_account=skipped_no_account)
