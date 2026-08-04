"""LMS progress services (LM1-2) — per-item writes, unlock, derived completion.

Completion is never stored (the whole point of the `item_progress` design):
`course_completion` and `unlock_state` read the raw per-item rows and derive
the answer each time, so there is no flag to go stale when a student's
progress changes or an author edits an item's `is_required` mid-course.

Unlock (D6) is a strict linear chain: module *n* is open iff every mandatory
item of module *n-1* is completed. A module with no mandatory items is done
vacuously, so it never blocks the next one. Optional items never block unlock,
whatever their status.

`item_progress` is deliberately strict about actions: a quiz item may only be
marked `quiz-attempt` (in_progress) here — the only way a quiz becomes
`completed` is a passing `submit_quiz` in services/lms/quiz.py. The client is
never trusted to mark work done on a path whose answer it shouldn't know.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import Course, CourseModule, ModuleItem
from app.models.lms.enrollment import ItemProgress

# action -> the item kinds that action is meaningful for. Completed-producing
# actions are only ever legal on kinds whose content the student is allowed to
# see fully; a quiz's completion goes through submit_quiz alone.
_ACTION_KINDS: dict[str, set[str]] = {
    "video-watched": {"video"},
    "text-viewed": {"text"},
    "quiz-attempt": {"quiz"},
    "flashcards-skipped": {"flashcards"},
}

# action -> resulting status
_ACTION_STATUS: dict[str, str] = {
    "video-watched": "completed",
    "text-viewed": "completed",
    "quiz-attempt": "in_progress",
    "flashcards-skipped": "skipped",
}

COMPLETED_STATUSES = ("completed", "skipped")


async def _progress_row(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> ItemProgress:
    row = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == user_id,
            ItemProgress.item_id == item_id,
        )
    )).scalars().first()
    if row is None:
        row = ItemProgress(
            id=uuid.uuid4(),
            user_id=user_id,
            item_id=item_id,
            status="not_started",
            quiz_attempts=0,
        )
        db.add(row)
    return row


async def item_progress(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    action: str,
) -> ItemProgress:
    """One write path for `video-watched`, `text-viewed`, `quiz-attempt` and
    `flashcards-skipped`. Rejects actions that don't apply to the item's kind
    — notably, nothing here can complete a quiz."""
    item = await db.get(ModuleItem, item_id)
    if item is None:
        raise HTTPException(404, detail="Item not found")

    allowed = _ACTION_KINDS.get(action)
    if allowed is None:
        raise HTTPException(400, detail=f"Unknown progress action: {action}")
    if item.kind not in allowed:
        raise HTTPException(
            400,
            detail=f"Action '{action}' does not apply to a {item.kind} item",
        )

    row = await _progress_row(db, user_id, item_id)
    row.updated_at = datetime.now(timezone.utc)
    row.status = _ACTION_STATUS[action]
    if row.status in ("completed", "skipped") and row.completed_at is None:
        row.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return row


async def _module_progress(
    db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID
) -> list[dict]:
    """Ordered modules with their mandatory-item tallies for one student.

    `mandatory_completed` counts only required items with a completed status
    (skipped counts too — an optional item that was skipped still counts as
    done, and a mandatory one can't be skipped through this API anyway).
    """
    modules = (await db.execute(
        select(CourseModule)
        .where(CourseModule.course_id == course_id)
        .order_by(CourseModule.position)
    )).scalars().all()

    items = (await db.execute(
        select(ModuleItem).where(ModuleItem.module_id.in_([m.id for m in modules]))
    )).scalars().all()
    progress = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == user_id,
            ItemProgress.item_id.in_([i.id for i in items]),
        )
    )).scalars().all()
    progress_by_item = {p.item_id: p for p in progress}

    by_module: dict[uuid.UUID, list[ModuleItem]] = {}
    for i in items:
        by_module.setdefault(i.module_id, []).append(i)

    rows = []
    for m in modules:
        mandatory = [i for i in by_module.get(m.id, []) if i.is_required]
        completed = sum(
            1 for i in mandatory if progress_by_item.get(i.id) is not None
            and progress_by_item[i.id].status in COMPLETED_STATUSES
        )
        rows.append({
            "module_id": m.id,
            "title": m.title,
            "position": m.position,
            "mandatory_total": len(mandatory),
            "mandatory_completed": completed,
        })
    return rows


async def unlock_state(
    db: AsyncSession, *, user_id: uuid.UUID, course_id: uuid.UUID
) -> list[dict]:
    """Which modules are open, in order (D6): the first module whose previous
    module's mandatory items are not all complete is locked, and everything
    after it is locked too — a locked linear sequence per student."""
    rows = await _module_progress(db, user_id, course_id)
    locked = False
    for row in rows:
        row["locked"] = locked
        if not locked and row["mandatory_completed"] < row["mandatory_total"]:
            # this module blocks every module after it until it's done
            locked = True
    return rows


async def course_completion(
    db: AsyncSession, *, user_id: uuid.UUID, course_id: uuid.UUID
) -> dict:
    """Derived completion: a module is done when every mandatory item in it is
    completed; the course is done when every module is done. Returns the
    per-module tallies alongside the overall flag so the instructor view
    (LM1-10) can render progress, not just the final state."""
    rows = await _module_progress(db, user_id, course_id)
    for row in rows:
        row["completed"] = row["mandatory_total"] == 0 or (
            row["mandatory_completed"] == row["mandatory_total"]
        )
    return {
        "course_id": course_id,
        "completed": all(r["completed"] for r in rows),
        "modules": rows,
    }