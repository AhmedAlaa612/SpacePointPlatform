"""Mission embedding inside a course (P5-5) — `module_items.kind='mission'`,
`content = {mission_id, variant_id?}`.

Rule ① (PHASE2_EXECUTION_PLAN.md Stage 5): a mission item's completion is
never client-assertable — there is no entry for it in
`services/lms/progress.py::_ACTION_KINDS`. `decide_attempt` calls
`complete_embedded_items` directly on a pass, exactly as `submit_quiz`
writes `ItemProgress` itself for a quiz item — the client never gets a path
to mark this done on its own say-so.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import CourseModule, ModuleItem
from app.models.lms.enrollment import Enrollment, ItemProgress
from app.services.lms.enrollment import enrollment_is_active


async def _progress_row(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> ItemProgress:
    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == user_id, ItemProgress.item_id == item_id)
    )).scalars().first()
    if row is None:
        row = ItemProgress(id=uuid.uuid4(), user_id=user_id, item_id=item_id, status="not_started", quiz_attempts=0)
        db.add(row)
    return row


async def complete_embedded_items(
    db: AsyncSession, *, mission_id: uuid.UUID, variant_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """A mission attempt just passed — complete every `module_item` that
    embeds this exact mission (and, if the item pins a variant, only when
    that variant is the one that just passed), for every course the student
    holds an active enrollment in. A standalone attempt (the common case,
    P5-4) touches no module_items at all — this is a no-op unless embedding
    is actually in play.
    """
    items = (await db.execute(
        select(ModuleItem).where(
            ModuleItem.kind == "mission",
            ModuleItem.content["mission_id"].astext == str(mission_id),
        )
    )).scalars().all()
    if not items:
        return

    for item in items:
        pinned_variant = (item.content or {}).get("variant_id")
        if pinned_variant and pinned_variant != str(variant_id):
            continue
        module = await db.get(CourseModule, item.module_id)
        if module is None:
            continue
        enrollment = (await db.execute(
            select(Enrollment).where(
                Enrollment.user_id == user_id, Enrollment.course_id == module.course_id, *enrollment_is_active(),
            )
        )).scalars().first()
        if enrollment is None:
            continue
        row = await _progress_row(db, user_id, item.id)
        if row.status != "completed":
            row.status = "completed"
            row.completed_at = datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
    await db.flush()
