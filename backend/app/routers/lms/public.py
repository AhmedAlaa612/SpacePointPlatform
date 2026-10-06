"""Public LMS storefront — `/public/courses*` + `/public/learning-paths*`.

Anonymous readers for the Learn landing/catalog/detail pages: anyone can
browse published courses and paths (with prices), login is only required to
enroll or buy. No auth dependency at all — per-user fields degrade to their
logged-out values:

* `enrolled` / `fully_owned` / `pct` — always False / 0 (nothing to check
  enrollment against without a caller).
* course `locked` — always False (prerequisites can't be evaluated without
  a user; the detail page still lists them, all unsatisfied).
* module locks — `unlock_state` with no progress rows, i.e. module-1-open,
  rest-locked, the same outline a not-yet-enrolled student sees.
* path step states — first course step `current`, rest `locked`, pct 0.

Invite-mode content is fully hidden (same rule as the authed catalog —
`_published_course`/`_published_path` with `user_id=None` always fail the
invite branch). Enroll, checkout, progress, and module-item reads stay
behind `/lms/*` auth — browsing is free, enrolling costs a login.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.lms import Course
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.user import User
from app.schemas.curriculum import PrerequisiteItemOut
from app.schemas.lms import (
    CourseCatalogOut,
    CourseDetailOut,
    LearningPathCatalogOut,
    LearningPathDetailOut,
    LearningPathStepOut,
    ModuleLockOut,
)
from app.services import storage
from app.services.curriculum import prerequisite_status
from app.services.lms import path_progress, path_total_duration_seconds, unlock_state

router = APIRouter(prefix="/public", tags=["public-lms"])


@router.get("/courses", response_model=list[CourseCatalogOut])
async def public_courses(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Published, non-invite courses for anonymous browsing (searchable)."""
    stmt = select(Course).where(Course.is_published.is_(True))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Course.title.ilike(pattern), Course.description.ilike(pattern)))
    rows = (await db.execute(stmt.order_by(Course.title))).scalars().all()
    rows = [c for c in rows if c.access_mode != "invite"]
    return [
        CourseCatalogOut(
            id=c.id, title=c.title, description=c.description, kind=c.kind,
            image_url=await storage.resolve_url(c.image_bucket, c.image_path),
            level=c.level, track=c.track,
            access_mode=c.access_mode, enrolled=False, locked=False,
            price_cents=c.price_cents, currency=c.currency,
        )
        for c in rows
    ]


@router.get("/courses/{course_id}", response_model=CourseDetailOut)
async def public_course_detail(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Published course outline for anonymous browsing. Drafts and
    invite-mode courses 404, exactly as for a caller with no enrollment."""
    course = await db.get(Course, course_id)
    if course is None or not course.is_published or course.access_mode == "invite":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

    locks = await unlock_state(db, user_id=None, course_id=course.id)  # type: ignore[arg-type]
    prereqs = await prerequisite_status(
        db, item_type="course", item_id=course.id, user_id=None,  # type: ignore[arg-type]
    )

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
        enrolled=False,
        is_published=course.is_published,
        is_preview=False,
        completed=False,
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
        locked=False,
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


@router.get("/learning-paths", response_model=list[LearningPathCatalogOut])
async def public_learning_paths(
    db: AsyncSession = Depends(get_db),
):
    """Published, non-invite learning paths for anonymous browsing."""
    paths = (await db.execute(
        select(LearningPath).where(LearningPath.is_published.is_(True)).order_by(LearningPath.title)
    )).scalars().all()

    out: list[LearningPathCatalogOut] = []
    for path in paths:
        if path.access_mode == "invite":
            continue
        steps = await _path_steps(db, path.id)
        progress = await path_progress(db, user_id=None, steps=steps)  # type: ignore[arg-type]
        duration = await path_total_duration_seconds(db, [s.course_id for s in steps])
        out.append(LearningPathCatalogOut(
            id=path.id, title=path.title, description=path.description,
            image_url=await storage.resolve_url(path.image_bucket, path.image_path),
            course_count=progress["course_count"], mission_count=progress["mission_count"],
            total_duration_seconds=duration, pct=0, enrolled=False,
            access_mode=path.access_mode,
            price_cents=path.price_cents, currency=path.currency,
            fully_owned=False,
        ))
    return out


@router.get("/learning-paths/{path_id}", response_model=LearningPathDetailOut)
async def public_learning_path_detail(
    path_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Published path outline for anonymous browsing. Drafts and invite-mode
    paths 404, exactly as for a caller with no enrollment."""
    path = await db.get(LearningPath, path_id)
    if path is None or not path.is_published or path.access_mode == "invite":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")
    steps = await _path_steps(db, path.id)
    progress = await path_progress(db, user_id=None, steps=steps)  # type: ignore[arg-type]
    duration = await path_total_duration_seconds(db, [s.course_id for s in steps])
    return LearningPathDetailOut(
        id=path.id, title=path.title, description=path.description,
        image_url=await storage.resolve_url(path.image_bucket, path.image_path),
        pct=0, course_count=progress["course_count"],
        mission_count=progress["mission_count"], total_duration_seconds=duration,
        steps=[LearningPathStepOut(**row) for row in progress["steps"]],
        access_mode=path.access_mode, enrolled=False,
        price_cents=path.price_cents, currency=path.currency, fully_owned=False,
    )


async def _path_steps(db: AsyncSession, path_id) -> list[LearningPathStep]:
    return list((await db.execute(
        select(LearningPathStep)
        .where(LearningPathStep.learning_path_id == path_id)
        .order_by(LearningPathStep.position)
    )).scalars().all())
