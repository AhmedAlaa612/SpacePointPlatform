from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.models.user import User
from app.core.dependencies import require_intern
from app.schemas.interns.task import TaskOut, TaskStatusUpdate
from app.schemas.interns.submission import TaskSubmissionCreate, TaskSubmissionOut
from app.schemas.interns.proposal import ProposalCreate, ProposalOut
from app.schemas.interns.mind_map import TaskMindMapNoteUpdate, TaskMindMapNoteOut, MindMapLayoutOut
from app.schemas.interns.epic import EpicOut
from app.schemas.interns.project import ProjectOut
from app.schemas.interns.team import TeamOut
from app.models.interns.team import Team, team_members

from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.services.interns import task as task_service
from app.services.interns import proposal as proposal_service
from app.services.interns import mind_map as mind_map_service
from app.services.interns import epic as epic_service
from app.services.interns import project as project_service

router = APIRouter(prefix="/intern", tags=["intern"])


async def _verify_intern_task_access(db: AsyncSession, user: User, task_id: UUID):
    task = await task_service.get_task_by_id(db, task_id)
    if user not in task.assignees:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this task")
    return task


# â”€â”€ Projects â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/projects", response_model=List[ProjectOut])
async def read_projects(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    return await project_service.get_projects(db)


# â”€â”€ Tasks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/tasks", response_model=List[TaskOut])
async def read_my_tasks(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    return await task_service.get_tasks_assigned_to(db, current_user.id)

@router.patch("/tasks/{id}/status", response_model=TaskOut)
async def update_task_status(id: UUID, status_in: TaskStatusUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    await _verify_intern_task_access(db, current_user, id)
    return await task_service.update_task_status(db, id, status_in)

@router.post("/tasks/{id}/submit", response_model=TaskSubmissionOut)
async def submit_work(id: UUID, submit_in: TaskSubmissionCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    await _verify_intern_task_access(db, current_user, id)
    return await task_service.submit_task_work(db, id, submit_in, current_user.id)


# â”€â”€ Team â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/team", response_model=TeamOut)
async def read_my_team(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    result = await db.execute(
        select(Team)
        .join(team_members, Team.id == team_members.c.team_id)
        .where(team_members.c.user_id == current_user.id)
        .options(selectinload(Team.members))
    )
    team = result.scalars().first()
    if not team:
        raise HTTPException(status_code=404, detail="Not assigned to any team")
    return team


# â”€â”€ Proposals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/proposals", response_model=List[ProposalOut])
async def read_my_proposals(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    return await proposal_service.get_proposals_by_user(db, current_user.id)

@router.post("/epics/{id}/proposals", response_model=ProposalOut)
async def create_proposal(id: UUID, proposal_in: ProposalCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    return await proposal_service.create_proposal(db, id, proposal_in, current_user.id)


# â”€â”€ Mind map notes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.patch("/tasks/{id}/mind-map-note", response_model=TaskMindMapNoteOut)
async def update_task_note(id: UUID, note_in: TaskMindMapNoteUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    await _verify_intern_task_access(db, current_user, id)
    return await mind_map_service.update_task_note(db, id, note_in, current_user.id)

@router.get("/tasks/{id}/mind-map-note", response_model=TaskMindMapNoteOut)
async def get_task_note(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    await _verify_intern_task_access(db, current_user, id)
    return await mind_map_service.get_or_create_task_note(db, id)


# â”€â”€ Mind map (read-only epic structure + layout) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/epics/{id}", response_model=EpicOut)
async def read_epic(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    return await epic_service.get_epic_by_id(db, id)

@router.get("/epics/{id}/mind-map", response_model=MindMapLayoutOut)
async def get_mind_map(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    return await mind_map_service.get_or_create_layout(db, id)
