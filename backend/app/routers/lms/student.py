"""LMS student routes (LM1-3) — `/lms/*`.

Catalog and course outline are any-authenticated-user reads; module content
(the actual lessons), progress writes and quiz submissions are gated purely
on enrollment, not on holding the `student` role (P1-6, D2 — 2026-08-10:
"yes, staff can take LMS courses"). `require_lms_student` stays only on
`/enroll` and `/learning-paths/{id}/start` — the two *self-service* routes,
where the role gate is a deliberate policy line (self-enrol is for accounts
that hold the `student` role; staff access to a course is always an ops
grant, never self-enrol, per the operator's 2026-08-12 "assigned to them
only" instruction). `/my-courses`, `/my-programs` and `/my-activity` are
read-only views of a user's own enrollments/activity and are open to any
authenticated account (2026-08-12) so an ops-granted staff member can see
what they were assigned. Not-enrolled is a 404, never a 403 — a student (or
an enrolled staff member) who hasn't joined must not learn whether a course
exists and is a particular course, only that access is unavailable. Draft
(unpublished) courses 404 from every route for the same reason.

Every item payload flows through `student_view` (§2) — the answer-stripping
choke point — and the Pydantic response models (`extra="forbid"`) enforce the
leak guarantee a second time at the response boundary.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select

# from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_lms_student
from app.db.session import get_db
from app.models.lms import Course, CourseModule, Enrollment, ItemProgress, ModuleItem, VideoCheckpoint
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.team import Team
from app.models.lms.program import (
    LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress, LmsProgramTeamItemProgress,
)
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.user import User
from app.schemas.curriculum import PrerequisiteItemOut
from app.schemas.lms import (
    ActivityItemOut,
    AttachmentUrlOut,
    CheckpointAnswerIn,
    CheckpointAnswerOut,
    ContentQuiz,
    CourseCatalogOut,
    CourseDetailOut,
    EnrollIn,
    EnrollmentOut,
    LeaderboardEntryOut,
    LearningPathCatalogOut,
    LearningPathDetailOut,
    LearningPathStepOut,
    LmsProgramAssignmentSummaryOut,
    LmsProgramChecklistItemOut,
    LmsProgramChecklistOut,
    LmsProgramItemSubmitIn,
    LmsProgramTeamNameIn,
    ModuleItemOut,
    ModuleLockOut,
    ModuleOut,
    MyCertificateOut,
    MyCoursesOut,
    MyProgramOut,
    ProgressIn,
    ProgressOut,
    QuizAnswerCheckIn,
    QuizAnswerCheckOut,
    QuizAnswersIn,
    QuizReviewOut,
    VideoCheckpointOut,
)
from app.schemas.lms_cohort_quiz import (
    CohortQuizAttemptOut, CohortQuizAttemptQuestionOut, CohortQuizResultOut, CohortQuizSubmitIn,
)
from app.services.lms import (
    check_quiz_answer,
    course_completion,
    enroll,
    enrollment_is_active,
    get_quiz_display_order,
    item_progress,
    path_progress,
    path_total_duration_seconds,
    sanitize_checkpoint,
    student_view,
    submit_checkpoint_answer,
    submit_quiz,
    unlock_state,
)
from app.services.curriculum import is_unlocked, prerequisite_status
from app.services.lms.certificates import award_for_course_completion
from app.services.lms.dashboard import my_courses_dashboard, recent_activity
from app.services.lms.leaderboard import leaderboard
from app.services.lms.my_programs import my_programs
from app.models.missions.design import Design
from app.models.missions.mission import MissionAttempt
from app.models.team import Team
from app.services.missions.verifiers.design import ensure_design
from app.services.lms.program import (
    PROGRAM_ITEM_PDF_BUCKET, checklist_item_locked, checklist_item_write_target, get_student_checklist,
    list_student_assignments, refresh_item_progress, resolve_effective_poster_template_url,
)
from app.services.lms import cohort_quiz as cohort_quiz_service
from app.services import storage
from app.services.video_service import get_playback_info, get_video_for_owner
from app.models.certificate import Certificate
from app.models.enums import CertificateType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lms", tags=["lms"])


async def _assert_enrolled(
    db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID
) -> None:
    """Flat 404 for "not enrolled" *and* for "unknown course" — the two are
    indistinguishable on purpose (don't leak existence, LM1-3 spec). An
    expired enrollment (P1-3) reads the same as never having enrolled — no
    separate "your access expired" message, same don't-leak-existence
    reasoning extended to *why* access is gone."""
    enrollment = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user_id,
            Enrollment.course_id == course_id,
            *enrollment_is_active(),
        )
    )).scalars().first()
    if enrollment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")


async def _enrolled_item(
    db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID
) -> ModuleItem:
    item = await db.get(ModuleItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    module = await db.get(CourseModule, item.module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await _assert_enrolled(db, user_id, module.course_id)
    return item


async def _award_certificates_for_item(db: AsyncSession, user_id: uuid.UUID, item: ModuleItem) -> None:
    """Issue any certificate this progress write just earned (2026-08-13).

    Best-effort: a failure here (storage down, reportlab error) must never
    fail the progress write that triggered it — the student's completion is
    already recorded, and the certificate is re-checked on their next write
    and by `GET /lms/my-certificates`, so a miss is self-healing rather than
    permanent. Cheap on the overwhelmingly common path: `course_completion`
    returns False and nothing else runs.
    """
    module = await db.get(CourseModule, item.module_id)
    if module is None:
        return
    try:
        await award_for_course_completion(db, user_id=user_id, course_id=module.course_id)
    except Exception:
        logger.exception("certificate issuance failed for user=%s course=%s", user_id, module.course_id)


async def _published_course(
    db: AsyncSession, course_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> Course:
    """Published, OR the caller already holds an active enrollment (B5) — ops
    can deliberately enrol a student into a course still pending a publish
    review (e.g. via a program's curriculum), and that access must not
    dead-end at a 404. Enrollment implies visibility, not the other way
    round: self-enrol (below) omits user_id, since nobody can hold an
    enrollment in a course they haven't self-enrolled into yet."""
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    if course.is_published:
        return course
    if user_id is not None:
        enrolled = (await db.execute(
            select(Enrollment.id).where(
                Enrollment.user_id == user_id,
                Enrollment.course_id == course_id,
                *enrollment_is_active(),
            )
        )).first()
        if enrolled is not None:
            return course
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")


# ── catalog + course outline: any authenticated user ────────────────────────

@router.get("/catalog", response_model=list[CourseCatalogOut])
async def catalog(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """`open` and `paid` courses list for everyone; `invite` courses are
    fully hidden from this catalog for anyone without an active enrollment
    — the catalog isn't the place to advertise a course you can't get into
    without an existing grant, only `enrolled=True` invite courses show up
    (this applies to every caller, admin/operations included — the admin
    course list at `/lms/admin/courses` is the unfiltered oversight view).

    Staff can't self-enrol at all — `POST /lms/enroll` is student-only, so
    any course they don't already hold an ops-granted `Enrollment` in just
    403s on click. For everyone but admin/operations (who need the full
    catalog for oversight), the catalog additionally scopes down to what
    they're actually enrolled in."""
    stmt = select(Course).where(Course.is_published.is_(True))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Course.title.ilike(pattern), Course.description.ilike(pattern)))
    rows = (await db.execute(stmt.order_by(Course.title))).scalars().all()

    enrolled_course_ids = set((await db.execute(
        select(Enrollment.course_id).where(
            Enrollment.user_id == current.id,
            Enrollment.course_id.in_([c.id for c in rows]),
            *enrollment_is_active(),
        )
    )).scalars().all())

    rows = [c for c in rows if c.access_mode != "invite" or c.id in enrolled_course_ids]

    if not ({"student", "admin", "operations"} & set(current.roles)):
        rows = [c for c in rows if c.id in enrolled_course_ids]

    return [
        CourseCatalogOut(
            id=c.id, title=c.title, description=c.description, kind=c.kind,
            image_url=await storage.resolve_url(c.image_bucket, c.image_path),
            level=c.level, track=c.track,
            access_mode=c.access_mode, enrolled=c.id in enrolled_course_ids,
            locked=not await is_unlocked(db, item_type="course", item_id=c.id, user_id=current.id),
        )
        for c in rows
    ]


@router.get("/courses/{course_id}", response_model=CourseDetailOut)
async def course_detail(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Module list + lock states + overall completion for *this* user.

    The outline is login-only (catalog + browse, D8); the items inside a
    module are what enrollment gates. Lock states for a non-student or a
    not-yet-enrolled student simply read as module-1-open, rest-locked.
    """
    course = await _published_course(db, course_id, current.id)

    enrolled_row = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == current.id,
            Enrollment.course_id == course.id,
            *enrollment_is_active(),
        )
    )).scalars().first()

    locks = await unlock_state(db, user_id=current.id, course_id=course.id)
    completion = await course_completion(db, user_id=current.id, course_id=course.id)
    prereqs = await prerequisite_status(db, item_type="course", item_id=course.id, user_id=current.id)

    instructor_name = instructor_photo_url = None
    if course.instructor_id:
        instructor = await db.get(User, course.instructor_id)
        if instructor:
            instructor_name = instructor.full_name
            instructor_photo_url = instructor.photo_url

    return CourseDetailOut(
        id=course.id,
        title=course.title,
        description=course.description,
        kind=course.kind,
        enrolled=enrolled_row is not None,
        completed=completion["completed"],
        image_url=await storage.resolve_url(course.image_bucket, course.image_path),
        outcomes=course.outcomes or [],
        level=course.level,
        track=course.track,
        instructor_name=instructor_name,
        instructor_title=course.instructor_title,
        instructor_photo_url=instructor_photo_url,
        access_mode=course.access_mode,
        price_cents=course.price_cents,
        currency=course.currency,
        locked=not all(p["satisfied"] for p in prereqs),
        prerequisites=[PrerequisiteItemOut(**p) for p in prereqs],
        modules=[
            ModuleLockOut(
                module_id=row["module_id"],
                title=row["title"],
                position=row["position"],
                locked=row["locked"],
                mandatory_total=row["mandatory_total"],
                mandatory_completed=row["mandatory_completed"],
                total_items=row.get("total_items", 0),
            )
            for row in locks
        ],
    )


# ── learning paths (self-paced ordered course sequences) ────────────────────

async def _path_steps(db: AsyncSession, path_id: uuid.UUID) -> list[LearningPathStep]:
    return list((await db.execute(
        select(LearningPathStep)
        .where(LearningPathStep.learning_path_id == path_id)
        .order_by(LearningPathStep.position)
    )).scalars().all())


async def _path_enrolled(db: AsyncSession, *, user_id: uuid.UUID, course_ids: list[uuid.UUID]) -> bool:
    """True iff the caller has an active enrollment in at least one of these
    step courses — the "am I on this path" signal (2026-08-12), and
    (2026-09-01) also what makes an invite-mode path visible/reachable at
    all for that caller."""
    if not course_ids:
        return False
    return (await db.execute(
        select(Enrollment.id).where(
            Enrollment.user_id == user_id, Enrollment.course_id.in_(course_ids), *enrollment_is_active(),
        ).limit(1)
    )).first() is not None


async def _published_path(
    db: AsyncSession, path_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> LearningPath:
    """Published, AND not invite-mode unless the caller already holds an
    active enrollment in one of its step courses (mirrors _published_course)
    — an invite path is fully hidden, not just locked, for anyone it hasn't
    been granted to. `user_id=None` (nothing to check enrollment against)
    always fails the invite branch, same as `_published_course`."""
    path = await db.get(LearningPath, path_id)
    if path is None or not path.is_published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    if path.access_mode == "invite":
        steps = await _path_steps(db, path.id)
        enrolled = user_id is not None and await _path_enrolled(
            db, user_id=user_id, course_ids=[s.course_id for s in steps]
        )
        if not enrolled:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    return path


async def _path_fully_owned(db: AsyncSession, *, user_id: uuid.UUID, course_ids: list[uuid.UUID]) -> bool:
    """True iff the caller already has an active enrollment in every one of
    these courses — i.e. a bundle purchase would have nothing left to grant."""
    if not course_ids:
        return False
    owned = (await db.execute(
        select(Enrollment.course_id).where(
            Enrollment.user_id == user_id, Enrollment.course_id.in_(course_ids), *enrollment_is_active(),
        )
    )).scalars().all()
    return set(owned) >= set(course_ids)


@router.get("/learning-paths", response_model=list[LearningPathCatalogOut])
async def learning_paths_catalog(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    paths = (await db.execute(
        select(LearningPath).where(LearningPath.is_published.is_(True)).order_by(LearningPath.title)
    )).scalars().all()

    out: list[LearningPathCatalogOut] = []
    for path in paths:
        steps = await _path_steps(db, path.id)
        step_course_ids = [s.course_id for s in steps]
        enrolled = await _path_enrolled(db, user_id=current.id, course_ids=step_course_ids)
        if path.access_mode == "invite" and not enrolled:
            continue
        progress = await path_progress(db, user_id=current.id, steps=steps)
        duration = await path_total_duration_seconds(db, [s.course_id for s in steps])
        out.append(LearningPathCatalogOut(
            id=path.id, title=path.title, description=path.description,
            image_url=await storage.resolve_url(path.image_bucket, path.image_path),
            course_count=progress["course_count"], mission_count=progress["mission_count"],
            total_duration_seconds=duration, pct=progress["pct"], enrolled=enrolled,
            access_mode=path.access_mode,
            price_cents=path.price_cents, currency=path.currency,
            fully_owned=await _path_fully_owned(db, user_id=current.id, course_ids=step_course_ids),
        ))
    return out


@router.get("/learning-paths/{path_id}", response_model=LearningPathDetailOut)
async def learning_path_detail(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    path = await _published_path(db, path_id, user_id=current.id)
    steps = await _path_steps(db, path.id)
    step_course_ids = [s.course_id for s in steps]
    progress = await path_progress(db, user_id=current.id, steps=steps)
    duration = await path_total_duration_seconds(db, [s.course_id for s in steps])
    enrolled = await _path_enrolled(db, user_id=current.id, course_ids=step_course_ids)
    fully_owned = await _path_fully_owned(db, user_id=current.id, course_ids=step_course_ids)
    return LearningPathDetailOut(
        id=path.id, title=path.title, description=path.description,
        image_url=await storage.resolve_url(path.image_bucket, path.image_path),
        pct=progress["pct"], course_count=progress["course_count"],
        mission_count=progress["mission_count"], total_duration_seconds=duration,
        steps=[LearningPathStepOut(**row) for row in progress["steps"]],
        access_mode=path.access_mode, enrolled=enrolled,
        price_cents=path.price_cents, currency=path.currency, fully_owned=fully_owned,
    )


@router.post("/learning-paths/{path_id}/start", response_model=LearningPathDetailOut)
async def start_learning_path(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
):
    """Bulk self-enrol in every step's course at once (idempotent, same
    `enroll()` self-source path `POST /lms/enroll` already uses) — a path's
    stats/progress only make sense once the student has access to every
    course in it, mirroring how cohort-add already bulk-enrols a program's
    whole curriculum in one shot.

    The path's own access_mode (2026-09-01) is checked first: `invite`/`paid`
    paths 403/402 here exactly like `POST /lms/enroll` does for a course —
    self-`/start` only works on `open` paths; an invite path only becomes
    reachable via an admin/invite-code grant, a paid path via the bundle
    checkout. Separately, and unchanged, only `open` steps self-enrol even on
    an `open` path (P1-4/P1-6) — this bulk path is a shortcut for the same
    self-enrol `POST /lms/enroll` does, so it must respect each step's own
    access_mode gate too. A restricted step is just skipped; the rest of the
    path still starts."""
    path = await _published_path(db, path_id, user_id=current.id)
    if path.access_mode == "invite":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="This learning path is invite-only — ask an admin to grant you access",
        )
    if path.access_mode == "paid":
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="This learning path requires payment — buy it via POST /lms/learning-paths/{path_id}/checkout",
        )
    steps = await _path_steps(db, path.id)
    step_course_ids = [s.course_id for s in steps]
    for step in steps:
        course = await db.get(Course, step.course_id)
        if course is not None and course.access_mode == "open":
            await enroll(db, user_id=current.id, course_id=step.course_id, source="self")
    await db.commit()

    progress = await path_progress(db, user_id=current.id, steps=steps)
    duration = await path_total_duration_seconds(db, [s.course_id for s in steps])
    enrolled = await _path_enrolled(db, user_id=current.id, course_ids=step_course_ids)
    fully_owned = await _path_fully_owned(db, user_id=current.id, course_ids=step_course_ids)
    return LearningPathDetailOut(
        id=path.id, title=path.title, description=path.description,
        image_url=await storage.resolve_url(path.image_bucket, path.image_path),
        pct=progress["pct"], course_count=progress["course_count"],
        mission_count=progress["mission_count"], total_duration_seconds=duration,
        steps=[LearningPathStepOut(**row) for row in progress["steps"]],
        access_mode=path.access_mode, enrolled=enrolled,
        price_cents=path.price_cents, currency=path.currency, fully_owned=fully_owned,
    )


# ── dashboard: student only ──────────────────────────────────────────────────

@router.get("/my-courses", response_model=MyCoursesOut)
async def my_courses(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Stats + resume pointer + per-course progress for the landing page's
    resume band and the /learn/my-courses dashboard (LMS redesign).

    Any authenticated account, not just `student` (2026-08-12): a staff
    member ops-granted a course (D2, "yes, staff can take LMS courses") must
    be able to see it here, same as a student would. `require_lms_student`
    stayed on this route only because it predates that decision, not because
    the dashboard is meant to be student-only — it has no role-shaped
    content, just this user's own enrollments."""
    return await my_courses_dashboard(db, user_id=current.id)


@router.get("/my-programs", response_model=list[MyProgramOut])
async def my_programs_route(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """P4-3 — the cohort view a student cannot currently see at all: dates,
    location, instructor, attendance, courses. `missions` is an empty list
    from day one (Stage 5 fills it in) so the frontend never has to branch
    on whether the key exists.

    Opened to any authenticated account (2026-08-12), same reasoning as
    `/my-courses` above — staff with no cohort just get an empty list."""
    return await my_programs(db, user=current)


# ── LMS Program checklist (2026-08-21 redesign) ─────────────────────────────
# Distinct from /my-programs above (the older, courses-only cohort view) —
# these serve the new checklist entity: lms_program_assignments.

@router.get("/programs", response_model=list[LmsProgramAssignmentSummaryOut])
async def my_program_assignments(
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    return await list_student_assignments(db, user_id=current.id)


@router.get("/programs/{assignment_id}", response_model=LmsProgramChecklistOut)
async def program_checklist(
    assignment_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    checklist = await get_student_checklist(db, assignment_id=assignment_id, user_id=current.id)
    if checklist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program assignment not found")
    return checklist


async def _own_progress_row(
    db: AsyncSession, *, assignment_id: uuid.UUID, item_id: uuid.UUID, user: User,
) -> tuple[LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress]:
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    if assignment is None or assignment.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program assignment not found")
    progress = await db.scalar(
        select(LmsProgramItemProgress).where(
            LmsProgramItemProgress.assignment_id == assignment_id, LmsProgramItemProgress.item_id == item_id,
        )
    )
    item = await db.get(LmsProgramItem, item_id) if progress else None
    if progress is None or item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Checklist item not found")
    return assignment, item, progress


async def _checklist_item_out(
    db: AsyncSession, *, item: LmsProgramItem, target: LmsProgramItemProgress | LmsProgramTeamItemProgress,
) -> LmsProgramChecklistItemOut:
    """Serializes whichever row `checklist_item_write_target` returned —
    individual or the shared team row — into the one response shape the
    frontend renders either way."""
    is_team = isinstance(target, LmsProgramTeamItemProgress)
    updated_by_name = None
    poster_template_url = None
    if is_team and target.updated_by_user_id:
        updater = await db.get(User, target.updated_by_user_id)
        updated_by_name = updater.full_name if updater else None
    elif not is_team:
        assignment = await db.get(LmsProgramAssignment, target.assignment_id)
        submitter = await db.get(User, assignment.user_id) if assignment else None
        updated_by_name = submitter.full_name if submitter else None

    if item.mission_step_key == "poster":
        cohort_id = None
        if is_team:
            team = await db.get(Team, target.team_id)
            cohort_id = team.cohort_id if team else None
        else:
            assignment = await db.get(LmsProgramAssignment, target.assignment_id)
            cohort_id = assignment.cohort_id if assignment else None
        poster_template_url = await resolve_effective_poster_template_url(db, cohort_id=cohort_id)

    submitted_url = target.submitted_url
    if not submitted_url and not is_team and target.mission_attempt_id:
        design = await db.scalar(select(Design).where(Design.attempt_id == target.mission_attempt_id))
        if design and design.poster_url:
            submitted_url = design.poster_url

    return LmsProgramChecklistItemOut(
        id=item.id, position=item.position, item_type=item.item_type, title=item.title,
        description=item.description, optional=item.optional, requires_confirmation=item.requires_confirmation,
        status=target.status, course_id=item.course_id,
        mission_attempt_id=target.mission_attempt_id if not is_team else None,
        external_url=item.external_url, submission_prompt=item.submission_prompt,
        has_pdf=item.pdf_path is not None,
        submitted_url=submitted_url,
        deadline_at=item.deadline_at,
        session_date=item.session_date, session_starts_at=item.session_starts_at,
        session_location=item.session_location, session_meeting_url=item.session_meeting_url,
        scope=item.scope, updated_by_name=updated_by_name,
        updated_at=target.updated_at,
        mission_step_key=item.mission_step_key,
        poster_template_url=poster_template_url,
        submission_multi_link=item.submission_multi_link,
        submitted_links=target.submitted_links,
        submission_link_labels=item.submission_link_labels,
    )


@router.get("/programs/{assignment_id}/items/{item_id}/pdf-url")
async def program_item_pdf_url(
    assignment_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_student),
) -> dict[str, str]:
    """Resolved only when a student actually opens a `pdf` item's document
    (or a `pdf`-kind guideline on any other item type — same file, same
    reuse the admin upload endpoint follows) — same posture as
    `attachment_url`/the Curriculum Library's resolve endpoint, never
    baked into the checklist read payload."""
    _, item, _ = await _own_progress_row(db, assignment_id=assignment_id, item_id=item_id, user=current)
    if (item.item_type != "pdf" and item.guideline_kind != "pdf") or not item.pdf_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No PDF uploaded for this item yet")
    url = await storage.get_signed_url(PROGRAM_ITEM_PDF_BUCKET, item.pdf_path)
    return {"url": url}


@router.get("/programs/{assignment_id}/items/{item_id}/guideline-video-url")
async def program_item_guideline_video_url(
    assignment_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_student),
) -> dict:
    """Resolved only when a student actually opens an *uploaded* video
    guideline — an embed-link guideline never needs this, the checklist
    payload already carries the real (public) URL in guideline_url. Same
    posture as program_item_pdf_url above.

    `video_info` mirrors get_playback_info()'s shape exactly and is what the
    frontend's shared <VideoPlayer> needs — `url` alone can't represent an
    hls_encrypted video (no plain URL exists for one; playback needs a
    token, fetched by the player itself off `video_info.video_id`)."""
    _, item, _ = await _own_progress_row(db, assignment_id=assignment_id, item_id=item_id, user=current)
    if item.guideline_kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No video guideline on this item")
    video = await get_video_for_owner(db, owner_type="program_item_guideline", owner_id=item_id)
    if video is None or video.provider != "upload":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No video uploaded for this item yet")
    info = await get_playback_info(db, video)
    return {"url": info.get("url") or "", "video_info": info}


@router.post("/programs/{assignment_id}/items/{item_id}/complete", response_model=LmsProgramChecklistItemOut)
async def complete_program_item(
    assignment_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_student),
):
    """Self-check — for external_link/pdf/manual items with no
    `requires_confirmation`, and for `submission` items only after a link
    has already been submitted. `course`/`mission_run` are auto-tracked
    and rejected here; use the course player / mission attempt directly.
    A `scope="team"` item writes to the shared team row (any teammate can
    call this), not the caller's own individual row."""
    assignment, item, individual = await _own_progress_row(db, assignment_id=assignment_id, item_id=item_id, user=current)
    if item.item_type in ("course", "mission_run", "quiz"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This item is tracked automatically")
    if await checklist_item_locked(db, assignment=assignment, item=item):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This step isn't unlocked yet")
    target = await checklist_item_write_target(db, assignment=assignment, item=item, individual=individual, user_id=current.id)
    if item.item_type == "submission" and not target.submitted_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Submit a link first")
    if item.requires_confirmation:
        target.status = "awaiting_confirmation"
    else:
        target.status = "done"
        target.completed_at = datetime.now(timezone.utc)
    if isinstance(target, LmsProgramTeamItemProgress):
        target.updated_by_user_id = current.id
    target.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(target)
    return await _checklist_item_out(db, item=item, target=target)


@router.post("/programs/{assignment_id}/items/{item_id}/submit", response_model=LmsProgramChecklistItemOut)
async def submit_program_item(
    assignment_id: uuid.UUID, item_id: uuid.UUID, body: LmsProgramItemSubmitIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_student),
):
    """Paste-back for a `submission` item — same shape as the Poster tab.
    Auto-completes on submit: marks the item `done` right away, or
    `awaiting_confirmation` if the item requires ops sign-off. A
    `scope="team"` item writes to the shared team row — any teammate
    submitting overrides whatever was there before, on purpose.

    `submission_multi_link` items (2026-09-14, ops's own per-item toggle)
    take `body.links` instead of `body.url` — several labeled links in one
    submission (e.g. mem1/mem2/team link). `submitted_url` still gets set
    to the first link either way, so anything only reading that column
    (the poster path, older exports) keeps seeing something real."""
    assignment, item, individual = await _own_progress_row(db, assignment_id=assignment_id, item_id=item_id, user=current)
    is_poster = item.item_type == "mission_run" and item.mission_step_key == "poster"
    if item.item_type != "submission" and not is_poster:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This item does not take a submission")
    if not is_poster and item.deadline_at is not None and datetime.now(timezone.utc) > item.deadline_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The deadline for this submission has passed")
    if await checklist_item_locked(db, assignment=assignment, item=item):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This step isn't unlocked yet")
    target = await checklist_item_write_target(db, assignment=assignment, item=item, individual=individual, user_id=current.id)

    is_multi = item.item_type == "submission" and item.submission_multi_link
    if is_multi:
        links = [link for link in (body.links or []) if link.url.strip()]
        if not links:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Submit at least one link")
        # 2026-09-14 — ops's own fixed label set (submission_link_labels):
        # once set, it's the one source of truth for which slots this
        # item's form shows, so a link under any other label is rejected
        # (never silently dropped or silently accepted) and every required
        # label needs a real link before this goes through. An older
        # multi-link item authored before this existed (submission_link_labels
        # is None/empty) keeps taking free-text, student-entered labels,
        # none of them required — completely unchanged.
        label_specs = item.submission_link_labels or []
        if label_specs:
            valid_labels = [spec["label"] for spec in label_specs]
            required_labels = [spec["label"] for spec in label_specs if spec.get("required")]
            submitted_labels = {link.label for link in links}
            unknown = sorted(submitted_labels - set(valid_labels))
            if unknown:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail=f"Unrecognized link label(s): {', '.join(unknown)}",
                )
            missing = [label for label in required_labels if label not in submitted_labels]
            if missing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail=f"Missing required link(s): {', '.join(missing)}",
                )
        target.submitted_links = [link.model_dump() for link in links]
        target.submitted_url = links[0].url
        # The poster-attempt block below is unreachable here — is_multi
        # requires item_type=="submission", is_poster requires
        # item_type=="mission_run"; mutually exclusive by construction.
    else:
        if not body.url or not body.url.strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Submit a link")
        target.submitted_url = body.url
    if item.requires_confirmation:
        target.status = "awaiting_confirmation"
    else:
        target.status = "done"
        target.completed_at = datetime.now(timezone.utc)
    if isinstance(target, LmsProgramTeamItemProgress):
        target.updated_by_user_id = current.id
    target.updated_at = datetime.now(timezone.utc)

    # The attempt lives on `target`, not necessarily `individual` — a
    # team-scoped poster step's shared attempt is on the team row
    # (LmsProgramTeamItemProgress.mission_attempt_id), never on this
    # student's own individual row.
    if target.mission_attempt_id is not None:
        attempt = await db.get(MissionAttempt, target.mission_attempt_id)
        if attempt is not None:
            design = await ensure_design(db, attempt=attempt)
            design.poster_url = body.url
            design.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(target)
    return await _checklist_item_out(db, item=item, target=target)


