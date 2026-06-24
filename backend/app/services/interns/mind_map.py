from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID
from datetime import datetime, timezone

from app.models.interns.mind_map import MindMapLayout, TaskMindMapNote
from app.schemas.interns.mind_map import MindMapLayoutUpdate, TaskMindMapNoteUpdate


async def get_or_create_layout(db: AsyncSession, epic_id: UUID) -> MindMapLayout:
    result = await db.execute(
        select(MindMapLayout).where(MindMapLayout.epic_id == epic_id)
    )
    layout = result.scalars().first()
    if not layout:
        layout = MindMapLayout(epic_id=epic_id, layout={})
        db.add(layout)
        await db.commit()
        await db.refresh(layout)
    return layout


async def update_layout(
    db: AsyncSession, epic_id: UUID, layout_in: MindMapLayoutUpdate
) -> MindMapLayout:
    layout = await get_or_create_layout(db, epic_id)
    layout.layout = layout_in.layout
    layout.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(layout)
    return layout


async def get_or_create_task_note(db: AsyncSession, task_id: UUID) -> TaskMindMapNote:
    result = await db.execute(
        select(TaskMindMapNote).where(TaskMindMapNote.task_id == task_id)
    )
    note = result.scalars().first()
    if not note:
        note = TaskMindMapNote(task_id=task_id, note=None)
        db.add(note)
        await db.commit()
        await db.refresh(note)
    return note


async def update_task_note(
    db: AsyncSession, task_id: UUID, note_in: TaskMindMapNoteUpdate, user_id: UUID
) -> TaskMindMapNote:
    note = await get_or_create_task_note(db, task_id)
    note.note = note_in.note
    note.updated_by = user_id
    note.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(note)
    return note
