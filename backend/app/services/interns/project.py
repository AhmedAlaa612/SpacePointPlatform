from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from uuid import UUID
from app.models.interns.project import Project
from app.schemas.interns.project import ProjectCreate, ProjectUpdate
from app.services.interns.team import get_team_by_id

async def create_project(db: AsyncSession, project_in: ProjectCreate, user_id: UUID) -> Project:
    db_project = Project(
        title=project_in.title,
        description=project_in.description,
        created_by=user_id
    )
    db.add(db_project)
    await db.commit()
    # Re-query with selectinload — async sessions can't lazy-load relationships
    result = await db.execute(
        select(Project).where(Project.id == db_project.id).options(selectinload(Project.teams))
    )
    return result.scalars().first()

async def get_projects(db: AsyncSession):
    result = await db.execute(select(Project).options(selectinload(Project.teams)))
    return result.scalars().all()

async def get_project_by_id(db: AsyncSession, project_id: UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id).options(selectinload(Project.teams)))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project

async def update_project(db: AsyncSession, project_id: UUID, project_in: ProjectUpdate) -> Project:
    project = await get_project_by_id(db, project_id)
    update_data = project_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project

async def delete_project(db: AsyncSession, project_id: UUID):
    project = await get_project_by_id(db, project_id)
    await db.delete(project)
    await db.commit()
    return {"detail": "Project deleted"}

async def assign_team_to_project(db: AsyncSession, project_id: UUID, team_id: UUID) -> Project:
    project = await get_project_by_id(db, project_id)
    team = await get_team_by_id(db, team_id)
    if team in project.teams:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Team already assigned to project")
    project.teams.append(team)
    await db.commit()
    await db.refresh(project)
    return project

async def remove_team_from_project(db: AsyncSession, project_id: UUID, team_id: UUID) -> Project:
    project = await get_project_by_id(db, project_id)
    team = await get_team_by_id(db, team_id)
    if team not in project.teams:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Team not assigned to project")
    project.teams.remove(team)
    await db.commit()
    await db.refresh(project)
    return project