@router.post("/programs/{assignment_id}/items/{item_id}/team-name", response_model=LmsProgramChecklistItemOut)
async def set_team_name(
    assignment_id: uuid.UUID, item_id: uuid.UUID, body: LmsProgramTeamNameIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_student),
):
    """A `team_setup` item's one action — rename the caller's own team.
    Always team-scoped (validate_item_payload rejects any other scope at
    authoring time), so any teammate can call this as many times as they
    want until the deadline — last write wins, same convention every other
    team-scoped write already follows (see `submit_program_item` above).
    Writes straight to `Team.name` — the item's own progress row only
    tracks *that* the team did it (status/who/when), never a second copy
    of the name itself, so every other view that reads `Team.name` (ops's
    Teams tab, judge views, this same checklist's own top-level
    `team_name`) sees the change with no extra wiring."""
    assignment, item, individual = await _own_progress_row(db, assignment_id=assignment_id, item_id=item_id, user=current)
    if item.item_type != "team_setup":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This item isn't a team setup step")
    if item.deadline_at is not None and datetime.now(timezone.utc) > item.deadline_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The deadline to set your team name has passed")
    if await checklist_item_locked(db, assignment=assignment, item=item):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This step isn't unlocked yet")
    target = await checklist_item_write_target(db, assignment=assignment, item=item, individual=individual, user_id=current.id)
    if not isinstance(target, LmsProgramTeamItemProgress):
        # Can't happen given item.scope is forced to "team" at authoring
        # time (validate_item_payload) — guard rather than silently write
        # to the wrong row if that invariant is ever broken.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="This team setup item is misconfigured")
    team = await db.get(Team, target.team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")

    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Team name can't be empty")
    collision = await db.scalar(
        select(Team.id).where(
            Team.cohort_id == team.cohort_id, Team.id != team.id, func.lower(Team.name) == name.lower(),
        )
    )
    if collision is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="That team name is already taken")
    team.name = name

    if item.requires_confirmation:
        target.status = "awaiting_confirmation"
    else:
        target.status = "done"
        target.completed_at = datetime.now(timezone.utc)
    target.updated_by_user_id = current.id
    target.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(target)
    return await _checklist_item_out(db, item=item, target=target)


