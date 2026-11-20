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
from app.models.sessions.cohort import Cohort
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


async def is_cohort_org_manager(db: AsyncSession, cohort: Cohort, user: User) -> bool:
    """True when `user` is an organization owner/coordinator for `cohort`'s organization."""
    if "organization" not in user.role_values or not is_org_manager(user):
        return False
    from app.services.website_events import resolve_user_organization

    org = await resolve_user_organization(db, user)
    if org is None:
        return False
    org_id = await cohort_organization_id(db, cohort)
    return org_id is not None and org_id == org.id


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
