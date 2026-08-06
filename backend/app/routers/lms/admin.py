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
from app.models.lms import Course, CourseModule, Enrollment, ModuleItem, ModuleVideo, ProgramCurriculum
from app.models.sessions.program import Program
from app.models.user import User
from app.schemas.lms_admin import (
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
    ModuleAdminOut,
    ModuleCreate,
    ModuleReorderIn,
    ModuleUpdate,
)
from app.services import storage

router = APIRouter(prefix="/lms/admin", tags=["lms-admin"])

COURSE_IMAGE_BUCKET = "lms-course-images"
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


async def _validated_content(db: AsyncSession, *, kind: str, module_id: uuid.UUID, content: dict) -> dict:
    model = _CONTENT_MODEL.get(kind)
    if model is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown item kind '{kind}'")
    try:
        parsed = model(**content)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=exc.errors())

    if kind == "quiz" and parsed.mid_video_at_seconds is not None:
        video_count = await db.scalar(
            select(func.count()).select_from(ModuleItem).where(
                ModuleItem.module_id == module_id, ModuleItem.kind == "video"
            )
        )
        if video_count != 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="mid_video_at_seconds requires the module to have exactly one video item",
            )
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

    content = await _validated_content(db, kind=body.kind, module_id=module_id, content=body.content)

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
        changes["content"] = await _validated_content(
            db, kind=item.kind, module_id=item.module_id, content=changes["content"]
        )
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