@router.post("/programs/{assignment_id}/items/{item_id}/quiz/start", response_model=CohortQuizAttemptOut)
async def start_cohort_quiz(
    assignment_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_student),
):
    """Get-or-create the student's one attempt at this checklist item's
    quiz — a page refresh never reshuffles it (see
    `services/lms/cohort_quiz.py::start_attempt`). Returns the existing
    attempt (in whatever state) if one already exists, so a student who
    already submitted gets their own record back rather than a 409."""
    assignment, item, _ = await _own_progress_row(db, assignment_id=assignment_id, item_id=item_id, user=current)
    if item.item_type != "quiz":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This item is not a quiz")
    if await checklist_item_locked(db, assignment=assignment, item=item):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This step isn't unlocked yet")
    attempt = await cohort_quiz_service.start_attempt(db, item=item, user_id=current.id, cohort_id=assignment.cohort_id)
    await db.commit()
    questions = await cohort_quiz_service.get_attempt_questions(db, attempt)
    return CohortQuizAttemptOut(
        id=attempt.id, program_item_id=attempt.program_item_id, status=attempt.status, total=attempt.total,
        questions=[CohortQuizAttemptQuestionOut(**q) for q in questions],
    )


@router.post("/programs/{assignment_id}/items/{item_id}/quiz/submit", response_model=CohortQuizResultOut)
async def submit_cohort_quiz(
    assignment_id: uuid.UUID, item_id: uuid.UUID, body: CohortQuizSubmitIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_student),
):
    """All the student's answers at once (client-tracked per-question
    timing included) — grades, flips the checklist item to done via
    `refresh_item_progress` (done on submission alone, score never gates
    it — this is a diagnostic, not a pass/fail step)."""
    assignment, item, progress = await _own_progress_row(db, assignment_id=assignment_id, item_id=item_id, user=current)
    if item.item_type != "quiz":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This item is not a quiz")
    # Re-checked here too, not just in start_cohort_quiz — the item's
    # gating can change between start and submit (same defensive posture
    # submit_program_item takes for a submission item).
    if await checklist_item_locked(db, assignment=assignment, item=item):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This step isn't unlocked yet")
    attempt = await cohort_quiz_service.get_own_attempt(db, program_item_id=item_id, user_id=current.id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Start the quiz before submitting it")
    attempt = await cohort_quiz_service.submit_attempt(db, attempt, body.answers)
    await refresh_item_progress(db, progress=progress, item=item, user_id=current.id)
    await db.commit()
    review = await cohort_quiz_service.get_attempt_review(db, attempt)
    return cohort_quiz_service.result_out(attempt, review)


@router.get("/programs/{assignment_id}/items/{item_id}/quiz/result", response_model=CohortQuizResultOut)
async def get_cohort_quiz_result(
    assignment_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_student),
):
    _, item, _ = await _own_progress_row(db, assignment_id=assignment_id, item_id=item_id, user=current)
    if item.item_type != "quiz":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This item is not a quiz")
    attempt = await cohort_quiz_service.get_own_attempt(db, program_item_id=item_id, user_id=current.id)
    if attempt is None or attempt.status != "submitted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No submitted attempt yet")
    review = await cohort_quiz_service.get_attempt_review(db, attempt)
    return cohort_quiz_service.result_out(attempt, review)


