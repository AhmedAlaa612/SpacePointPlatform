"""Organization sandbox roles (2026-11-18).

A partner organization is a sandbox of the portal: its own team, cohorts,
sessions, instructors and judges. `users.org_role` carries what a person does
*inside that organization*, while `users.roles` remains the global capability
set every existing endpoint already gates on.

Two rules this module encodes:

* The organization's managers (`owner`, `coordinator`) run the sandbox;
  `instructor`, `judge` and `observer` are sandbox members with narrower
  surfaces.
* An org-affiliated instructor/judge must not see SpacePoint's freelance
  marketplace, payouts or contracts. That fence reads `org_role`, never the
  global role, so granting `instructor` for delivery access does not also hand
  them the marketplace.
"""

import uuid
from typing import Iterable, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.sessions.cohort import Cohort, CohortCoordinator
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.user import User

ORG_ROLES: tuple[str, ...] = ("owner", "coordinator", "instructor", "judge", "observer")
# Roles an org owner/coordinator may assign from the Team page. `owner` is not
# in this list on purpose: the primary owner is `organizations.owner_user_id`,
# a legal/signatory fact, not a dropdown value.
ASSIGNABLE_ORG_ROLES: tuple[str, ...] = ("coordinator", "instructor", "judge", "observer")
ORG_MANAGER_ROLES: tuple[str, ...] = ("owner", "coordinator")
OWNER_EXTRA_ORG_ROLES: tuple[str, ...] = ("instructor", "judge", "observer")
_ORG_ROLE_ORDER: dict[str, int] = {r: i for i, r in enumerate(ORG_ROLES)}


def normalize_org_role(value: str | None) -> str:
    role = (value or "coordinator").strip().lower()
    if role not in ASSIGNABLE_ORG_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Organization role must be one of: "
                + ", ".join(ASSIGNABLE_ORG_ROLES)
            ),
        )
    return role


def normalize_org_roles(
    values: Sequence[str] | None,
    *,
    fallback_role: str | None = None,
    is_owner: bool = False,
) -> list[str]:
    """Validate and canonically sort a set of org sandbox roles.

    Primary owners always keep `"owner"` locked (`coordinator` is redundant
    with `owner` and omitted) while allowing any combination of
    `instructor`/`judge`/`observer`. Non-owners must have at least one role
    from `ASSIGNABLE_ORG_ROLES`.
    """
    if values is None:
        if is_owner:
            fb = (fallback_role or "").strip().lower()
            if fb in ("", "owner", "coordinator"):
                return ["owner"]
            if fb not in OWNER_EXTRA_ORG_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Organization owner additional role must be one of: " + ", ".join(OWNER_EXTRA_ORG_ROLES),
                )
            return sorted(["owner", fb], key=lambda r: _ORG_ROLE_ORDER[r])
        return [normalize_org_role(fallback_role)]

    cleaned = [str(v).strip().lower() for v in values if v is not None and str(v).strip()]
    if is_owner:
        invalid = [r for r in cleaned if r not in ORG_ROLES]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Organization roles must be chosen from: " + ", ".join(ORG_ROLES),
            )
        role_set = {"owner"} | (set(cleaned) - {"coordinator"})
        return sorted(role_set, key=lambda r: _ORG_ROLE_ORDER[r])

    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least one organization role",
        )
    invalid = [r for r in cleaned if r not in ASSIGNABLE_ORG_ROLES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Organization roles must be chosen from: " + ", ".join(ASSIGNABLE_ORG_ROLES),
        )
    return sorted(set(cleaned), key=lambda r: _ORG_ROLE_ORDER[r])


def primary_org_role(roles: Sequence[str]) -> str | None:
    valid = [r for r in roles if r in ORG_ROLES]
    if not valid:
        return None
    return min(valid, key=lambda r: _ORG_ROLE_ORDER[r])


def set_user_org_roles(user: User, roles: Sequence[str]) -> list[str]:
    """Write `user.org_roles` (fresh list for SQLAlchemy change detection)
    and keep `user.org_role` synced to the highest-priority role."""
    ordered = sorted({r for r in roles if r in ORG_ROLES}, key=lambda r: _ORG_ROLE_ORDER[r])
    user.org_roles = list(ordered)
    user.org_role = ordered[0] if ordered else None
    return ordered


