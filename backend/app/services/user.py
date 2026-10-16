from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from fastapi import HTTPException, status
from uuid import UUID
from app.models.spine.contact import Contact
from app.models.user import User
from app.schemas.user import UserCreate, UserSelfUpdate, UserUpdate
from app.core.security import get_password_hash
from app.services.documents.id_card import ensure_card_number
from app.services.spine.identity import (
    contact_roles_for_user,
    ensure_user_contact,
    normalize_user_email,
    replace_user_email,
    user_email_matches,
)
from app.services.spine.role_history import record_role_diff


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    # Canonical normalization at the write boundary (strip + lowercase) —
    # the User model validator enforces the same form as a safety net, and
    # the lookup below is case-insensitive so legacy mixed-case rows can't
    # slip past the duplicate check.
    email = normalize_user_email(user_in.email)
    result = await db.execute(select(User).where(user_email_matches(email)))
    if result.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    db_user = User(
        full_name=user_in.full_name,
        email=email,
        password_hash=get_password_hash(user_in.password),
        roles=user_in.roles,
        phone=user_in.phone,
    )
    db.add(db_user)
    await db.flush()

    if "lms_author" in db_user.role_values:
        from app.models.lms.author_profile import LmsAuthorProfile
        profile = LmsAuthorProfile(
            user_id=db_user.id,
            can_publish=bool(user_in.author_can_publish),
            scope_all=bool(user_in.author_scope_all),
        )
        db.add(profile)

    # Create the linked contact now (rather than waiting for the periodic
    # backfill script) so a role assigned at account-creation time — e.g.
    # "applicant" — has a role-history entry from day one, not a gap until
    # the next backfill run or role edit.
    contact = await ensure_user_contact(db, db_user, source="user_created")
    # Every account gets its SP-0000 number the moment it exists, not on
    # first card view (operator ask, 2026-08-17).
    await ensure_card_number(db, db_user)

    if "organization" in db_user.role_values or user_in.org_name_latin:
        from app.models.spine.organization import Organization
        org = Organization(
            name_latin=(user_in.org_name_latin or db_user.full_name).strip(),
            name_arabic=(user_in.org_name_arabic or "").strip() or None,
            org_type=(user_in.org_type or "university").strip().lower(),
            country=(user_in.org_country or "uae").strip().lower(),
            city=(user_in.org_city or "").strip() or None,
            primary_contact_id=contact.id if contact else db_user.contact_id,
            owner_user_id=db_user.id,
        )
        db.add(org)
        await db.flush()
        if contact:
            contact.organization_id = org.id

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

    org_fields = {
        k: update_data.pop(k)
        for k in ("org_name_latin", "org_name_arabic", "org_type", "org_country", "org_city")
        if k in update_data
    }

    if update_data.get("email"):
        update_data["email"] = normalize_user_email(update_data["email"])
        # Same 409-instead-of-500 discipline as the nickname check below:
        # an admin retyping an address another account holds must get a
        # correctable error, not a UniqueViolation. Case-insensitive so a
        # legacy mixed-case row can't be collided into either.
        clash = (await db.execute(
            select(User).where(user_email_matches(update_data["email"]), User.id != user_id)
        )).scalars().first()
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")
        # Replace everywhere (user row + every contact carrying the old
        # address + identity alias), not just the user row — the old
        # address must survive nowhere as this person's identifier. Runs
        # before the setattr loop below, which would otherwise overwrite
        # user.email first and blind the helper to the old address. The
        # loop re-sets the same value afterward, harmlessly.
        await replace_user_email(db, user, update_data["email"])

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

    # A rename follows the person onto their linked contact — the contact
    # row was seeded from this same name at account creation, and the
    # student-manage endpoint keeps the two in sync the same way. Email
    # itself is already handled above (replace_user_email).
    if update_data.get("full_name") and isinstance(user.full_name, str) and user.full_name.strip():
        if user.contact_id:
            named = await db.get(Contact, user.contact_id)
            if named is not None:
                named.full_name = user.full_name.strip()

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

    # Sync LMS Author profile
    if "lms_author" in user.role_values:
        from app.models.lms.author_profile import LmsAuthorProfile
        profile = await db.get(LmsAuthorProfile, user.id)
        if profile is None:
            profile = LmsAuthorProfile(
                user_id=user.id,
                can_publish=bool(update_data.get("author_can_publish")),
                scope_all=bool(update_data.get("author_scope_all")),
            )
            db.add(profile)
        else:
            if "author_can_publish" in update_data and update_data["author_can_publish"] is not None:
                profile.can_publish = bool(update_data["author_can_publish"])
            if "author_scope_all" in update_data and update_data["author_scope_all"] is not None:
                profile.scope_all = bool(update_data["author_scope_all"])

    # Sync Organization profile if user has 'organization' role or org fields were sent
    if "organization" in user.role_values or org_fields:
        from app.models.spine.organization import Organization
        org = (
            await db.execute(select(Organization).where(Organization.owner_user_id == user.id))
        ).scalars().first()
        if org is None and user.contact_id:
            contact_row = await db.get(Contact, user.contact_id)
            if contact_row and contact_row.organization_id:
                org = await db.get(Organization, contact_row.organization_id)
        if org is None:
            org = Organization(
                name_latin=(org_fields.get("org_name_latin") or user.full_name).strip(),
                name_arabic=(org_fields.get("org_name_arabic") or "").strip() or None,
                org_type=(org_fields.get("org_type") or "university").strip().lower(),
                country=(org_fields.get("org_country") or user.country or "uae").strip().lower(),
                city=(org_fields.get("org_city") or user.city_other or "").strip() or None,
                primary_contact_id=user.contact_id,
                owner_user_id=user.id,
            )
            db.add(org)
        else:
            if "org_name_latin" in org_fields and org_fields["org_name_latin"]:
                org.name_latin = org_fields["org_name_latin"].strip()
            if "org_name_arabic" in org_fields:
                org.name_arabic = (org_fields["org_name_arabic"] or "").strip() or None
            if "org_type" in org_fields and org_fields["org_type"]:
                org.org_type = org_fields["org_type"].strip().lower()
            if "org_country" in org_fields and org_fields["org_country"] is not None:
                org.country = org_fields["org_country"].strip().lower() or None
            if "org_city" in org_fields:
                org.city = (org_fields["org_city"] or "").strip() or None
            if org.owner_user_id is None:
                org.owner_user_id = user.id

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

    # Judge accounts (competition domain) can be deleted once they've never
    # scored anything, but CompetitionScore.judge_user_id CASCADEs on
    # delete — hard-deleting a judge who already judged would silently
    # wipe those teams' evaluation record. Deactivate instead (PATCH
    # .../users/{id} with status="inactive") for a judge who's done.
    score_check = await db.execute(
        text("SELECT COUNT(*) FROM competition_scores WHERE judge_user_id = :uid"), {"uid": user_id}
    )
    if score_check.scalar_one() > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a judge who has already scored teams — deactivate the account instead "
                   "so the scores they gave stay on record.",
        )

    # Remove from team_members
    await db.execute(text("DELETE FROM team_members WHERE user_id = :uid"), {"uid": user_id})
    # Remove from task_assignees
    await db.execute(text("DELETE FROM task_assignees WHERE user_id = :uid"), {"uid": user_id})
    has_website_events = (await db.execute(text("SELECT to_regclass('public.website_events')"))).scalar() is not None
    if has_website_events:
        await db.execute(text("UPDATE website_events SET created_by_user_id = NULL WHERE created_by_user_id = :uid"), {"uid": user_id})
    # Unlink or delete owned organizations if no cohorts reference them
    owned_orgs = (await db.execute(text("SELECT id FROM organizations WHERE owner_user_id = :uid"), {"uid": user_id})).all()
    for (oid,) in owned_orgs:
        if has_website_events:
            await db.execute(text("UPDATE website_events SET organization_id = NULL WHERE organization_id = :oid"), {"oid": oid})
        await db.execute(text("UPDATE contacts SET organization_id = NULL WHERE organization_id = :oid"), {"oid": oid})
        cohort_cnt = (await db.execute(text("SELECT COUNT(*) FROM cohorts WHERE organization_id = :oid"), {"oid": oid})).scalar_one()
        if cohort_cnt == 0:
            await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": oid})
        else:
            await db.execute(text("UPDATE organizations SET owner_user_id = NULL WHERE id = :oid"), {"oid": oid})

    await db.delete(user)
    await db.commit()
    return {"detail": "User deleted"}
