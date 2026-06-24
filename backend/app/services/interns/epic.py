from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from uuid import UUID

from app.models.interns.epic import Epic
from app.models.interns.module import Module
from app.models.interns.task import Task
from app.models.interns.team import Team
from app.schemas.interns.epic import EpicCreate, EpicUpdate


def _epic_options():
    return [
        selectinload(Epic.modules).selectinload(Module.tasks).selectinload(Task.assignees),
        selectinload(Epic.team).selectinload(Team.leader),
    ]


async def create_epic(db: AsyncSession, project_id: UUID, epic_in: EpicCreate, user_id: UUID) -> Epic:
    epic = Epic(
        project_id=project_id,
        team_id=epic_in.team_id,
        title=epic_in.title,
        description=epic_in.description,
        created_by=user_id,
    )
    db.add(epic)
    await db.flush()   # get the epic id before creating default module

    default_module = Module(
        epic_id=epic.id,
        title="General",
        created_by=user_id,
    )
    db.add(default_module)
    await db.commit()
    return await get_epic_by_id(db, epic.id)


async def get_epics_by_project(db: AsyncSession, project_id: UUID):
    result = await db.execute(
        select(Epic).where(Epic.project_id == project_id).options(*_epic_options())
    )
    return result.scalars().all()


async def get_all_epics(db: AsyncSession):
    result = await db.execute(select(Epic).options(*_epic_options()))
    return result.scalars().all()


async def get_epics_by_team(db: AsyncSession, team_id: UUID):
    result = await db.execute(
        select(Epic).where(Epic.team_id == team_id).options(*_epic_options())
    )
    return result.scalars().all()


async def get_epic_by_id(db: AsyncSession, epic_id: UUID) -> Epic:
    result = await db.execute(
        select(Epic).where(Epic.id == epic_id).options(*_epic_options())
    )
    epic = result.scalars().first()
    if not epic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Epic not found")
    return epic


async def update_epic(db: AsyncSession, epic_id: UUID, epic_in: EpicUpdate) -> Epic:
    epic = await get_epic_by_id(db, epic_id)
    for field, value in epic_in.dict(exclude_unset=True).items():
        setattr(epic, field, value)
    await db.commit()
    return await get_epic_by_id(db, epic_id)


async def delete_epic(db: AsyncSession, epic_id: UUID):
    epic = await get_epic_by_id(db, epic_id)
    await db.delete(epic)
    await db.commit()
    return {"detail": "Epic deleted"}