def clear_user_org_roles(user: User) -> None:
    user.org_roles = []
    user.org_role = None


def effective_org_roles(user: User, *, is_owner: bool = False) -> list[str]:
    """All sandbox roles the user holds inside their organization."""
    raw = [r for r in (getattr(user, "org_roles", None) or []) if r in ORG_ROLES]
    if not raw:
        legacy = getattr(user, "org_role", None)
        if legacy in ORG_ROLES:
            raw = [legacy]
        elif "organization" in user.role_values:
            raw = ["coordinator"]
    role_set = set(raw)
    if is_owner:
        role_set.add("owner")
        role_set.discard("coordinator")
    return sorted(role_set, key=lambda r: _ORG_ROLE_ORDER[r])


def effective_org_role(user: User, *, is_owner: bool = False) -> str | None:
    """Highest-priority sandbox role for legacy single-role readers."""
    roles = effective_org_roles(user, is_owner=is_owner)
    return roles[0] if roles else None


def has_org_role(user: User, role: str, *, is_owner: bool = False) -> bool:
    return role in effective_org_roles(user, is_owner=is_owner)


def has_any_org_role(user: User, roles: Iterable[str], *, is_owner: bool = False) -> bool:
    wanted = set(roles)
    return bool(wanted & set(effective_org_roles(user, is_owner=is_owner)))


def is_org_manager(user: User) -> bool:
    if any(r in user.role_values for r in ("admin", "operations")):
        return True
    return has_any_org_role(user, ORG_MANAGER_ROLES)


def require_org_manager(user: User) -> None:
    if not is_org_manager(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organization owner or a coordinator can do this",
        )


def is_org_owner(user: User, org) -> bool:
    if is_ops_or_admin(user):
        return True
    if org is not None and getattr(org, "owner_user_id", None) == user.id:
        return True
    return False


def require_org_owner(user: User, org) -> None:
    if not is_org_owner(user, org):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organization owner can manage team members",
        )


def global_roles_for_org_roles(org_roles: Sequence[str]) -> list[UserRole]:
    """Global roles an org team member receives.

    Every org sandbox member (coordinator, instructor, judge, observer) runs
    inside the `organization` workspace (`/organization/*`) and uses `org_roles`
    to switch tabs and permissions — never auto-granted global `instructor` or
    `judge`, so SpacePoint's freelance instructor/judge portals stay 100%
    separate.
    """
    return [UserRole.organization]


def global_roles_for_org_role(org_role: str) -> list[UserRole]:
    return global_roles_for_org_roles([org_role])


def is_ops_or_admin(user: User) -> bool:
    return any(r in ("operations", "admin") for r in user.role_values)


async def cohort_organization_id(db: AsyncSession, cohort: Cohort) -> uuid.UUID | None:
    if cohort.organization_id is not None:
        return cohort.organization_id
    program = await db.get(Program, cohort.program_id)
    return program.organization_id if program else None


async def is_cohort_assigned_to_coordinator(db: AsyncSession, cohort: Cohort, user: User) -> bool:
    """True if `cohort` is in `'general'` mode or `user` is listed in `cohort_coordinators`."""
    if (getattr(cohort, "coordinator_access_mode", None) or "general") != "assigned":
        return True
    row = await db.scalar(
        select(CohortCoordinator.id).where(
            CohortCoordinator.cohort_id == cohort.id,
            CohortCoordinator.user_id == user.id,
        )
    )
    return row is not None


