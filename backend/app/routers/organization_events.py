from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_organization_account
from app.core.security import create_password_set_token
from app.db.session import get_db
from app.models.competitions.judging import CompetitionJudge
from app.models.enums import UserRole
from app.models.lms.program import CohortLmsEditor, LmsProgramAssignment
from app.models.sessions.cohort import Cohort, CohortCoordinator
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import MegaEvent, WebsiteEvent
from app.schemas.website_event import (
    OrgTeamMemberCreateIn,
    OrgTeamMemberOut,
    OrgTeamMemberUpdateIn,
    WebsiteEventCreate,
    WebsiteEventOut,
    WebsiteEventUpdate,
)
from app.services.email import (
    send_org_team_added_email,
    send_org_team_invite_email,
    send_password_set_link_email,
)
from app.services.org_access import (
    clear_user_org_roles,
    effective_org_roles,
    global_roles_for_org_roles,
    is_org_manager,
    is_org_owner,
    normalize_org_roles,
    require_org_manager,
    require_org_owner,
    set_user_org_roles,
)
from app.services.website_events import (
    build_organization_team_member,
    ensure_default_events_seeded,
    resolve_user_organization,
    serialize_mega_events,
    serialize_website_events,
    unique_website_event_slug,
)

router = APIRouter(prefix="/organization", tags=["organization-events"])


def _is_admin_or_ops(user: User) -> bool:
    return any(r in user.role_values for r in ("admin", "operations"))


