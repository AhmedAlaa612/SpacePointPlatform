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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_lms_content
from app.db.session import get_db
from app.models.lms import (
    CohortCurriculum, Course, CourseModule, Enrollment, ModuleItem, ModuleVideo, ProgramCurriculum, VideoCheckpoint,
)
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.instructors.invitation_code import InvitationCode
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
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
    CohortCurriculumEntryOut,
    CourseAdminOut,
    CourseCreate,
    CourseUpdate,
    CurriculumEntryIn,
    CurriculumEntryOut,
    EnrollmentAdminOut,
    EnrollmentGrantIn,
    InstructorOptionOut,
    InviteCodeCreate,
    InviteCodeOut,
    InviteCodeUpdate,
    ItemAdminOut,
    ItemCreate,
    ItemReorderIn,
    ItemUpdate,
    LearningPathAdminOut,
    LearningPathCreate,
    LearningPathStepIn,
    LearningPathStepOut,
    LearningPathUpdate,
    ModuleAdminOut,
    ModuleCreate,
    ModuleReorderIn,
    ModuleUpdate,
    ReconcileEnrollmentsOut,
    StaffOptionOut,
    StudentProfileOut,
    StudentProgramOut,
    StudentSummaryOut,
    VideoCheckpointAdminOut,
    VideoCheckpointCreate,
    VideoCheckpointUpdate,
)
from app.schemas.curriculum import PrerequisiteEdgeIn, PrerequisiteEdgeOut
from app.schemas.lms_progress_grid import (
    CourseOverviewRowOut, CourseProgressAllOut, MissionOverviewRowOut, MissionProgressAllOut, ProgressGridOut,
)
from app.services import curriculum as curriculum_service
from app.services import storage
from app.services.lms import enroll, enrollment_is_active
from app.services.lms.admin_progress import (
    cohort_progress_grid, course_progress_all, courses_overview, mission_progress_all, missions_overview,
)
from app.services.lms.curriculum import reconcile_cohort_enrollments, reconcile_cohorts_inheriting_program
from app.services.lms.my_programs import my_programs
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES

router = APIRouter(prefix="/lms/admin", tags=["lms-admin"])

COURSE_IMAGE_BUCKET = "lms-course-images"
LEARNING_PATH_IMAGE_BUCKET = "lms-learning-path-images"
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB — a cover image, not a dataset
ATTACHMENT_BUCKET = "lms-attachments"
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # 25MB — a reading, not a video