async def accessible_org_cohort_ids(db: AsyncSession, org, user: User) -> set[uuid.UUID] | None:
    """Return cohort_ids in `org` that `user` may manage/view, or None for unrestricted access.

    Ops/Admin and the organization owner see every cohort in the org (`None`).
    A coordinator (without owner or observer privilege) sees ONLY `'general'`
    cohorts plus `'assigned'` cohorts where they appear in `cohort_coordinators`.
    """
    if is_ops_or_admin(user) or (org is not None and org.owner_user_id == user.id):
        return None
    if org is None:
        return set()
    roles = effective_org_roles(user, is_owner=False)
    if "observer" in roles and "coordinator" not in roles:
        return None
    if "coordinator" not in roles:
        return set()

    from sqlalchemy import or_

    all_org_cohorts = (
        await db.execute(
            select(Cohort.id, Cohort.coordinator_access_mode)
            .outerjoin(Program, Program.id == Cohort.program_id)
            .where(or_(Cohort.organization_id == org.id, Program.organization_id == org.id))
        )
    ).all()
    if not all_org_cohorts:
        return set()
    assigned_ids = set(
        (
            await db.execute(
                select(CohortCoordinator.cohort_id).where(
                    CohortCoordinator.user_id == user.id,
                    CohortCoordinator.cohort_id.in_([cid for cid, _ in all_org_cohorts]),
                )
            )
        ).scalars().all()
    )
    return {
        cid
        for cid, mode in all_org_cohorts
        if (mode or "general") != "assigned" or cid in assigned_ids
    }


async def is_cohort_org_manager(db: AsyncSession, cohort: Cohort, user: User) -> bool:
    """True when `user` is an organization owner/coordinator permitted on `cohort`."""
    if "organization" not in user.role_values or not is_org_manager(user):
        return False
    from app.services.website_events import resolve_user_organization

    org = await resolve_user_organization(db, user)
    if org is None:
        return False
    org_id = await cohort_organization_id(db, cohort)
    if org_id is None or org_id != org.id:
        return False
    if org.owner_user_id == user.id:
        return True
    return await is_cohort_assigned_to_coordinator(db, cohort, user)


async def is_program_org_manager(db: AsyncSession, program_id: uuid.UUID, user: User) -> bool:
    """True when `user` is an organization owner/coordinator for `program_id`'s organization."""
    if "organization" not in user.role_values or not is_org_manager(user):
        return False
    from app.services.website_events import resolve_user_organization

    org = await resolve_user_organization(db, user)
    if org is None:
        return False
    program = await db.get(Program, program_id)
    return program is not None and program.organization_id == org.id


def can_org_use_shared_program(org, program: Program) -> bool:
    """True when `org` is granted shared access to launch cohorts from SpacePoint `program`."""
    if program.organization_id is not None:
        return False
    scope = (getattr(org, "program_scope", None) or "own").strip().lower()
    if scope == "all":
        return bool(program.active)
    if scope == "selected":
        allowed = {str(pid) for pid in (getattr(org, "allowed_program_ids", None) or [])}
        return str(program.id) in allowed
    return False


def is_program_allowed_for_org(org, program: Program) -> bool:
    """True when `org` owns `program` OR has shared SpacePoint program access to it."""
    return program.organization_id == org.id or can_org_use_shared_program(org, program)


async def can_org_manager_read_program_template(
    db: AsyncSession, program_id: uuid.UUID, user: User
) -> bool:
    """True if `user` manages the program directly, manages an org cohort under it,
    or belongs to an org with shared program access."""
    if await is_program_org_manager(db, program_id, user):
        return True
    if "organization" not in user.role_values or not is_org_manager(user):
        return False
    from app.services.website_events import resolve_user_organization

    org = await resolve_user_organization(db, user)
    if org is None:
        return False
    program = await db.get(Program, program_id)
    if program is not None and can_org_use_shared_program(org, program):
        return True
    cohort_id = await db.scalar(
        select(Cohort.id)
        .where(Cohort.program_id == program_id, Cohort.organization_id == org.id)
        .limit(1)
    )
    return cohort_id is not None


def is_partner_managed(cohort: Cohort) -> bool:
    """True when the partner organization runs this cohort (Mode A)."""
    return (getattr(cohort, "management_mode", "spacepoint") or "spacepoint") == "partner"


def is_spacepoint_managed(cohort: Cohort) -> bool:
    """True when SpacePoint Ops runs this cohort (standard or Mode B for partner)."""
    return not is_partner_managed(cohort)


async def is_cohort_org_member(db: AsyncSession, cohort: Cohort, user: User) -> bool:
    """True when `user` belongs to `cohort`'s organization (any org role)."""
    if "organization" not in user.role_values:
        return False
    from app.services.website_events import resolve_user_organization

    org = await resolve_user_organization(db, user)
    if org is None:
        return False
    org_id = await cohort_organization_id(db, cohort)
    return org_id is not None and org_id == org.id


