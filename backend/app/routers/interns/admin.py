from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from app.core.config import settings
from app.db.session import get_db
from app.models.certificate import Certificate
from app.models.enums import CertificateType
from app.models.intern_letter import InternLetter
from app.models.user import User
from app.core.dependencies import require_admin
from app.services import storage
from app.services.documents.certificate import generate_completion_certificate_pdf
from app.services.documents.intern_letters import generate_intern_letter_pdf
from app.schemas.interns.team import TeamCreate, TeamOut, TeamUpdate
from app.schemas.interns.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.schemas.interns.epic import EpicCreate, EpicOut, EpicUpdate
from app.schemas.interns.module import ModuleCreate, ModuleOut, ModuleUpdate
from app.schemas.interns.task import TaskCreate, TaskOut, TaskUpdate, TaskAssign
from app.schemas.interns.submission import TaskSubmissionOut, TaskSubmissionReview
from app.schemas.interns.proposal import ProposalOut, ProposalReview
from app.schemas.interns.mind_map import MindMapLayoutOut, MindMapLayoutUpdate, TaskMindMapNoteOut

from app.services.interns import team as team_service
from app.services.interns import project as project_service
from app.services.interns import epic as epic_service
from app.services.interns import module as module_service
from app.services.interns import task as task_service
from app.services.interns import proposal as proposal_service
from app.services.interns import mind_map as mind_map_service

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Documents (PLAN §9.1) — manual admin triggers, no auto status lifecycle ───