async def _course_admin_out(db: AsyncSession, course: Course) -> CourseAdminOut:
    """`CourseAdminOut` carries two derived fields (`image_url`,
    `instructor_name`) that aren't real columns on `Course` — Pydantic's
    `from_attributes` can't resolve those from the bare ORM object, so every
    course-returning endpoint goes through this instead of `return course`."""
    image_url = await storage.resolve_url(course.image_bucket, course.image_path)
    instructor_name = None
    if course.instructor_id:
        instructor = await db.get(User, course.instructor_id)
        instructor_name = instructor.full_name if instructor else None
    return CourseAdminOut(
        id=course.id, title=course.title, description=course.description, kind=course.kind,
        is_published=course.is_published, created_by=course.created_by, created_at=course.created_at,
        image_url=image_url, outcomes=course.outcomes or [], level=course.level, track=course.track,
        instructor_id=course.instructor_id, instructor_name=instructor_name,
        instructor_title=course.instructor_title,
        access_mode=course.access_mode, access_days=course.access_days,
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.errors())
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
    _: User = Depends(require_lms_content),
):
    """Named-individual search for the course/mission assignment picker —
    any staff account (`student` excluded; that role self-enrols or is
    bulk-granted by cohort, never picked by name here). `role` narrows to one
    held role, `q` is a case-insensitive substring match on name or email.
    Capped at 25 rows — a picker, not a roster export."""
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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Name/email substring search over student accounts, capped at 50 rows
    — the list view backing the student-management page.

    `invite_code` filters to one batch (2026-08-13). The literal string
    `none` selects students with no code at all — the ones who signed up
    before the gate existed; without it they'd be unreachable through the
    filter, since "no code" isn't a code you can type.
    """
    stmt = select(User).where(User.roles.any("student"))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    if invite_code:
        if invite_code.strip().lower() == "none":
            stmt = stmt.where(User.invitation_code_used.is_(None))
        else:
            stmt = stmt.where(User.invitation_code_used == invite_code.strip().upper())
    rows = (await db.execute(stmt.order_by(User.full_name).limit(50))).scalars().all()

    labels = dict((await db.execute(
        select(InvitationCode.code, InvitationCode.label).where(InvitationCode.kind == "student")
    )).all())

    # School and grade live on the linked spine Contact, not on `users` —
    # resolved in two batched queries rather than one pair per row.
    contact_ids = [u.contact_id for u in rows if u.contact_id]
    contacts = {
        c.id: c for c in (
            (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
            if contact_ids else []
        )
    }
    org_ids = {c.organization_id for c in contacts.values() if c.organization_id}
    orgs = {
        o.id: o for o in (
            (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars().all()
            if org_ids else []
        )
    }

    out = []
    for u in rows:
        contact = contacts.get(u.contact_id) if u.contact_id else None
        org = orgs.get(contact.organization_id) if contact and contact.organization_id else None
        out.append(StudentSummaryOut(
            id=u.id, full_name=u.full_name, nickname=u.nickname, email=u.email,
            invite_code=u.invitation_code_used,
            invite_label=labels.get(u.invitation_code_used) if u.invitation_code_used else None,
            school_name=org.name_latin if org else None,
            grade=contact.grade if contact else None,
            status=u.status,
            created_at=u.created_at,
        ))
    return out


# ── student invite codes (2026-08-13) ───────────────────────────────────────
# Ops-managed, distinct from the admin-only instructor codes at
# /instructors/admin/invitations — same table, split by `kind` so a school
# batch code can't open the instructor application pipeline.

async def _invite_code_out(db: AsyncSession, row: InvitationCode) -> InviteCodeOut:
    signups = await db.scalar(
        select(func.count()).select_from(User).where(User.invitation_code_used == row.code)
    )
    return InviteCodeOut(
        id=row.id, code=row.code, label=row.label, is_active=row.is_active,
        max_uses=row.max_uses, used_count=row.used_count, expires_at=row.expires_at,
        created_at=row.created_at, signups=signups or 0,
    )


@router.get("/invite-codes", response_model=list[InviteCodeOut])
async def list_invite_codes(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    rows = (await db.execute(
        select(InvitationCode).where(InvitationCode.kind == "student")
        .order_by(InvitationCode.created_at.desc())
    )).scalars().all()
    return [await _invite_code_out(db, r) for r in rows]


@router.post("/invite-codes", response_model=InviteCodeOut, status_code=status.HTTP_201_CREATED)
async def create_invite_code(
    body: InviteCodeCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
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
        id=uuid.uuid4(), code=code, kind="student", label=body.label,
        max_uses=body.max_uses, is_active=body.is_active, expires_at=body.expires_at,
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
    _: User = Depends(require_lms_content),
):
    row = await db.get(InvitationCode, code_id)
    if row is None or row.kind != "student":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite code not found")

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
    _: User = Depends(require_lms_content),
):
    """Refuses once anyone has signed up on it — the code is the only record
    of which batch those students belong to (users.invitation_code_used is a
    plain string, not an FK, so deleting the row would silently orphan them
    from the filter rather than cascade). Deactivate it instead."""
    row = await db.get(InvitationCode, code_id)
    if row is None or row.kind != "student":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite code not found")
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
    if user is None or "student" not in user.role_values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    programs = await my_programs(db, user=user)
    return StudentProfileOut(
        id=user.id, full_name=user.full_name, nickname=user.nickname, avatar=user.avatar,
        email=user.email, programs=[StudentProgramOut(**p) for p in programs],
    )


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
    _: User = Depends(require_lms_content),
):
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
    _: User = Depends(require_lms_content),
):
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


@router.get("/courses", response_model=list[CourseAdminOut])
async def list_courses(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    rows = (await db.execute(select(Course).order_by(Course.created_at.desc()))).scalars().all()
    return [await _course_admin_out(db, c) for c in rows]


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
    return await _course_admin_out(db, course)


@router.get("/courses/{course_id}", response_model=CourseAdminOut)
async def get_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    return await _course_admin_out(db, course)


@router.patch("/courses/{course_id}", response_model=CourseAdminOut)
async def update_course(
    course_id: uuid.UUID,
    body: CourseUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    changes = body.model_dump(exclude_unset=True)
    if "instructor_id" in changes:
        await _check_instructor(db, changes["instructor_id"])
    for field, value in changes.items():
        setattr(course, field, value)
    await db.commit()
    await db.refresh(course)
    return await _course_admin_out(db, course)


@router.post("/courses/{course_id}/publish", response_model=CourseAdminOut)
async def publish_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    course.is_published = True
    await db.commit()
    await db.refresh(course)
    return await _course_admin_out(db, course)


@router.post("/courses/{course_id}/unpublish", response_model=CourseAdminOut)
async def unpublish_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    course.is_published = False
    await db.commit()
    await db.refresh(course)
    return await _course_admin_out(db, course)


@router.post("/courses/{course_id}/image", response_model=CourseAdminOut)
async def upload_course_image(
    course_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

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
    return await _course_admin_out(db, course)


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Refuses if any student has ever enrolled (LM1-5 spec). An unpublished,
    never-enrolled course cascades — nothing else references it."""
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

    enrollment_count = await db.scalar(
        select(func.count()).select_from(Enrollment).where(Enrollment.course_id == course_id)
    )
    if enrollment_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"This course has {enrollment_count} enrollment(s) and can't be deleted. Unpublish it instead.",
        )

    await db.delete(course)
    await db.commit()