@router.get("/my-activity", response_model=list[ActivityItemOut])
async def my_activity(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Last 10 completed items across every course — the profile page's
    activity feed.

    Opened to any authenticated account (2026-08-12), same reasoning as
    `/my-courses` above."""
    return await recent_activity(db, user_id=current.id)


@router.get("/my-certificates", response_model=list[MyCertificateOut])
async def my_certificates(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Certificates this account has earned in the LMS (2026-08-13).

    Deliberately scoped to the two LMS types — a staff member's workshop or
    instructor-completion certs belong on their portal documents page, not
    on the learner profile, and mixing them would put a cert they earned as
    an employee next to ones they earned as a student.

    Also acts as the self-heal for a certificate whose issuance failed at
    completion time: anything now complete but uncertified is issued here.
    """
    await _backfill_missing_certificates(db, current.id)

    rows = (await db.execute(
        select(Certificate).where(
            Certificate.user_id == current.id,
            Certificate.type.in_([
                CertificateType.lms_course_completion, CertificateType.lms_path_completion,
            ]),
        ).order_by(Certificate.generated_at.desc())
    )).scalars().all()

    out: list[MyCertificateOut] = []
    for row in rows:
        if row.course_id is not None:
            course = await db.get(Course, row.course_id)
            title = course.title if course else "Course"
        else:
            path = await db.get(LearningPath, row.learning_path_id) if row.learning_path_id else None
            title = path.title if path else "Learning path"
        out.append(MyCertificateOut(
            id=row.id, type=row.type.value if hasattr(row.type, "value") else str(row.type),
            title=title, course_id=row.course_id, learning_path_id=row.learning_path_id,
            issued_at=row.generated_at,
            url=await storage.resolve_url(row.bucket, row.file_path),
        ))
    return out


async def _backfill_missing_certificates(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Issue anything the student has finished but wasn't certified for —
    covers certificates missed while issuance was failing, and courses
    completed before this feature existed. Best-effort and bounded to the
    student's own active enrollments; `award_for_course_completion` is a
    no-op for anything already certified or not yet complete.

    `notify=False`: this can issue several certificates in one sweep for
    work finished long ago, and a burst of congratulation emails for old
    completions is worse than none. Only the live completion path emails."""
    course_ids = (await db.execute(
        select(Enrollment.course_id).where(
            Enrollment.user_id == user_id, *enrollment_is_active(),
        )
    )).scalars().all()
    for course_id in course_ids:
        try:
            await award_for_course_completion(db, user_id=user_id, course_id=course_id, notify=False)
        except Exception:
            logger.exception("certificate backfill failed for user=%s course=%s", user_id, course_id)
    await db.commit()


@router.get("/leaderboard", response_model=list[LeaderboardEntryOut])
async def get_leaderboard(
    scope: Literal["cohort", "global"] = "global",
    cohort_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """P2-4, linked into the frontend as of Live Games Phase 2C (8-2). D6
    (scope + display-name policy) is settled: `display_name` is the
    student's nickname (`services/nicknames.py`, 8-1), never a real name."""
    if scope == "cohort" and cohort_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cohort_id is required for scope=cohort")
    return await leaderboard(db, cohort_id=cohort_id if scope == "cohort" else None)


# ── enrollment: student only ────────────────────────────────────────────────

@router.post("/enroll", response_model=EnrollmentOut)
async def enroll_self(
    body: EnrollIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
):
    """Self-enrol from the catalog (D8 source='self'), branched on the
    course's access_mode (P1-4): `open` enrols outright; `invite` 403s — a
    student can't self-enrol into an invite-only course, only an admin grant
    (P1-5) gets them in; `paid` 402s and points the caller at
    `POST /lms/courses/{course_id}/checkout` — that's where the real Stripe
    flow lives (checkout.py); this endpoint never takes payment itself, on
    purpose, so a client can't self-enrol a paid course by hitting the wrong
    route. `access_mode` and prerequisites (7B-2) are two different
    mechanisms and both apply here — a grant alone isn't enough if the
    unified DAG says a required course/mission isn't done yet. Idempotent
    for `open` — enrolling again returns the same row; a reinstated or
    re-expired enrollment (re)activates in place."""
    course = await _published_course(db, body.course_id)

    if course.access_mode == "invite":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="This course is invite-only — ask an admin to grant you access",
        )
    if course.access_mode == "paid":
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="This course requires payment — start checkout via POST /lms/courses/{course_id}/checkout",
        )
    if not await is_unlocked(db, item_type="course", item_id=course.id, user_id=current.id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Complete the required courses/missions first",
        )

    enrollment = await enroll(
        db, user_id=current.id, course_id=body.course_id, source="self"
    )
    await db.commit()
    return EnrollmentOut(
        id=enrollment.id,
        course_id=enrollment.course_id,
        source=enrollment.source,
        status=enrollment.status,
        created_at=enrollment.created_at,
        expires_at=enrollment.expires_at,
    )


