"""LMS student routes (LM1-3) — `/lms/*`.

Catalog and course outline are any-authenticated-user reads; module content
(the actual lessons), progress writes and quiz submissions are
`require_lms_student` **and** enrolled. Not-enrolled is a 404, never a 403 —
a student who hasn't joined must not learn whether a course exists and is a
particular course, only that access is unavailable. Draft (unpublished)
courses 404 from every route for the same reason.

Every item payload flows through `student_view` (§2) — the answer-stripping
choke point — and the Pydantic response models (`extra="forbid"`) enforce the
leak guarantee a second time at the response boundary.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

# from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_lms_student
from app.db.session import get_db
from app.models.lms import Course, CourseModule, Enrollment, ItemProgress, ModuleItem, ModuleVideo
from app.models.user import User
from app.schemas.lms import (
    CourseCatalogOut,
    CourseDetailOut,
    EnrollIn,
    EnrollmentOut,
    ModuleItemOut,
    ModuleLockOut,
    ModuleOut,
    MyCoursesOut,
    ProgressIn,
    ProgressOut,
    QuizAnswersIn,
    QuizReviewOut,
)
from app.services.lms import (
    course_completion,
    enroll,
    item_progress,
    student_view,
    submit_quiz,
    unlock_state,
)
from app.services.lms.dashboard import my_courses_dashboard
from app.services import storage

router = APIRouter(prefix="/lms", tags=["lms"])


async def _assert_enrolled(
    db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID
) -> None:
    """Flat 404 for "not enrolled" *and* for "unknown course" — the two are
    indistinguishable on purpose (don't leak existence, LM1-3 spec)."""
    enrollment = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user_id,
            Enrollment.course_id == course_id,
            Enrollment.status == "active",
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


async def _published_course(db: AsyncSession, course_id: uuid.UUID) -> Course:
    course = await db.get(Course, course_id)
    if course is None or not course.is_published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


# ── catalog + course outline: any authenticated user ────────────────────────

@router.get("/catalog", response_model=list[CourseCatalogOut])
async def catalog(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    rows = (await db.execute(
        select(Course)
        .where(Course.is_published.is_(True))
        .order_by(Course.title)
    )).scalars().all()
    return [
        CourseCatalogOut(
            id=c.id, title=c.title, description=c.description, kind=c.kind,
            image_url=await storage.resolve_url(c.image_bucket, c.image_path),
            level=c.level, track=c.track,
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
    course = await _published_course(db, course_id)

    enrolled_row = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == current.id,
            Enrollment.course_id == course.id,
            Enrollment.status == "active",
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


# ── dashboard: student only ──────────────────────────────────────────────────

@router.get("/my-courses", response_model=MyCoursesOut)
async def my_courses(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
):
    """Stats + resume pointer + per-course progress for the landing page's
    resume band and the /learn/my-courses dashboard (LMS redesign)."""
    return await my_courses_dashboard(db, user_id=current.id)


# ── enrollment: student only ────────────────────────────────────────────────

@router.post("/enroll", response_model=EnrollmentOut)
async def enroll_self(
    body: EnrollIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
):
    """Self-enrol from the catalog (D8 source='self'). Idempotent — enrolling
    again returns the same row; a reinstated account reactivates in place."""
    await _published_course(db, body.course_id)
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
    current: User = Depends(require_lms_student),
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


# ── learner writes: student AND enrolled ────────────────────────────────────

@router.post("/items/{item_id}/quiz/submit", response_model=QuizReviewOut)
async def quiz_submit(
    item_id: uuid.UUID,
    body: QuizAnswersIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
):
    """Server-side grading (D7) — the review sheet returns after submission,
    which is exactly when the explanations are allowed to leave the server."""
    await _enrolled_item(db, current.id, item_id)
    result = await submit_quiz(
        db, user_id=current.id, item_id=item_id, answers=body.answers
    )
    await db.commit()
    return result


@router.post("/items/{item_id}/progress", response_model=ProgressOut)
async def submit_progress(
    item_id: uuid.UUID,
    body: ProgressIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
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