# ── modules ──────────────────────────────────────────────────────────────────

@router.get("/courses/{course_id}/modules", response_model=list[ModuleAdminOut])
async def list_modules(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    rows = (await db.execute(
        select(CourseModule).where(CourseModule.course_id == course_id).order_by(CourseModule.position)
    )).scalars().all()
    return rows


@router.post("/courses/{course_id}/modules", response_model=ModuleAdminOut, status_code=status.HTTP_201_CREATED)
async def create_module(
    course_id: uuid.UUID,
    body: ModuleCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

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
    _: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

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
    _: User = Depends(require_lms_content),
):
    """The module-detail authoring page only has `module_id` in its URL (no
    `course_id` alongside it) — it needs this to show/rename the module
    itself, not just list the items inside it."""
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    return module


@router.patch("/modules/{module_id}", response_model=ModuleAdminOut)
async def update_module(
    module_id: uuid.UUID,
    body: ModuleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")

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
    _: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    await db.delete(module)
    await db.commit()


# ── items ────────────────────────────────────────────────────────────────────

async def _item_admin_out(db: AsyncSession, item: ModuleItem) -> ItemAdminOut:
    """Video items store `content = {}` on the row — the real state (has the
    upload finished transcoding, is it watchable yet) lives on `ModuleVideo`,
    written asynchronously by the ARQ worker. Every item-returning admin
    endpoint goes through this so the authoring UI can show it instead of
    leaving the author to guess whether an upload actually finished."""
    content = dict(item.content)
    if item.kind == "video":
        video = (await db.execute(
            select(ModuleVideo).where(ModuleVideo.item_id == item.id)
        )).scalars().first()
        content = {
            "transcode_status": video.transcode_status if video else None,
            "transcode_error": video.transcode_error if video else None,
            "duration_seconds": video.duration_seconds if video else None,
        }
    return ItemAdminOut(
        id=item.id, module_id=item.module_id, kind=item.kind, title=item.title,
        is_required=item.is_required, position=item.position, content=content,
    )


@router.get("/modules/{module_id}/items", response_model=list[ItemAdminOut])
async def list_items(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    rows = (await db.execute(
        select(ModuleItem).where(ModuleItem.module_id == module_id).order_by(ModuleItem.position)
    )).scalars().all()
    return [await _item_admin_out(db, item) for item in rows]


@router.post("/modules/{module_id}/items", response_model=ItemAdminOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    module_id: uuid.UUID,
    body: ItemCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")

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
    _: User = Depends(require_lms_content),
):
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")

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
    _: User = Depends(require_lms_content),
):
    item = await db.get(ModuleItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

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
    _: User = Depends(require_lms_content),
):
    item = await db.get(ModuleItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
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
    _: User = Depends(require_lms_content),
):
    item = await db.get(ModuleItem, item_id)
    if item is None or item.kind != "attachment":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment item not found")

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
    kind: str, start_seconds: int, end_seconds: int | None, content: dict,
) -> tuple[int | None, dict]:
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
    _: User = Depends(require_lms_content),
):
    await _video_item(db, video_item_id)
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
    _: User = Depends(require_lms_content),
):
    await _video_item(db, video_item_id)
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
    _: User = Depends(require_lms_content),
):
    checkpoint = await db.get(VideoCheckpoint, checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")

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
    _: User = Depends(require_lms_content),
):
    checkpoint = await db.get(VideoCheckpoint, checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
    await db.delete(checkpoint)
    await db.commit()


# ── program curriculum (program → ordered courses, D5) ──────────────────────

@router.get("/programs/{program_id}/curriculum", response_model=list[CurriculumEntryOut])
async def list_curriculum(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    rows = (await db.execute(
        select(ProgramCurriculum)
        .where(ProgramCurriculum.program_id == program_id)
        .order_by(ProgramCurriculum.position)
    )).scalars().all()
    return rows


@router.post(
    "/programs/{program_id}/curriculum",
    response_model=CurriculumEntryOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_curriculum_entry(
    program_id: uuid.UUID,
    body: CurriculumEntryIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    course = await db.get(Course, body.course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

    dup = (await db.execute(
        select(ProgramCurriculum.id).where(
            ProgramCurriculum.program_id == program_id, ProgramCurriculum.course_id == body.course_id
        )
    )).first()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This course is already in the program's curriculum")

    position = body.position
    if position is None:
        max_pos = await db.scalar(
            select(func.max(ProgramCurriculum.position)).where(ProgramCurriculum.program_id == program_id)
        )
        position = (max_pos or 0) + 1
    else:
        taken = (await db.execute(
            select(ProgramCurriculum.id).where(
                ProgramCurriculum.program_id == program_id, ProgramCurriculum.position == position
            )
        )).first()
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Position {position} is already taken in this curriculum")

    entry = ProgramCurriculum(id=uuid.uuid4(), program_id=program_id, course_id=body.course_id, position=position)
    db.add(entry)
    await db.flush()
    # P4-2, trigger 1: reaches every cohort that inherits this program's
    # curriculum (no cohort_curriculum override of its own) — otherwise a
    # course added here reaches nobody already registered, silently.
    await reconcile_cohorts_inheriting_program(db, program_id)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/programs/{program_id}/curriculum/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_curriculum_entry(
    program_id: uuid.UUID,
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    entry = (await db.execute(
        select(ProgramCurriculum).where(
            ProgramCurriculum.program_id == program_id, ProgramCurriculum.course_id == course_id
        )
    )).scalars().first()
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Curriculum entry not found")
    await db.delete(entry)
    await db.commit()


# ── cohort curriculum (P4-1, Phase 2 Stage 4, 2026-08-10) ───────────────────
# A cohort with ANY rows here overrides its program's curriculum outright —
# see models/lms/curriculum.py::CohortCurriculum's docstring.

@router.get("/cohorts/{cohort_id}/curriculum", response_model=list[CohortCurriculumEntryOut])
async def list_cohort_curriculum(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    rows = (await db.execute(
        select(CohortCurriculum).where(CohortCurriculum.cohort_id == cohort_id).order_by(CohortCurriculum.position)
    )).scalars().all()
    return rows


@router.post(
    "/cohorts/{cohort_id}/curriculum", response_model=CohortCurriculumEntryOut, status_code=status.HTTP_201_CREATED,
)
async def add_cohort_curriculum_entry(
    cohort_id: uuid.UUID,
    body: CurriculumEntryIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    course = await db.get(Course, body.course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

    dup = (await db.execute(
        select(CohortCurriculum.id).where(
            CohortCurriculum.cohort_id == cohort_id, CohortCurriculum.course_id == body.course_id
        )
    )).first()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This course is already in the cohort's curriculum")

    position = body.position
    if position is None:
        max_pos = await db.scalar(
            select(func.max(CohortCurriculum.position)).where(CohortCurriculum.cohort_id == cohort_id)
        )
        position = (max_pos or 0) + 1
    else:
        taken = (await db.execute(
            select(CohortCurriculum.id).where(
                CohortCurriculum.cohort_id == cohort_id, CohortCurriculum.position == position
            )
        )).first()
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Position {position} is already taken in this curriculum")

    entry = CohortCurriculum(id=uuid.uuid4(), cohort_id=cohort_id, course_id=body.course_id, position=position)
    db.add(entry)
    await db.flush()
    # P4-2, trigger 1: this cohort's curriculum just changed (or just
    # started overriding its program's) — reach everyone already
    # registered, not just future registrations.
    await reconcile_cohort_enrollments(db, cohort_id)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/cohorts/{cohort_id}/curriculum/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_cohort_curriculum_entry(
    cohort_id: uuid.UUID,
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    entry = (await db.execute(
        select(CohortCurriculum).where(
            CohortCurriculum.cohort_id == cohort_id, CohortCurriculum.course_id == course_id
        )
    )).scalars().first()
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Curriculum entry not found")
    await db.delete(entry)
    await db.commit()


@router.post("/cohorts/{cohort_id}/reconcile-enrollments", response_model=ReconcileEnrollmentsOut)
async def reconcile_cohort_enrollments_now(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """P4-2, trigger 3: a manual "re-sync now" action — for whenever staff
    suspect drift (e.g. after a bulk data fix) rather than a curriculum
    edit specifically. Same idempotent function the other two triggers
    call; safe to press as often as wanted."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    created = await reconcile_cohort_enrollments(db, cohort_id)
    await db.commit()
    return ReconcileEnrollmentsOut(created=created)


# ── learning paths (self-paced ordered course sequences, 2026-08-08) ───────

async def _learning_path_admin_out(db: AsyncSession, path: LearningPath) -> LearningPathAdminOut:
    return LearningPathAdminOut(
        id=path.id, title=path.title, description=path.description,
        is_published=path.is_published, created_by=path.created_by, created_at=path.created_at,
        image_url=await storage.resolve_url(path.image_bucket, path.image_path),
    )


@router.get("/learning-paths", response_model=list[LearningPathAdminOut])
async def list_learning_paths(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    rows = (await db.execute(select(LearningPath).order_by(LearningPath.created_at.desc()))).scalars().all()
    return [await _learning_path_admin_out(db, p) for p in rows]


@router.post("/learning-paths", response_model=LearningPathAdminOut, status_code=status.HTTP_201_CREATED)
async def create_learning_path(
    body: LearningPathCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    path = LearningPath(id=uuid.uuid4(), created_by=current.id, **body.model_dump())
    db.add(path)
    await db.commit()
    await db.refresh(path)
    return await _learning_path_admin_out(db, path)


@router.get("/learning-paths/{path_id}", response_model=LearningPathAdminOut)
async def get_learning_path(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    return await _learning_path_admin_out(db, path)


@router.patch("/learning-paths/{path_id}", response_model=LearningPathAdminOut)
async def update_learning_path(
    path_id: uuid.UUID,
    body: LearningPathUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(path, field, value)
    await db.commit()
    await db.refresh(path)
    return await _learning_path_admin_out(db, path)


@router.post("/learning-paths/{path_id}/image", response_model=LearningPathAdminOut)
async def upload_learning_path_image(
    path_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")

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
    return await _learning_path_admin_out(db, path)


@router.delete("/learning-paths/{path_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_learning_path(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """No enrollment check like `delete_course` — a path itself grants no
    access (its steps' courses do, independently), so deleting one never
    strands a student mid-course. It only removes the curated grouping."""
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    await db.delete(path)
    await db.commit()


@router.get("/learning-paths/{path_id}/steps", response_model=list[LearningPathStepOut])
async def list_learning_path_steps(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
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
    _: User = Depends(require_lms_content),
):
    path = await db.get(LearningPath, path_id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    course = await db.get(Course, body.course_id)
    if course is None:
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
    _: User = Depends(require_lms_content),
):
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

async def _enrollment_admin_out(db: AsyncSession, enrollment: Enrollment) -> EnrollmentAdminOut:
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
    _: User = Depends(require_lms_content),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    rows = (await db.execute(
        select(Enrollment).where(Enrollment.course_id == course_id).order_by(Enrollment.created_at.desc())
    )).scalars().all()
    return [await _enrollment_admin_out(db, e) for e in rows]


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
    student = await db.get(User, body.user_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    enrollment = await enroll(
        db, user_id=body.user_id, course_id=course_id, source="ops", granted_by=current.id,
    )
    await db.commit()
    return await _enrollment_admin_out(db, enrollment)


@router.post("/enrollments/{enrollment_id}/revoke", response_model=EnrollmentAdminOut)
async def revoke_enrollment(
    enrollment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Sets status='inactive', never deletes (P1-5) — the row, and whatever
    progress/points hang off it later, survive; enroll() reactivates it in
    place if access is ever restored."""
    enrollment = await db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    enrollment.status = "inactive"
    await db.commit()
    return await _enrollment_admin_out(db, enrollment)


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
        row = await _enrollment_admin_out(db, e)
        course = await db.get(Course, e.course_id)
        row.course_title = course.title if course else None
        out.append(row)
    return out


@router.post("/courses/{course_id}/enrollments/bulk", response_model=BulkGrantOut)
async def bulk_grant_enrollment(
    course_id: uuid.UUID,
    body: BulkGrantIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    """One-shot iteration over a roster or a role (§3) — not a live
    membership rule. cohort_id: every contact with an active registration in
    that cohort who already has a linked LMS account (bulk-grant doesn't
    create accounts — see BulkGrantOut.skipped_no_account's docstring).
    role: every user holding that role, D2's "staff can take LMS courses
    too" made concrete."""
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

    skipped_no_account = 0
    if body.role is not None:
        user_ids = list((await db.execute(
            select(User.id).where(User.roles.any(body.role))
        )).scalars().all())
    else:
        contact_ids = list((await db.execute(
            select(Registration.contact_id).where(
                Registration.cohort_id == body.cohort_id,
                Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
        )).scalars().all())
        user_ids = list((await db.execute(
            select(User.id).where(User.contact_id.in_(contact_ids))
        )).scalars().all())
        skipped_no_account = len(set(contact_ids)) - len(set(user_ids))

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