# ── module read: student AND enrolled ───────────────────────────────────────

async def _video_state(db: AsyncSession, item: ModuleItem) -> dict:
    """Called only from module_read, which already ran _assert_enrolled — so
    handing back the Video row's id here is not a new access grant. It's
    what lets the player call the generic /videos/{video_id}/... surface
    (routers/video.py) directly; that surface re-checks enrollment itself on
    every request regardless of what this endpoint returned."""
    video = await get_video_for_owner(db, owner_type="module_item", owner_id=item.id)
    if video is None:
        return {"transcode_status": None, "duration_seconds": None, "video_id": None}
    return {
        "transcode_status": video.status,
        "duration_seconds": video.duration_seconds,
        "video_id": str(video.id),
    }


async def _mission_embed_state(db: AsyncSession, item: ModuleItem, user_id: uuid.UUID) -> dict:
    """P5-5 — enriches a mission item's sanitized `{mission_id, variant_id}`
    with display fields looked up fresh per request (same two-step shape as
    `_video_state`, nothing here is stored on the item itself)."""
    content = item.content or {}
    mission_id = content.get("mission_id")
    if mission_id is None:
        return {"mission_title": None, "mission_kind": None, "points": None, "attempt_status": None}

    mission = await db.get(Mission, mission_id)
    variant_id = content.get("variant_id")
    points = None
    if variant_id:
        variant = await db.get(MissionVariant, variant_id)
        points = variant.points if variant else None

    attempt = (await db.execute(
        select(MissionAttempt)
        .where(MissionAttempt.mission_id == mission_id, MissionAttempt.user_id == user_id)
        .order_by(MissionAttempt.attempt_no.desc())
    )).scalars().first()

    return {
        "mission_title": mission.title if mission else None,
        "mission_kind": mission.kind if mission else None,
        "points": points,
        "attempt_status": attempt.status if attempt else None,
    }


