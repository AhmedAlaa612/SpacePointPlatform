from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from fastapi import HTTPException, status
from uuid import UUID
from app.models.user import User
from app.schemas.user import UserCreate, UserSelfUpdate, UserUpdate
from app.core.security import get_password_hash
from app.services.documents.id_card import ensure_card_number
from app.services.spine.identity import contact_roles_for_user, ensure_user_contact
from app.services.spine.role_history import record_role_diff


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
    await db.flush()

    # Create the linked contact now (rather than waiting for the periodic
    # backfill script) so a role assigned at account-creation time — e.g.
    # "applicant" — has a role-history entry from day one, not a gap until
    # the next backfill run or role edit.
    await ensure_user_contact(db, db_user, source="user_created")
    # Every account gets its SP-0000 number the moment it exists, not on
    # first card view (operator ask, 2026-08-17).
    await ensure_card_number(db, db_user)

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


async def update_user(db: AsyncSession, user_id: UUID, user_in: UserUpdate | UserSelfUpdate, actor_user_id: UUID | None = None) -> User:
    user = await get_user_by_id(db, user_id)
    update_data = user_in.dict(exclude_unset=True)

    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))

    # `users.nickname` is UNIQUE, so an admin retyping a name already in use
    # would otherwise surface as a 500 from the database rather than as the
    # correctable mistake it is.
    if update_data.get("nickname"):
        nickname = update_data["nickname"].strip()
        clash = (await db.execute(
            select(User).where(User.nickname == nickname, User.id != user_id)
        )).scalars().first()
        if clash is not None:
            raise HTTPException(409, detail=f"The nickname \"{nickname}\" is already taken")
        update_data["nickname"] = nickname

    if update_data.get("avatar"):
        from app.services.games.avatars import AVATAR_PRESETS
        if update_data["avatar"] not in AVATAR_PRESETS:
            raise HTTPException(400, detail="Unknown avatar")

    # Capture the raw role list before it's overwritten (PATCH replaces the
    # whole array) so a role-history event can be recorded — see
    # services/spine/role_history.py. Uses the actual role strings
    # (applicant/instructor/intern/...), not the collapsed contact_roles
    # bucket, since that's what an admin actually assigned/removed.
    # `update_data.get("roles") is not None` (not just "roles" in update_data):
    # UserSelfUpdate (routers/interns/shared.py's self-service PATCH /users/me)
    # has no `roles` field at all, so that path never puts "roles" in
    # update_data. This guard just protects against a bare `roles=None` from
    # any UserUpdate caller being treated as "remove every role" — Pydantic v2
    # marks an explicitly-passed None as "set", same as any other field.
    roles_before = list(user.role_values) if update_data.get("roles") is not None else None

    for field, value in update_data.items():
        setattr(user, field, value)

    if roles_before is not None:
        roles_after = list(user.role_values)
        if roles_before != roles_after:
            contact = await ensure_user_contact(db, user, source="user_role_edit")
            await record_role_diff(
                db, contact.id, roles_before, roles_after,
                source="user_role_edit", changed_by_user_id=actor_user_id,
            )
            # "instructor" newly granted directly by an admin (not through
            # applicant approval) — freeze instructor_since here too, or the
            # contract this person eventually views would print date.today()
            # forever (there's no InstructorProfile row yet to hold a date
            # at all). Never overwrites an existing date — this only fills
            # the gap for someone who never went through approval.
            if "instructor" in roles_after and "instructor" not in roles_before:
                from app.models.instructors.instructor_profile import InstructorProfile
                inst_profile = await db.get(InstructorProfile, user.id)
                if inst_profile is None:
                    db.add(InstructorProfile(
                        user_id=user.id, instructor_since=datetime.now(timezone.utc).date(),
                    ))
                elif inst_profile.instructor_since is None:
                    inst_profile.instructor_since = datetime.now(timezone.utc).date()
            # Additive-only sync onto contact_roles (the coarser bucket used
            # for Contacts search/filter) — same safety policy as the
            # backfill script's re-sync: never removes a role the contact
            # already has. No separate history event for this: the row
            # above already narrates *why* — this is just keeping the
            # derived filter field caught up, not a second human action.
            mapped_needed = set(contact_roles_for_user(user)) - set(contact.contact_roles or [])
            if mapped_needed:
                contact.contact_roles = sorted(set(contact.contact_roles or []) | mapped_needed)

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