@router.get("/me")
async def get_my_organization_context(
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Returns the organization linked to the current user and all available
    MegaEvents they can attach their events to."""
    await ensure_default_events_seeded(db)
    org = await resolve_user_organization(db, current_user)
    megas = (
        await db.execute(
            select(MegaEvent)
            .where(MegaEvent.is_published.is_(True))
            .order_by(MegaEvent.display_order.asc(), MegaEvent.title.asc())
        )
    ).scalars().all()
    is_owner = org is not None and org.owner_user_id == current_user.id
    my_org_roles = effective_org_roles(current_user, is_owner=is_owner)
    return {
        "organization": {
            "id": str(org.id),
            "name_latin": org.name_latin,
            "name_arabic": org.name_arabic,
            "org_type": org.org_type,
            "country": org.country,
            "city": org.city,
            "is_approved": org.is_approved,
            "can_publish_events": org.can_publish_events,
            "can_author_courses": org.can_author_courses,
            "can_publish_courses": org.can_publish_courses,
            "course_scope_all": org.course_scope_all,
            "allowed_course_ids": [str(c) for c in (org.allowed_course_ids or [])],
            "book_scope": (getattr(org, "book_scope", None) or "none").strip().lower(),
            "allowed_book_ids": [str(b) for b in (getattr(org, "allowed_book_ids", None) or [])],
            "max_events": org.max_events,
            "max_programs": org.max_programs,
            "max_cohorts": org.max_cohorts,
            "max_students_per_cohort": org.max_students_per_cohort,
            "max_observers_per_cohort": org.max_observers_per_cohort,
        }
        if org
        else None,
        "mega_events": await serialize_mega_events(db, megas, published_only_counts=True),
        "org_role": my_org_roles[0] if my_org_roles else None,
        "org_roles": my_org_roles,
        "is_owner": is_owner,
        "can_manage": is_org_manager(current_user),
    }


@router.get("/events", response_model=list[WebsiteEventOut])
async def list_my_organization_events(
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    await ensure_default_events_seeded(db)
    org = await resolve_user_organization(db, current_user)
    if _is_admin_or_ops(current_user) and org is None:
        rows = (
            await db.execute(
                select(WebsiteEvent).order_by(WebsiteEvent.display_order.asc(), WebsiteEvent.updated_at.desc())
            )
        ).scalars().all()
    else:
        conds = [WebsiteEvent.created_by_user_id == current_user.id]
        if org is not None:
            conds.append(WebsiteEvent.organization_id == org.id)
        rows = (
            await db.execute(
                select(WebsiteEvent)
                .where(or_(*conds))
                .order_by(WebsiteEvent.display_order.asc(), WebsiteEvent.updated_at.desc())
            )
        ).scalars().all()
    return await serialize_website_events(db, rows)


@router.post("/events", response_model=WebsiteEventOut, status_code=status.HTTP_201_CREATED)
async def create_organization_event(
    body: WebsiteEventCreate,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Organizations create their own events using the standard 12-section
    template. `is_published` is governed by org.can_publish_events."""
    org = await resolve_user_organization(db, current_user)
    require_org_manager(current_user)
    if org is not None and org.max_events is not None and not _is_admin_or_ops(current_user):
        existing_count = await db.scalar(
            select(func.count(WebsiteEvent.id)).where(WebsiteEvent.organization_id == org.id)
        )
        if (existing_count or 0) >= org.max_events:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_events} landing page(s). Contact the SpacePoint team to increase your limit.",
            )

    slug = await unique_website_event_slug(db, body.slug or body.title)

    data = body.model_dump(exclude={"slug", "is_published", "organization_id"})
    data["country"] = (data.get("country") or (org.country if org else "uae") or "uae").strip().lower()
    if not data.get("host_org_name") and org is not None:
        data["host_org_name"] = org.name_latin
    if body.cohort_id and not data.get("registration_url"):
        data["registration_url"] = f"/learn/programs/{body.cohort_id}"

    can_publish = _is_admin_or_ops(current_user) or (org is not None and bool(org.can_publish_events))

    row = WebsiteEvent(
        **data,
        slug=slug,
        organization_id=org.id if org else body.organization_id,
        created_by_user_id=current_user.id,
        is_published=bool(body.is_published) if can_publish else False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.put("/events/{event_id}", response_model=WebsiteEventOut)
async def update_organization_event(
    event_id: UUID,
    body: WebsiteEventUpdate,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    org = await resolve_user_organization(db, current_user)
    require_org_manager(current_user)
    is_owner = (
        _is_admin_or_ops(current_user)
        or row.created_by_user_id == current_user.id
        or (org is not None and row.organization_id == org.id)
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Not permitted to edit this event")

    updates = body.model_dump(exclude_unset=True)
    can_publish = _is_admin_or_ops(current_user) or (org is not None and bool(org.can_publish_events))
    if not can_publish:
        updates.pop("is_published", None)
    if not _is_admin_or_ops(current_user):
        updates.pop("organization_id", None)

    if "slug" in updates and updates["slug"]:
        updates["slug"] = await unique_website_event_slug(db, updates["slug"], exclude_id=row.id)
    if "country" in updates and updates["country"]:
        updates["country"] = updates["country"].strip().lower()
    if updates.get("cohort_id") and not updates.get("registration_url") and not row.registration_url:
        updates["registration_url"] = f"/learn/programs/{updates['cohort_id']}"

    for k, v in updates.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_event(
    event_id: UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    org = await resolve_user_organization(db, current_user)
    require_org_manager(current_user)
    is_owner = (
        _is_admin_or_ops(current_user)
        or row.created_by_user_id == current_user.id
        or (org is not None and row.organization_id == org.id)
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Not permitted to delete this event")

    await db.delete(row)
    await db.commit()
    return None


# ── Organization Team Management ─────────────────────────────────────────────
@router.get("/team", response_model=list[OrgTeamMemberOut])
async def list_my_organization_team(
    cohort_id: UUID | None = Query(None),
    org_id: UUID | None = Query(None),
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    is_ops = any(r in current_user.role_values for r in ("admin", "operations"))
    org: Organization | None = None
    if is_ops and cohort_id is not None:
        from app.models.sessions.program import Program

        cohort = await db.get(Cohort, cohort_id)
        if cohort is not None:
            program = await db.get(Program, cohort.program_id)
            target_org_id = cohort.organization_id or (program.organization_id if program else None)
            if target_org_id is not None:
                org = await db.get(Organization, target_org_id)
    elif is_ops and org_id is not None:
        org = await db.get(Organization, org_id)

    if org is None:
        org = await resolve_user_organization(db, current_user)
    if org is None:
        return []
    # Team management is owner + SpacePoint ops/admin only; coordinators use
    # GET /organization/coordinators when assigning cohort co-coordinators.
    require_org_owner(current_user, org)
    conds = [User.organization_id == org.id]
    if org.owner_user_id:
        conds.append(User.id == org.owner_user_id)
    users = (
        await db.execute(
            select(User)
            .where(or_(*conds))
            .order_by(User.created_at.asc())
        )
    ).scalars().all()
    # Affiliation is not membership: `users.organization_id` is also written by
    # the student profile's university field, so only people the partner org
    # actually staffed (or the owner) belong on the Team page. Legacy team
    # members carry the `organization` role but no `org_role` yet.
    users = [
        u
        for u in users
        if u.id == org.owner_user_id
        or u.org_role is not None
        or bool(getattr(u, "org_roles", None))
        or "organization" in u.role_values
    ]
    out: list[OrgTeamMemberOut] = []
    for u in users:
        is_owner = u.id == org.owner_user_id
        roles_list = effective_org_roles(u, is_owner=is_owner) or ["coordinator"]
        out.append(
            OrgTeamMemberOut(
                id=u.id,
                full_name=u.full_name,
                email=u.email,
                phone=u.phone,
                status=u.status,
                created_at=u.created_at,
                is_owner=is_owner,
                org_role=roles_list[0],
                org_roles=roles_list,
                invite_pending=bool(u.must_change_password),
            )
        )
    return out


@router.get("/coordinators")
async def list_organization_coordinators(
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight read-only list of org owners & coordinators for cohort assignment pickers."""
    org = await resolve_user_organization(db, current_user)
    if org is None:
        return []
    require_org_manager(current_user)
    conds = [User.organization_id == org.id]
    if org.owner_user_id:
        conds.append(User.id == org.owner_user_id)
    users = (
        await db.execute(select(User).where(or_(*conds)).order_by(User.full_name.asc()))
    ).scalars().all()
    out = []
    for u in users:
        is_owner_user = u.id == org.owner_user_id
        roles = effective_org_roles(u, is_owner=is_owner_user)
        if not any(r in ("owner", "coordinator") for r in roles):
            continue
        out.append({
            "id": str(u.id),
            "full_name": u.full_name,
            "email": u.email,
            "is_owner": is_owner_user,
            "org_roles": roles,
        })
    return out


@router.post("/team", response_model=OrgTeamMemberOut, status_code=status.HTTP_201_CREATED)
async def add_organization_team_member(
    body: OrgTeamMemberCreateIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await resolve_user_organization(db, current_user)
    if org is None:
        raise HTTPException(status_code=400, detail="No organization context found")
    require_org_owner(current_user, org)

    user, created = await build_organization_team_member(
        db,
        org=org,
        full_name=body.full_name,
        email=str(body.email),
        password=body.password,
        phone=body.phone,
        org_role=body.org_role,
        org_roles=body.org_roles,
    )

    base = (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    if created:
        token = create_password_set_token(user.id, expires_delta=timedelta(days=7))
        email_sent = await send_org_team_invite_email(
            user.email,
            user.full_name,
            org.name_latin,
            f"{base}/set-password?token={token}",
        )
    else:
        email_sent = await send_org_team_added_email(
            user.email, user.full_name, org.name_latin, f"{base}/login"
        )

    roles_list = effective_org_roles(user) or ["coordinator"]
    return OrgTeamMemberOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        status=user.status,
        created_at=user.created_at,
        is_owner=False,
        org_role=roles_list[0],
        org_roles=roles_list,
        invite_email_sent=email_sent,
        existing_account=not created,
    )


@router.patch("/team/{user_id}", response_model=OrgTeamMemberOut)
async def update_organization_team_member(
    user_id: UUID,
    body: OrgTeamMemberUpdateIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Change a member's sandbox roles. Owner/coordinator only; the primary
    owner (organizations.owner_user_id) always keeps `owner` locked and may
    also hold additional delivery/judging/observer roles."""
    org = await resolve_user_organization(db, current_user)
    if org is None:
        raise HTTPException(status_code=400, detail="No organization context found")
    require_org_owner(current_user, org)

    if body.org_roles is None and body.org_role is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide org_roles or org_role",
        )

    is_owner = user_id == org.owner_user_id
    user = await db.get(User, user_id)
    is_member = user is not None and (is_owner or user.organization_id == org.id)
    if not is_member:
        raise HTTPException(status_code=404, detail="Team member not found")

    roles_list = normalize_org_roles(body.org_roles, fallback_role=body.org_role, is_owner=is_owner)
    if is_owner and user.organization_id is None:
        user.organization_id = org.id
    set_user_org_roles(user, roles_list)
    merged = list(user.roles or [])
    existing_values = {r.value if hasattr(r, "value") else str(r) for r in merged}
    for needed in global_roles_for_org_roles(roles_list):
        if needed.value not in existing_values:
            merged.append(needed)
    user.roles = merged
    await db.commit()
    await db.refresh(user)

    return OrgTeamMemberOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        status=user.status,
        created_at=user.created_at,
        is_owner=is_owner,
        org_role=roles_list[0],
        org_roles=roles_list,
        invite_pending=bool(user.must_change_password),
    )


@router.delete("/team/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_organization_team_member(
    user_id: UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Detach a person from this organization without deleting their account.

    Deleting the `User` was the old behaviour and is catastrophic once the same
    account can also be a student or another org's instructor. Detach clears the
    membership, drops sandbox assignments (sessions/judging/observer rows) and
    only removes the global `instructor`/`judge` role when no assignment outside
    this organization still needs it.
    """
    org = await resolve_user_organization(db, current_user)
    if org is None:
        raise HTTPException(status_code=400, detail="No organization context found")
    require_org_owner(current_user, org)

    if user_id == org.owner_user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the organization primary owner")

    user = await db.get(User, user_id)
    if user is None or user.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Team member not found")

    org_cohort_ids = (
        select(Cohort.id)
        .outerjoin(Program, Program.id == Cohort.program_id)
        .where(or_(Cohort.organization_id == org.id, Program.organization_id == org.id))
    )
    org_session_ids = select(Session.id).where(Session.cohort_id.in_(org_cohort_ids))

    # Sandbox assignments belong to the membership, so they go with it.
    await db.execute(
        delete(SessionInstructor).where(
            SessionInstructor.user_id == user.id,
            SessionInstructor.session_id.in_(org_session_ids),
        )
    )
    await db.execute(
        delete(CompetitionJudge).where(
            CompetitionJudge.user_id == user.id,
            CompetitionJudge.cohort_id.in_(org_cohort_ids),
        )
    )
    await db.execute(
        delete(CohortLmsEditor).where(
            CohortLmsEditor.user_id == user.id,
            CohortLmsEditor.cohort_id.in_(org_cohort_ids),
        )
    )
    await db.execute(
        delete(CohortCoordinator).where(
            CohortCoordinator.user_id == user.id,
            CohortCoordinator.cohort_id.in_(org_cohort_ids),
        )
    )
    await db.execute(
        delete(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == user.id,
            LmsProgramAssignment.cohort_id.in_(org_cohort_ids),
        )
    )
    await db.flush()

    remaining_roles = [
        r for r in (user.roles or [])
        if (r.value if hasattr(r, "value") else str(r)) != "organization"
    ]
    if any((r.value if hasattr(r, "value") else str(r)) == "observer" for r in remaining_roles):
        still_observing = await db.scalar(
            select(LmsProgramAssignment.id)
            .where(
                LmsProgramAssignment.user_id == user.id,
                LmsProgramAssignment.mode == "observer",
            )
            .limit(1)
        )
        if still_observing is None:
            remaining_roles = [
                r for r in remaining_roles
                if (r.value if hasattr(r, "value") else str(r)) != "observer"
            ]
    if not remaining_roles:
        remaining_roles = [UserRole.student]

    # Never strip global SpacePoint instructor/judge roles on org detach;
    # org membership only grants/revokes the `organization` role (and falls back
    # to `student` when no other role remains).
    user.roles = remaining_roles
    user.organization_id = None
    clear_user_org_roles(user)

    if user.contact_id:
        from app.models.spine.contact import Contact

        contact = await db.get(Contact, user.contact_id)
        if contact is not None and contact.organization_id == org.id:
            contact.organization_id = None

    await db.commit()
    return None


@router.post("/team/{user_id}/reset-link")
async def organization_team_member_reset_link(
    user_id: UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Generates a 7-day password set/reset link for a member of this org's
    team and emails it to them. The URL is also returned so the owner can copy
    it manually if the email didn't go out."""
    org = await resolve_user_organization(db, current_user)
    if org is None:
        raise HTTPException(status_code=400, detail="No organization context found")
    require_org_owner(current_user, org)

    user = await db.get(User, user_id)
    is_member = user is not None and (user.id == org.owner_user_id or user.organization_id == org.id)
    if not is_member:
        raise HTTPException(status_code=404, detail="Team member not found")

    token = create_password_set_token(user.id, expires_delta=timedelta(days=7))
    base = (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    reset_url = f"{base}/set-password?token={token}"
    email_sent = await send_password_set_link_email(
        user.email, user.full_name, org.name_latin, reset_url
    )
    return {
        "organization_id": str(org.id),
        "user_id": str(user.id),
        "email": user.email,
        "reset_url": reset_url,
        "email_sent": email_sent,
    }