def _preview_content(kind: str, content: dict | None) -> dict:
    content = content or {}
    if kind == "quiz":
        return {"pass_threshold": content.get("pass_threshold", 0), "questions": []}
    if kind == "text":
        return {"body": ""}
    if kind == "flashcards":
        return {"title": content.get("title"), "cards": []}
    if kind == "attachment":
        return {"filename": content.get("filename"), "size_bytes": content.get("size_bytes")}
    if kind == "video":
        return {}
    if kind == "mission":
        return {"mission_id": content.get("mission_id"), "variant_id": content.get("variant_id")}
    return {}


@router.get("/modules/{module_id}", response_model=ModuleOut)
async def module_read(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """The actual lessons — every item through `student_view`, plus this
    student's per-item status and the video transcode state the player needs.

    When the caller is not enrolled, returns the module outline (item titles,
    positions, kinds, duration) so the course landing page can preview the
    syllabus without leaking lesson bodies, quiz questions, or flashcards.
    """
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await _published_course(db, module.course_id, current.id)

    enrolled = (await db.execute(
        select(Enrollment.id).where(
            Enrollment.user_id == current.id,
            Enrollment.course_id == module.course_id,
            *enrollment_is_active(),
        )
    )).first() is not None

    items = (await db.execute(
        select(ModuleItem).where(ModuleItem.module_id == module_id).order_by(ModuleItem.position)
    )).scalars().all()

    progress_map = {}
    if enrolled:
        progress_rows = (await db.execute(
            select(ItemProgress).where(
                ItemProgress.user_id == current.id,
                ItemProgress.item_id.in_([i.id for i in items]),
            )
        )).scalars().all()
        progress_map = {p.item_id: p for p in progress_rows}

    item_payloads: list[ModuleItemOut] = []
    for item in items:
        row = progress_map.get(item.id)
        quiz_order = None
        if enrolled:
            if item.kind == "quiz":
                # Pass the already-fetched (possibly absent) row so a random-N
                # quiz doesn't re-SELECT ItemProgress per item — the batched
                # query above already has it (or knows it's missing). If this
                # creates a row (first-ever view), `row` here still reports the
                # status as of the batched query (None, i.e. not started) —
                # cosmetically stale for this one response, corrected on the
                # very next fetch once the row exists in that query too.
                quiz_order = await get_quiz_display_order(db, user_id=current.id, item=item, progress=row)
            payload = student_view(item, quiz_order=quiz_order)
            if item.kind == "video":
                payload["content"].update(await _video_state(db, item))
            if item.kind == "mission":
                payload["content"].update(await _mission_embed_state(db, item, current.id))
        else:
            payload = {"content": _preview_content(item.kind, item.content)}
            if item.kind == "video":
                payload["content"].update(await _video_state(db, item))
            if item.kind == "mission":
                payload["content"].update(await _mission_embed_state(db, item, current.id))

        item_payloads.append(ModuleItemOut(
            id=item.id,
            kind=item.kind,
            title=item.title,
            position=item.position,
            content=payload["content"],
            status=row.status if row else None,
        ))

    if enrolled:
        await db.commit()
    return ModuleOut(
        id=module.id,
        course_id=module.course_id,
        title=module.title,
        position=module.position,
        items=item_payloads,
    )


@router.get("/items/{video_item_id}/checkpoints", response_model=list[VideoCheckpointOut])
async def list_checkpoints(
    video_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    item = await _enrolled_item(db, current.id, video_item_id)
    if item.kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    rows = (await db.execute(
        select(VideoCheckpoint)
        .where(VideoCheckpoint.item_id == video_item_id)
        .order_by(VideoCheckpoint.start_seconds)
    )).scalars().all()
    return [sanitize_checkpoint(c) for c in rows]


# ── learner writes: enrolled (P1-6/D2 — role no longer gates this) ─────────

@router.get("/items/{item_id}/quiz/questions", response_model=ContentQuiz)
async def quiz_questions(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Re-fetch this quiz's current sample (random-N quizzes, 2026-09-01) —
    used by the player's Retry action to draw a fresh random N without
    re-fetching the whole module. `submit_quiz` always clears the stored
    sample first, so this naturally returns a new one after a submission."""
    item = await _enrolled_item(db, current.id, item_id)
    if item.kind != "quiz":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz item not found")
    quiz_order = await get_quiz_display_order(db, user_id=current.id, item=item)
    await db.commit()
    return student_view(item, quiz_order=quiz_order)["content"]


@router.post("/items/{item_id}/quiz/check", response_model=QuizAnswerCheckOut)
async def quiz_check_answer(
    item_id: uuid.UUID,
    body: QuizAnswerCheckIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Live, per-question feedback while stepping through a quiz — no
    grading/completion state touched, same posture as checkpoint_answer
    below. `quiz/submit` is still what actually records the attempt once
    every question's been answered; this just lets the player reveal
    correct/explanation as the student goes, one question at a time,
    instead of only at the end. Does record item_progress.hints_used
    (P2-3) so the points award can see it was used."""
    await _enrolled_item(db, current.id, item_id)
    return await check_quiz_answer(
        db, user_id=current.id, item_id=item_id, question_index=body.question_index, answer=body.answer,
    )


@router.post("/items/{item_id}/quiz/submit", response_model=QuizReviewOut)
async def quiz_submit(
    item_id: uuid.UUID,
    body: QuizAnswersIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Server-side grading (D7) — the review sheet returns after submission,
    which is exactly when the explanations are allowed to leave the server."""
    item = await _enrolled_item(db, current.id, item_id)
    result = await submit_quiz(
        db, user_id=current.id, item_id=item_id, answers=body.answers
    )
    await _award_certificates_for_item(db, current.id, item)
    await db.commit()
    return result


@router.post("/items/{video_item_id}/checkpoints/{checkpoint_id}/answer", response_model=CheckpointAnswerOut)
async def checkpoint_answer(
    video_item_id: uuid.UUID,
    checkpoint_id: uuid.UUID,
    body: CheckpointAnswerIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Stateless grading (checkpoint.py) — a checkpoint quiz gates playback,
    not module completion, so there's nothing to commit here."""
    await _enrolled_item(db, current.id, video_item_id)
    return await submit_checkpoint_answer(
        db, checkpoint_id=checkpoint_id, item_id=video_item_id, answer=body.answer,
    )


@router.get("/items/{item_id}/attachment/url", response_model=AttachmentUrlOut)
async def attachment_url(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """A signed URL is minted fresh per request (short-lived, same posture
    as every other resolve_url() call in this codebase) rather than baked
    into the module-read payload — keeps student_view() a plain sync
    function with no storage I/O in it."""
    item = await _enrolled_item(db, current.id, item_id)
    if item.kind != "attachment":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    bucket = item.content.get("bucket") if item.content else None
    path = item.content.get("path") if item.content else None
    if not bucket or not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No file uploaded for this attachment yet")
    url = await storage.get_signed_url(bucket, path)
    return AttachmentUrlOut(url=url, filename=item.content.get("filename"))


@router.post("/items/{item_id}/progress", response_model=ProgressOut)
async def submit_progress(
    item_id: uuid.UUID,
    body: ProgressIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    item = await _enrolled_item(db, current.id, item_id)
    row = await item_progress(db, user_id=current.id, item_id=item_id, action=body.action)
    await _award_certificates_for_item(db, current.id, item)
    await db.commit()
    return ProgressOut(
        status=row.status,
        quiz_attempts=row.quiz_attempts,
        best_score=float(row.best_score) if row.best_score is not None else None,
        completed_at=row.completed_at,
    )