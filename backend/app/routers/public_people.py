"""Public people-showcase endpoints — no auth required.

Step 6 — People Showcase: the marketing site reads active team members,
ambassadors, alumni, and student missions here. Unmigrated (fresh table)
reads as an empty list rather than a 500 so the site's fallback content
stays in charge.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.website_people import StudentMission, TeamMember, WebsiteAlumni, WebsiteAmbassador
from app.schemas.website_people import AlumniOut, AmbassadorOut, StudentMissionOut, TeamMemberOut

router = APIRouter(prefix="/public", tags=["public-people"])


async def _active_list(db: AsyncSession, model, out_model):
    try:
        rows = (
            await db.execute(
                select(model)
                .where(model.is_active.is_(True))
                .order_by(model.display_order, model.created_at)
            )
        ).scalars().all()
    except Exception:
        return []
    return [out_model.model_validate(r) for r in rows]


@router.get("/team", response_model=list[TeamMemberOut])
async def list_public_team(db: AsyncSession = Depends(get_db)):
    return await _active_list(db, TeamMember, TeamMemberOut)


@router.get("/ambassadors", response_model=list[AmbassadorOut])
async def list_public_ambassadors(db: AsyncSession = Depends(get_db)):
    return await _active_list(db, WebsiteAmbassador, AmbassadorOut)


@router.get("/alumni", response_model=list[AlumniOut])
async def list_public_alumni(db: AsyncSession = Depends(get_db)):
    return await _active_list(db, WebsiteAlumni, AlumniOut)


@router.get("/student-missions", response_model=list[StudentMissionOut])
async def list_public_student_missions(db: AsyncSession = Depends(get_db)):
    return await _active_list(db, StudentMission, StudentMissionOut)
