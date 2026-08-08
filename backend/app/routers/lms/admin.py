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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_lms_content
from app.db.session import get_db
from app.models.lms import (
    Course, CourseModule, Enrollment, ModuleItem, ModuleVideo, ProgramCurriculum, VideoCheckpoint,
)
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.sessions.program import Program
from app.models.user import User
from app.schemas.lms_admin import (
    AdminCheckpointNoteContent,
    AdminCheckpointQuizContent,
    AdminContentFlashcards,
    AdminContentQuiz,
    AdminContentText,
    AdminContentVideo,
    CourseAdminOut,
    CourseCreate,
    CourseUpdate,
    CurriculumEntryIn,
    CurriculumEntryOut,
    InstructorOptionOut,
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
    VideoCheckpointAdminOut,
    VideoCheckpointCreate,
    VideoCheckpointUpdate,
)
from app.services import storage

router = APIRouter(prefix="/lms/admin", tags=["lms-admin"])

COURSE_IMAGE_BUCKET = "lms-course-images"
LEARNING_PATH_IMAGE_BUCKET = "lms-learning-path-images"
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB — a cover image, not a dataset


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
    )

_CONTENT_MODEL = {
    "text": AdminContentText,
    "quiz": AdminContentQuiz,
    "flashcards": AdminContentFlashcards,
    "video": AdminContentVideo,
}


def _validated_content(*, kind: str, content: dict) -> dict:
    model = _CONTENT_MODEL.get(kind)
    if model is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown item kind '{kind}'")
    try:
        parsed = model(**content)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.errors())
    return parsed.model_dump()


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
