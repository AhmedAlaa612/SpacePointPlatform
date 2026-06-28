from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from fastapi import HTTPException, status
from uuid import UUID
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    db_user = User(
        full_name=user_in.full_name,
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        roles=user_in.roles,
        phone=user_in.phone,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def get_users(db: AsyncSession):
    result = await db.execute(select(User))
    return result.scalars().all()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def update_user(db: AsyncSession, user_id: UUID, user_in: UserUpdate) -> User:
    user = await get_user_by_id(db, user_id)
    update_data = user_in.dict(exclude_unset=True)

    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: UUID):
    user = await get_user_by_id(db, user_id)

    # Check if user is a leader of any teams
    team_check = await db.execute(text("SELECT id, name FROM teams WHERE leader_id = :uid"), {"uid": user_id})
    led_teams = team_check.all()
    if led_teams:
        team_names = ", ".join([r[1] for r in led_teams])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete user who is a leader of team(s): {team_names}. Reassign team leadership first."
        )

    # Check if user created any projects
    project_check = await db.execute(text("SELECT id, title FROM projects WHERE created_by = :uid"), {"uid": user_id})
    created_projects = project_check.all()
    if created_projects:
        proj_names = ", ".join([r[1] for r in created_projects])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete user who created project(s): {proj_names}. Delete or reassign projects first."
        )

    # Remove from team_members
    await db.execute(text("DELETE FROM team_members WHERE user_id = :uid"), {"uid": user_id})
    # Remove from task_assignees
    await db.execute(text("DELETE FROM task_assignees WHERE user_id = :uid"), {"uid": user_id})

    await db.delete(user)
    await db.commit()
    return {"detail": "User deleted"}
