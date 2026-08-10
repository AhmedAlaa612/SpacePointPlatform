"""LMS student routes (LM1-3) — `/lms/*`.

Catalog and course outline are any-authenticated-user reads; module content
(the actual lessons), progress writes and quiz submissions are gated purely
on enrollment, not on holding the `student` role (P1-6, D2 — 2026-08-10:
"yes, staff can take LMS courses"). `require_lms_student` stays only on the
account-shaped routes: signup, `/my-courses`, `/my-activity`, `/enroll`, and
`/learning-paths/{id}/start` (a bulk variant of self-enrol). Not-enrolled is
a 404, never a 403 — a student (or an enrolled staff member) who hasn't
joined must not learn whether a course exists and is a particular course,
only that access is unavailable. Draft (unpublished) courses 404 from every
route for the same reason.

Every item payload flows through `student_view` (§2) — the answer-stripping
choke point — and the Pydantic response models (`extra="forbid"`) enforce the
leak guarantee a second time at the response boundary.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select

# from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_lms_student
from app.db.session import get_db
from app.models.lms import Course, CourseModule, Enrollment, ItemProgress, ModuleItem, ModuleVideo, VideoCheckpoint
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.user import User
from app.schemas.lms import (
    ActivityItemOut,
    AttachmentUrlOut,
    CheckpointAnswerIn,
    CheckpointAnswerOut,
    CourseCatalogOut,
    CourseDetailOut,
    EnrollIn,
    EnrollmentOut,
    LeaderboardEntryOut,
    LearningPathCatalogOut,
    LearningPathDetailOut,
    LearningPathStepOut,
    ModuleItemOut,
    ModuleLockOut,
    ModuleOut,
    MyCoursesOut,
    ProgressIn,
    ProgressOut,
    QuizAnswerCheckIn,
    QuizAnswerCheckOut,
    QuizAnswersIn,
    QuizReviewOut,
    VideoCheckpointOut,
)
from app.services.lms import (
    check_quiz_answer,
    course_completion,
    enroll,
    enrollment_is_active,
    item_progress,
    path_progress,
    path_total_duration_seconds,
    sanitize_checkpoint,
    student_view,
    submit_checkpoint_answer,
    submit_quiz,
    unlock_state,
)
from app.services.lms.dashboard import my_courses_dashboard, recent_activity
from app.services.lms.leaderboard import leaderboard
from app.services import storage

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
    """P1-7: `invite` courses list *with a lock* (access_mode + enrolled),
    never hidden — the catalog stays the full picture; access_mode is what
    the client renders "Enrol" / "Buy" / a lock icon from."""
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

    return [
        CourseCatalogOut(
            id=c.id, title=c.title, description=c.description, kind=c.kind,
            image_url=await storage.resolve_url(c.image_bucket, c.image_path),
            level=c.level, track=c.track,
            access_mode=c.access_mode, enrolled=c.id in enrolled_course_ids,
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
        modules=[
            ModuleLockOut(
                module_id=row["module_id"],
                title=row["title"],
                position=row["position"],
                locked=row["locked"],
                mandatory_total=row["mandatory_total"],
                mandatory_completed=row["mandatory_completed"],
            )
            for row in locks
        ],
    )


# ── learning paths (self-paced ordered course sequences) ────────────────────

async def _published_path(db: AsyncSession, path_id: uuid.UUID) -> LearningPath:
    path = await db.get(LearningPath, path_id)
    if path is None or not path.is_published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    return path


async def _path_steps(db: AsyncSession, path_id: uuid.UUID) -> list[LearningPathStep]:
    return list((await db.execute(
        select(LearningPathStep)
        .where(LearningPathStep.learning_path_id == path_id)
        .order_by(LearningPathStep.position)
    )).scalars().all())


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
        progress = await path_progress(db, user_id=current.id, steps=steps)
        duration = await path_total_duration_seconds(db, [s.course_id for s in steps])
        out.append(LearningPathCatalogOut(
            id=path.id, title=path.title, description=path.description,
            image_url=await storage.resolve_url(path.image_bucket, path.image_path),
            course_count=progress["course_count"], mission_count=progress["mission_count"],
            total_duration_seconds=duration, pct=progress["pct"],
        ))
    return out


@router.get("/learning-paths/{path_id}", response_model=LearningPathDetailOut)
async def learning_path_detail(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    path = await _published_path(db, path_id)
    steps = await _path_steps(db, path.id)
    progress = await path_progress(db, user_id=current.id, steps=steps)
    duration = await path_total_duration_seconds(db, [s.course_id for s in steps])
    return LearningPathDetailOut(
        id=path.id, title=path.title, description=path.description,
        image_url=await storage.resolve_url(path.image_bucket, path.image_path),
        pct=progress["pct"], course_count=progress["course_count"],
        mission_count=progress["mission_count"], total_duration_seconds=duration,
        steps=[LearningPathStepOut(**row) for row in progress["steps"]],
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

    Only `open` steps self-enrol (P1-6) — this bulk path is a shortcut for
    the same self-enrol `POST /lms/enroll` does, so it must respect the same
    access_mode gate (P1-4) rather than silently granting access to an
    invite-only or paid course the single-course endpoint would 403/402 on.
    A restricted step is just skipped; the rest of the path still starts."""
    path = await _published_path(db, path_id)
    steps = await _path_steps(db, path.id)
    for step in steps:
        course = await db.get(Course, step.course_id)
        if course is not None and course.access_mode == "open":
            await enroll(db, user_id=current.id, course_id=step.course_id, source="self")
    await db.commit()

    progress = await path_progress(db, user_id=current.id, steps=steps)
    duration = await path_total_duration_seconds(db, [s.course_id for s in steps])
    return LearningPathDetailOut(
        id=path.id, title=path.title, description=path.description,
        image_url=await storage.resolve_url(path.image_bucket, path.image_path),
        pct=progress["pct"], course_count=progress["course_count"],
        mission_count=progress["mission_count"], total_duration_seconds=duration,
        steps=[LearningPathStepOut(**row) for row in progress["steps"]],
    )


