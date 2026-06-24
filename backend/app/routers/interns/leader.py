from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.models.user import User
from app.models.interns.team import Team
from app.models.interns.task import Task
from app.models.interns.module import Module
from app.models.interns.epic import Epic
from app.core.dependencies import require_leader
from app.schemas.user import UserOut
from app.schemas.interns.team import TeamOut
from app.schemas.interns.epic import EpicOut, EpicUpdate
from app.schemas.interns.module import ModuleCreate, ModuleOut, ModuleUpdate
from app.services.interns import module as module_service
from app.schemas.interns.task import TaskCreate, TaskOut, TaskUpdate, TaskAssign
from app.schemas.interns.submission import TaskSubmissionOut, TaskSubmissionReview
from app.schemas.interns.proposal import ProposalOut, ProposalReview
from app.schemas.interns.mind_map import MindMapLayoutOut, MindMapLayoutUpdate, TaskMindMapNoteOut
from app.schemas.interns.project import ProjectOut

from app.services.interns import epic as epic_service
from app.services.interns import task as task_service
from app.services.interns import proposal as proposal_service
from app.services.interns import mind_map as mind_map_service
from app.services.interns import project as project_service

router = APIRouter(prefix="/leader", tags=["leader"])


async def _get_leader_team(db: AsyncSession, user: User) -> Team:
    result = await db.execute(select(Team).where(Team.leader_id == user.id))
    team = result.scalars().first()
    if not team:
        raise HTTPException(status_code=404, detail="No team found for this leader")
    return team


async def _verify_epic_access(db: AsyncSession, user: User, epic_id: UUID) -> Epic:
    epic = await epic_service.get_epic_by_id(db, epic_id)
    team = await _get_leader_team(db, user)
    if epic.team_id != team.id:
        raise HTTPException(status_code=403, detail="Not authorized for this epic")
    return epic


async def _verify_task_access(db: AsyncSession, user: User, task_id: UUID) -> Task:
    task = await task_service.get_task_by_id(db, task_id)
    team = await _get_leader_team(db, user)
    module_result = await db.execute(select(Module).where(Module.id == task.module_id))
    module = module_result.scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    epic_result = await db.execute(select(Epic).where(Epic.id == module.epic_id))
    epic = epic_result.scalars().first()
    if not epic or epic.team_id != team.id:
        raise HTTPException(status_code=403, detail="Not authorized for this task")
    return task


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/projects", response_model=List[ProjectOut])
async def read_projects(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    return await project_service.get_projects(db)


# ── Team ───────────────────────────────────────────────────────────────────────

@router.get("/team", response_model=TeamOut)
async def read_my_team(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    team = await _get_leader_team(db, current_user)
    result = await db.execute(select(Team).where(Team.id == team.id).options(selectinload(Team.members)))
    return result.scalars().first()


@router.get("/team/members", response_model=List[UserOut])
async def read_team_members(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    team = await _get_leader_team(db, current_user)
    result = await db.execute(
        select(Team).where(Team.id == team.id).options(selectinload(Team.members))
    )
    team_with_members = result.scalars().first()
    return team_with_members.members


# ── Epics ─────────────────────────────────────────────────────────────────────

@router.get("/epics", response_model=List[EpicOut])
async def read_my_epics(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    team = await _get_leader_team(db, current_user)
    return await epic_service.get_epics_by_team(db, team.id)

@router.get("/epics/{id}", response_model=EpicOut)
async def read_epic(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    return await epic_service.get_epic_by_id(db, id)

@router.patch("/epics/{id}", response_model=EpicOut)
async def update_epic(id: UUID, epic_in: EpicUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    await _verify_epic_access(db, current_user, id)
    return await epic_service.update_epic(db, id, epic_in)


# ── Modules ───────────────────────────────────────────────────────────────────

@router.post("/epics/{id}/modules", response_model=ModuleOut)
async def create_module(id: UUID, module_in: ModuleCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    await _verify_epic_access(db, current_user, id)
    return await module_service.create_module(db, id, module_in, current_user.id)

@router.patch("/modules/{id}", response_model=ModuleOut)
async def update_module(id: UUID, module_in: ModuleUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    module = await module_service.get_module_by_id(db, id)
    await _verify_epic_access(db, current_user, module.epic_id)
    return await module_service.update_module(db, id, module_in)

@router.delete("/modules/{id}")
async def delete_module(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    module = await module_service.get_module_by_id(db, id)
    await _verify_epic_access(db, current_user, module.epic_id)
    return await module_service.delete_module(db, id)


# ── Tasks ─────────────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=List[TaskOut])
async def read_my_tasks(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    team = await _get_leader_team(db, current_user)
    return await task_service.get_tasks_by_team(db, team.id)

@router.post("/modules/{id}/tasks", response_model=TaskOut)
async def create_task(id: UUID, task_in: TaskCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    return await task_service.create_task(db, id, task_in, current_user.id)

@router.patch("/tasks/{id}", response_model=TaskOut)
async def update_task(id: UUID, task_in: TaskUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    await _verify_task_access(db, current_user, id)
    return await task_service.update_task(db, id, task_in)

@router.delete("/tasks/{id}")
async def delete_task(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    await _verify_task_access(db, current_user, id)
    return await task_service.delete_task(db, id)

@router.post("/tasks/{id}/assign", response_model=TaskOut)
async def assign_task(id: UUID, assign_in: TaskAssign, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    await _verify_task_access(db, current_user, id)
    return await task_service.assign_task(db, id, assign_in)

@router.delete("/tasks/{id}/assign/{user_id}", response_model=TaskOut)
async def unassign_task(id: UUID, user_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    await _verify_task_access(db, current_user, id)
    return await task_service.unassign_task(db, id, user_id)


# ── Submissions ───────────────────────────────────────────────────────────────

@router.patch("/submissions/{id}/review", response_model=TaskSubmissionOut)
async def review_submission(id: UUID, review_in: TaskSubmissionReview, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    return await task_service.review_submission(db, id, review_in)


# ── Proposals ─────────────────────────────────────────────────────────────────

@router.get("/proposals", response_model=List[ProposalOut])
async def read_all_proposals(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    """All proposals across the leader's team epics."""
    team = await _get_leader_team(db, current_user)
    return await proposal_service.get_proposals_by_team(db, team.id)

@router.get("/epics/{id}/proposals", response_model=List[ProposalOut])
async def read_proposals(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    return await proposal_service.get_proposals_by_epic(db, id)

@router.patch("/proposals/{id}", response_model=ProposalOut)
async def review_proposal(id: UUID, review_in: ProposalReview, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    return await proposal_service.review_proposal(db, id, review_in, current_user.id)


# ── Mind map ──────────────────────────────────────────────────────────────────

@router.get("/epics/{id}/mind-map", response_model=MindMapLayoutOut)
async def get_mind_map(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    return await mind_map_service.get_or_create_layout(db, id)

@router.patch("/epics/{id}/mind-map", response_model=MindMapLayoutOut)
async def update_mind_map(id: UUID, layout_in: MindMapLayoutUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    return await mind_map_service.update_layout(db, id, layout_in)

@router.get("/tasks/{id}/mind-map-note", response_model=TaskMindMapNoteOut)
async def get_task_note(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    return await mind_map_service.get_or_create_task_note(db, id)


# ── Tracker ───────────────────────────────────────────────────────────────────

@router.get("/tracker/{user_id}", response_model=List[TaskOut])
async def get_user_tracker(user_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_leader)):
    """All tasks assigned to a specific intern — used by leader to view their team member's tracker."""
    return await task_service.get_tasks_assigned_to(db, user_id)