async def is_cohort_org_observer(db: AsyncSession, cohort: Cohort, user: User) -> bool:
    """True when `user` has observer visibility into `cohort`'s organization."""
    if "organization" not in user.role_values:
        return False
    from app.services.website_events import resolve_user_organization

    org = await resolve_user_organization(db, user)
    if org is None:
        return False
    org_id = await cohort_organization_id(db, cohort)
    if org_id is None or org_id != org.id:
        return False
    return has_org_role(user, "observer", is_owner=(org.owner_user_id == user.id))


async def can_read_cohort(db: AsyncSession, cohort: Cohort, user: User) -> bool:
    """True when `user` can read `cohort` (Ops/Admin, Org Owner/Coordinator, or Org Observer)."""
    if is_ops_or_admin(user):
        return True
    if "organization" not in user.role_values:
        return False
    from app.services.website_events import resolve_user_organization

    org = await resolve_user_organization(db, user)
    if org is None:
        return False
    org_id = await cohort_organization_id(db, cohort)
    if org_id is None or org_id != org.id:
        return False
    roles = effective_org_roles(user, is_owner=(org.owner_user_id == user.id))
    if "owner" in roles or "observer" in roles:
        return True
    if "coordinator" in roles:
        return await is_cohort_assigned_to_coordinator(db, cohort, user)
    return False


async def can_write_cohort(db: AsyncSession, cohort: Cohort, user: User) -> bool:
    """True when `user` can edit cohort details/dates/students/LMS (Ops/Admin or Org Manager)."""
    if is_ops_or_admin(user):
        return True
    return await is_cohort_org_manager(db, cohort, user)


async def can_manage_cohort_delivery(db: AsyncSession, cohort: Cohort, user: User) -> bool:
    """True when `user` may control delivery/staffing/open-calls/duration/day-review/completion.

    SpacePoint Ops may manage any cohort. Partner Org Managers may manage delivery ONLY
    for Mode A (`management_mode == 'partner'`) cohorts; Mode B delivery stays Ops-only.
    """
    if is_ops_or_admin(user):
        return True
    if is_spacepoint_managed(cohort):
        return False
    return await is_cohort_org_manager(db, cohort, user)


async def can_org_read_program_template(
    db: AsyncSession, program_id: uuid.UUID, user: User
) -> bool:
    """True if `user` (manager OR observer) may read template/certificate config for `program_id`."""
    if await can_org_manager_read_program_template(db, program_id, user):
        return True
    if "organization" not in user.role_values:
        return False
    from app.services.website_events import resolve_user_organization

    org = await resolve_user_organization(db, user)
    if org is None:
        return False
    roles = effective_org_roles(user, is_owner=(org.owner_user_id == user.id))
    if not any(r in ("owner", "coordinator", "observer") for r in roles):
        return False
    program = await db.get(Program, program_id)
    if program is not None and (program.organization_id == org.id or can_org_use_shared_program(org, program)):
        return True
    cohort_id = await db.scalar(
        select(Cohort.id)
        .where(Cohort.program_id == program_id, Cohort.organization_id == org.id)
        .limit(1)
    )
    return cohort_id is not None


async def require_program_read_or_ops(
    db: AsyncSession, program_id: uuid.UUID, user: User
) -> Program:
    """Allow Ops/Admin OR an org manager/observer with read access to `program_id`."""
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    if is_ops_or_admin(user) or await can_org_read_program_template(db, program_id, user):
        return program
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Operation not permitted")


async def require_program_manager_or_ops(
    db: AsyncSession, program_id: uuid.UUID, user: User
) -> Program:
    """Allow Ops/Admin on any program OR Org Manager strictly on their org-owned program."""
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    if is_ops_or_admin(user) or await is_program_org_manager(db, program_id, user):
        return program
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Operation not permitted")


