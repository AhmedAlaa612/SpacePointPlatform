from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_people import StudentMission, TeamMember, WebsiteAlumni, WebsiteAmbassador
from app.schemas.website_people import (
    AlumniCreate,
    AlumniOut,
    AlumniUpdate,
    AmbassadorCreate,
    AmbassadorOut,
    AmbassadorUpdate,
    StudentMissionCreate,
    StudentMissionOut,
    StudentMissionUpdate,
    TeamMemberCreate,
    TeamMemberOut,
    TeamMemberUpdate,
)

router = APIRouter(prefix="/website", tags=["admin-website-people"])


async def _ordered_list(db: AsyncSession, model):
    return (
        await db.execute(select(model).order_by(model.display_order, model.created_at))
    ).scalars().all()


async def _get_or_404(db: AsyncSession, model, entity: str, row_id: UUID):
    row = (await db.execute(select(model).where(model.id == row_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{entity} not found")
    return row


async def _create(db: AsyncSession, model, body):
    row = model(**body.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _update(db: AsyncSession, model, entity: str, row_id: UUID, body):
    row = await _get_or_404(db, model, entity, row_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def _delete(db: AsyncSession, model, entity: str, row_id: UUID):
    row = await _get_or_404(db, model, entity, row_id)
    await db.delete(row)
    await db.commit()
    return None


# ── Team ──────────────────────────────────────────────────────────────────


@router.get("/team", response_model=list[TeamMemberOut])
async def list_team(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)):
    return await _ordered_list(db, TeamMember)


@router.post("/team", response_model=TeamMemberOut, status_code=status.HTTP_201_CREATED)
async def create_team_member(
    body: TeamMemberCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _create(db, TeamMember, body)


@router.put("/team/{row_id}", response_model=TeamMemberOut)
async def update_team_member(
    row_id: UUID, body: TeamMemberUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _update(db, TeamMember, "Team member", row_id, body)


@router.delete("/team/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_member(
    row_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _delete(db, TeamMember, "Team member", row_id)


# ── Ambassadors ───────────────────────────────────────────────────────────


@router.get("/ambassadors", response_model=list[AmbassadorOut])
async def list_ambassadors(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)):
    return await _ordered_list(db, WebsiteAmbassador)


@router.post("/ambassadors", response_model=AmbassadorOut, status_code=status.HTTP_201_CREATED)
async def create_ambassador(
    body: AmbassadorCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _create(db, WebsiteAmbassador, body)


@router.put("/ambassadors/{row_id}", response_model=AmbassadorOut)
async def update_ambassador(
    row_id: UUID, body: AmbassadorUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _update(db, WebsiteAmbassador, "Ambassador", row_id, body)


@router.delete("/ambassadors/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ambassador(
    row_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _delete(db, WebsiteAmbassador, "Ambassador", row_id)


# ── Alumni ────────────────────────────────────────────────────────────────


@router.get("/alumni", response_model=list[AlumniOut])
async def list_alumni(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)):
    return await _ordered_list(db, WebsiteAlumni)


@router.post("/alumni", response_model=AlumniOut, status_code=status.HTTP_201_CREATED)
async def create_alumni(
    body: AlumniCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _create(db, WebsiteAlumni, body)


@router.put("/alumni/{row_id}", response_model=AlumniOut)
async def update_alumni(
    row_id: UUID, body: AlumniUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _update(db, WebsiteAlumni, "Alumni", row_id, body)


@router.delete("/alumni/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alumni(
    row_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _delete(db, WebsiteAlumni, "Alumni", row_id)


# ── Student missions ──────────────────────────────────────────────────────


@router.get("/student-missions", response_model=list[StudentMissionOut])
async def list_student_missions(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)):
    return await _ordered_list(db, StudentMission)


@router.post(
    "/student-missions", response_model=StudentMissionOut, status_code=status.HTTP_201_CREATED
)
async def create_student_mission(
    body: StudentMissionCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _create(db, StudentMission, body)


@router.put("/student-missions/{row_id}", response_model=StudentMissionOut)
async def update_student_mission(
    row_id: UUID,
    body: StudentMissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    return await _update(db, StudentMission, "Student mission", row_id, body)


@router.delete("/student-missions/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student_mission(
    row_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _delete(db, StudentMission, "Student mission", row_id)
