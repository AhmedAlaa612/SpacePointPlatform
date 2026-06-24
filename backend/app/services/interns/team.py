from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from uuid import UUID
from app.models.interns.team import Team, team_members
from app.models.user import User
from app.schemas.interns.team import TeamCreate, TeamUpdate
from app.services.user import get_user_by_id

async def create_team(db: AsyncSession, team_in: TeamCreate) -> Team:
    db_team = Team(name=team_in.name, leader_id=team_in.leader_id)
    db.add(db_team)
    await db.commit()
    return await get_team_by_id(db, db_team.id)

async def get_teams(db: AsyncSession):
    result = await db.execute(select(Team).options(selectinload(Team.members)))
    return result.scalars().all()

async def get_team_by_id(db: AsyncSession, team_id: UUID) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id).options(selectinload(Team.members)))
    team = result.scalars().first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team

async def update_team(db: AsyncSession, team_id: UUID, team_in: TeamUpdate) -> Team:
    team = await get_team_by_id(db, team_id)
    update_data = team_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(team, field, value)
    await db.commit()
    await db.refresh(team)
    return team

async def delete_team(db: AsyncSession, team_id: UUID):
    team = await get_team_by_id(db, team_id)
    await db.delete(team)
    await db.commit()
    return {"detail": "Team deleted"}

async def add_member(db: AsyncSession, team_id: UUID, user_id: UUID) -> Team:
    team = await get_team_by_id(db, team_id)
    user = await get_user_by_id(db, user_id)
    if user in team.members:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already in team")
    team.members.append(user)
    await db.commit()
    await db.refresh(team)
    return team

async def remove_member(db: AsyncSession, team_id: UUID, user_id: UUID) -> Team:
    team = await get_team_by_id(db, team_id)
    user = await get_user_by_id(db, user_id)
    if user not in team.members:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not in team")
    team.members.remove(user)
    await db.commit()
    await db.refresh(team)
    return team