async def require_cohort_read_or_ops(
    db: AsyncSession, cohort_id: uuid.UUID, user: User
) -> Cohort:
    """Allow platform ops/admin OR an org manager/observer of the cohort's organization."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    if await can_read_cohort(db, cohort, user):
        return cohort
    if "organization" in user.role_values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Operation not permitted")


async def require_session_read_or_ops(
    db: AsyncSession,
    session_id: uuid.UUID,
    user: User,
    *,
    cohort_id: uuid.UUID | None = None,
) -> tuple[Session, Cohort]:
    session = await db.get(Session, session_id)
    if session is None or (cohort_id is not None and session.cohort_id != cohort_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    cohort = await require_cohort_read_or_ops(db, session.cohort_id, user)
    return session, cohort


async def require_cohort_manager_or_ops(
    db: AsyncSession, cohort_id: uuid.UUID, user: User
) -> Cohort:
    """Allow platform ops/admin OR an owner/coordinator of the cohort's organization."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    if is_ops_or_admin(user):
        return cohort
    if "organization" in user.role_values and is_org_manager(user):
        if await is_cohort_org_manager(db, cohort, user):
            return cohort
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Operation not permitted")


async def require_cohort_delivery_manager_or_ops(
    db: AsyncSession, cohort_id: uuid.UUID, user: User
) -> Cohort:
    """Allow Ops/Admin on any cohort, OR Org Manager ONLY on Mode A ('partner') cohorts."""
    cohort = await require_cohort_manager_or_ops(db, cohort_id, user)
    if not await can_manage_cohort_delivery(db, cohort, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Delivery and staffing for SpacePoint-managed cohorts are managed by SpacePoint Ops.",
        )
    return cohort


async def require_session_delivery_manager_or_ops(
    db: AsyncSession,
    session_id: uuid.UUID,
    user: User,
    *,
    cohort_id: uuid.UUID | None = None,
) -> tuple[Session, Cohort]:
    session = await db.get(Session, session_id)
    if session is None or (cohort_id is not None and session.cohort_id != cohort_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    cohort = await require_cohort_delivery_manager_or_ops(db, session.cohort_id, user)
    return session, cohort


async def resolve_target_org_for_actor(
    db: AsyncSession,
    current_user: User,
    organization_id: uuid.UUID | None = None,
):
    """Resolve target Organization for `/organization/*` endpoints.

    SpacePoint Ops/Admin may target any organization via explicit `organization_id` (or fall
    back to their own linked organization if any). Partner users always resolve to their own
    organization and receive 403 if attempting to target a different organization.
    """
    from app.models.spine.organization import Organization
    from app.services.website_events import resolve_user_organization

    if organization_id is not None:
        if is_ops_or_admin(current_user):
            org = await db.get(Organization, organization_id)
            if org is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found")
            return org
        own_org = await resolve_user_organization(db, current_user)
        if own_org is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="User is not linked to an organization.")
        if own_org.id != organization_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cannot access another organization.")
        return own_org

    own_org = await resolve_user_organization(db, current_user)
    if own_org is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="User is not linked to an organization.")
    return own_org


async def require_session_manager_or_ops(
    db: AsyncSession,
    session_id: uuid.UUID,
    user: User,
    *,
    cohort_id: uuid.UUID | None = None,
) -> tuple[Session, Cohort]:
    session = await db.get(Session, session_id)
    if session is None or (cohort_id is not None and session.cohort_id != cohort_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    cohort = await require_cohort_manager_or_ops(db, session.cohort_id, user)
    return session, cohort


async def require_registration_manager_or_ops(
    db: AsyncSession, registration_id: uuid.UUID, user: User
) -> tuple[Registration, Cohort]:
    reg = await db.get(Registration, registration_id)
    if reg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration not found")
    cohort = await require_cohort_manager_or_ops(db, reg.cohort_id, user)
    return reg, cohort


async def assert_user_eligible_for_cohort_staffing(
    db: AsyncSession, cohort: Cohort, target_user: User
) -> None:
    """Enforce cohort instructor scope regardless of whether Ops or Org Owner assigns.

    Organization cohorts may only be staffed with instructors belonging to that organization.
    """
    if not is_partner_managed(cohort):
        return
    org_id = await cohort_organization_id(db, cohort)
    if org_id is None:
        return
    from app.services.website_events import resolve_user_organization

    target_org = await resolve_user_organization(db, target_user)
    if (
        target_org is None
        or target_org.id != org_id
        or not has_org_role(
            target_user,
            "instructor",
            is_owner=(target_org.owner_user_id == target_user.id),
        )
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Organization cohorts can only be staffed with instructors from the same organization.",
        )
