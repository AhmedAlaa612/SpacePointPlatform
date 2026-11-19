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


def effective_org_role(user: User) -> str | None:
    """The role to act on.

    Legacy partner team members were created before `org_role` existed; they
    carry the `organization` role and no sandbox role, which is a coordinator.
    """
    role = getattr(user, "org_role", None)
    if role in ORG_ROLES:
        return role
    if "organization" in user.role_values:
        return "coordinator"
    return None


def is_org_manager(user: User) -> bool:
    if any(r in user.role_values for r in ("admin", "operations")):
        return True
    return effective_org_role(user) in ORG_MANAGER_ROLES


def require_org_manager(user: User) -> None:
    if not is_org_manager(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organization owner or a coordinator can do this",
        )


def global_roles_for_org_role(org_role: str) -> list[UserRole]:
    """Global roles an org team member receives.

    Every org sandbox member (coordinator, instructor, judge, observer) runs
    inside the `organization` workspace (`/organization/*`) and uses `org_role`
    to switch tabs and permissions — never auto-granted global `instructor` or
    `judge`, so SpacePoint's freelance instructor/judge portals stay 100%
    separate.
    """
    return [UserRole.organization]


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
        or effective_org_role(target_user) != "instructor"
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Organization cohorts can only be staffed with instructors from the same organization.",
        )
