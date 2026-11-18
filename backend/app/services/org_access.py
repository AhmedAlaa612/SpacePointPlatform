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

from fastapi import HTTPException, status

from app.models.enums import UserRole
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