# ── dashboard: student only ──────────────────────────────────────────────────

@router.get("/my-courses", response_model=MyCoursesOut)
async def my_courses(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
):
    """Stats + resume pointer + per-course progress for the landing page's
    resume band and the /learn/my-courses dashboard (LMS redesign)."""
    return await my_courses_dashboard(db, user_id=current.id)


@router.get("/my-activity", response_model=list[ActivityItemOut])
async def my_activity(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
):
    """Last 10 completed items across every course — the profile page's
    activity feed."""
    return await recent_activity(db, user_id=current.id)


@router.get("/leaderboard", response_model=list[LeaderboardEntryOut])
async def get_leaderboard(
    scope: Literal["cohort", "global"] = "global",
    cohort_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """P2-4. ⚠️ Backend only — not linked from any student-facing page yet.
    D6 (scope + display-name policy) is still an open operator decision
    (PHASE2_EXECUTION_PLAN.md §2); `display_name` here is a private-by-
    default stand-in (first name + last-initial), not the real answer.
    Do not surface this in the frontend until D6 is actually settled."""
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
    (P1-5) gets them in; `paid` 402s with a plain "not available yet"
    message — real checkout is Stage S, not built yet, so this is the
    correct shape (right status code, right branch) without a fabricated
    payment flow behind it. Idempotent for `open` — enrolling again returns
    the same row; a reinstated or re-expired enrollment (re)activates in
    place."""
    course = await _published_course(db, body.course_id)

    if course.access_mode == "invite":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="This course is invite-only — ask an admin to grant you access",
        )
    if course.access_mode == "paid":
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="This course requires payment — checkout isn't available yet",
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
    video = (await db.execute(
        select(ModuleVideo).where(ModuleVideo.item_id == item.id)
    )).scalars().first()
    if video is None:
        return {"transcode_status": None, "duration_seconds": None}
    return {
        "transcode_status": video.transcode_status,
        "duration_seconds": video.duration_seconds,
    }


@router.get("/modules/{module_id}", response_model=ModuleOut)
async def module_read(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """The actual lessons — every item through `student_view`, plus this
    student's per-item status and the video transcode state the player needs."""
    module = await db.get(CourseModule, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    await _assert_enrolled(db, current.id, module.course_id)

    items = (await db.execute(
        select(ModuleItem).where(ModuleItem.module_id == module_id).order_by(ModuleItem.position)
    )).scalars().all()

    progress_rows = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == current.id,
            ItemProgress.item_id.in_([i.id for i in items]),
        )
    )).scalars().all()
    progress_map = {p.item_id: p for p in progress_rows}

    item_payloads: list[ModuleItemOut] = []
    for item in items:
        payload = student_view(item)
        if item.kind == "video":
            payload["content"].update(await _video_state(db, item))
        row = progress_map.get(item.id)
        item_payloads.append(ModuleItemOut(
            id=item.id,
            kind=item.kind,
            title=item.title,
            position=item.position,
            content=payload["content"],
            status=row.status if row else None,
        ))

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
    await _enrolled_item(db, current.id, item_id)
    result = await submit_quiz(
        db, user_id=current.id, item_id=item_id, answers=body.answers
    )
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
    await _enrolled_item(db, current.id, item_id)
    row = await item_progress(db, user_id=current.id, item_id=item_id, action=body.action)
    await db.commit()
    return ProgressOut(
        status=row.status,
        quiz_attempts=row.quiz_attempts,
        best_score=float(row.best_score) if row.best_score is not None else None,
        completed_at=row.completed_at,
    )