@router.post("/users/{id}/confirmation-letter")
async def generate_confirmation_letter(
    id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    user = await db.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    start_date = user.created_at.strftime("%d %B %Y").lstrip("0")
    pdf_bytes = generate_intern_letter_pdf(
        user.full_name, "confirmation", start_date, None,
        settings.DEFAULT_SIGNATORY_NAME, settings.DEFAULT_SIGNATORY_TITLE,
    )
    file_url = await storage.upload_file("intern-letters", f"{id}/confirmation.pdf", pdf_bytes, "application/pdf")
    db.add(InternLetter(user_id=id, type="confirmation", file_url=file_url))
    await db.commit()
    return {"file_url": file_url}


@router.post("/users/{id}/completion-letter")
async def generate_completion_letter(
    id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    user = await db.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    start_date = user.created_at.strftime("%d %B %Y").lstrip("0")
    end_date = date.today().strftime("%d %B %Y").lstrip("0")
    pdf_bytes = generate_intern_letter_pdf(
        user.full_name, "completion", start_date, end_date,
        settings.DEFAULT_SIGNATORY_NAME, settings.DEFAULT_SIGNATORY_TITLE,
    )
    file_url = await storage.upload_file("intern-letters", f"{id}/completion.pdf", pdf_bytes, "application/pdf")
    db.add(InternLetter(user_id=id, type="completion", file_url=file_url))
    await db.commit()
    return {"file_url": file_url}


@router.post("/users/{id}/certificate")
async def generate_internship_certificate(
    id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    user = await db.get(User, id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    pdf_bytes = generate_completion_certificate_pdf(user.full_name, "Internship Program")
    file_url = await storage.upload_file(
        "certificates", f"{id}/internship_completion.pdf", pdf_bytes, "application/pdf"
    )
    db.add(Certificate(
        user_id=id, type=CertificateType.internship_completion, file_url=file_url,
        generated_by=current_user.id,
    ))
    await db.commit()
    return {"file_url": file_url}


# ── Teams ─────────────────────────────────────────────────────────────────────

@router.post("/teams", response_model=TeamOut)
async def create_team(team_in: TeamCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await team_service.create_team(db, team_in)

@router.get("/teams", response_model=List[TeamOut])
async def read_teams(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await team_service.get_teams(db)

@router.patch("/teams/{id}", response_model=TeamOut)
async def update_team(id: UUID, team_in: TeamUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await team_service.update_team(db, id, team_in)

@router.delete("/teams/{id}")
async def delete_team(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await team_service.delete_team(db, id)

@router.post("/teams/{id}/members", response_model=TeamOut)
async def add_team_member(id: UUID, user_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await team_service.add_member(db, id, user_id)

@router.delete("/teams/{id}/members/{user_id}", response_model=TeamOut)
async def remove_team_member(id: UUID, user_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await team_service.remove_member(db, id, user_id)


# ── Projects ──────────────────────────────────────────────────────────────────

@router.post("/projects", response_model=ProjectOut)
async def create_project(project_in: ProjectCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await project_service.create_project(db, project_in, current_user.id)

@router.get("/projects", response_model=List[ProjectOut])
async def read_projects(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await project_service.get_projects(db)

@router.get("/projects/{id}", response_model=ProjectOut)
async def read_project(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await project_service.get_project_by_id(db, id)

@router.patch("/projects/{id}", response_model=ProjectOut)
async def update_project(id: UUID, project_in: ProjectUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await project_service.update_project(db, id, project_in)

@router.delete("/projects/{id}")
async def delete_project(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await project_service.delete_project(db, id)

@router.post("/projects/{id}/teams", response_model=ProjectOut)
async def assign_team(id: UUID, team_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await project_service.assign_team_to_project(db, id, team_id)

@router.delete("/projects/{id}/teams/{team_id}", response_model=ProjectOut)
async def unassign_team(id: UUID, team_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await project_service.remove_team_from_project(db, id, team_id)


# ── Epics ─────────────────────────────────────────────────────────────────────

@router.get("/epics", response_model=List[EpicOut])
async def read_all_epics(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await epic_service.get_all_epics(db)

@router.post("/projects/{id}/epics", response_model=EpicOut)
async def create_epic(id: UUID, epic_in: EpicCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await epic_service.create_epic(db, id, epic_in, current_user.id)

@router.get("/projects/{id}/epics", response_model=List[EpicOut])
async def read_epics(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await epic_service.get_epics_by_project(db, id)

@router.get("/epics/{id}", response_model=EpicOut)
async def read_epic(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await epic_service.get_epic_by_id(db, id)

@router.patch("/epics/{id}", response_model=EpicOut)
async def update_epic(id: UUID, epic_in: EpicUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await epic_service.update_epic(db, id, epic_in)

@router.delete("/epics/{id}")
async def delete_epic(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await epic_service.delete_epic(db, id)


# ── Modules ───────────────────────────────────────────────────────────────────

@router.post("/epics/{id}/modules", response_model=ModuleOut)
async def create_module(id: UUID, module_in: ModuleCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await module_service.create_module(db, id, module_in, current_user.id)

@router.patch("/modules/{id}", response_model=ModuleOut)
async def update_module(id: UUID, module_in: ModuleUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await module_service.update_module(db, id, module_in)

@router.delete("/modules/{id}")
async def delete_module(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await module_service.delete_module(db, id)


# ── Tasks ─────────────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=List[TaskOut])
async def read_all_tasks(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await task_service.get_all_tasks(db)

@router.get("/tasks/{id}", response_model=TaskOut)
async def read_task(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await task_service.get_task_by_id(db, id)

@router.get("/tasks/{id}/mind-map-note", response_model=TaskMindMapNoteOut)
async def get_task_note(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await mind_map_service.get_or_create_task_note(db, id)

@router.post("/modules/{id}/tasks", response_model=TaskOut)
async def create_task(id: UUID, task_in: TaskCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await task_service.create_task(db, id, task_in, current_user.id)

@router.patch("/tasks/{id}", response_model=TaskOut)
async def update_task(id: UUID, task_in: TaskUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await task_service.update_task(db, id, task_in)

@router.delete("/tasks/{id}")
async def delete_task(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await task_service.delete_task(db, id)

@router.post("/tasks/{id}/assign", response_model=TaskOut)
async def assign_task(id: UUID, assign_in: TaskAssign, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await task_service.assign_task(db, id, assign_in)


# ── Submissions ───────────────────────────────────────────────────────────────

@router.patch("/submissions/{id}/review", response_model=TaskSubmissionOut)
async def review_submission(id: UUID, review_in: TaskSubmissionReview, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await task_service.review_submission(db, id, review_in)


# ── Proposals ─────────────────────────────────────────────────────────────────

@router.get("/epics/{id}/proposals", response_model=List[ProposalOut])
async def read_proposals(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await proposal_service.get_proposals_by_epic(db, id)

@router.patch("/proposals/{id}", response_model=ProposalOut)
async def review_proposal(id: UUID, review_in: ProposalReview, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await proposal_service.review_proposal(db, id, review_in, current_user.id)


# ── Mind map ──────────────────────────────────────────────────────────────────

@router.get("/epics/{id}/mind-map", response_model=MindMapLayoutOut)
async def get_mind_map(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await mind_map_service.get_or_create_layout(db, id)

@router.patch("/epics/{id}/mind-map", response_model=MindMapLayoutOut)
async def update_mind_map(id: UUID, layout_in: MindMapLayoutUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await mind_map_service.update_layout(db, id, layout_in)


# ── Tracker ───────────────────────────────────────────────────────────────────

@router.get("/tracker/{user_id}", response_model=List[TaskOut])
async def get_user_tracker(user_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """All tasks assigned to a specific user — used by admin to view any intern's tracker."""
    return await task_service.get_tasks_assigned_to(db, user_id)
