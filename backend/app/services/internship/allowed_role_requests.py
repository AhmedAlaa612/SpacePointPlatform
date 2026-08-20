"""Which current roles may request which additional role via `RoleRequest`
(POST /me/role-requests). Deliberately just a dict — adding a new direction
(e.g. intern -> instructor) later is one entry here plus an approval
side-effect handler, no schema change (see models/internship.py::RoleRequest).
"""

ALLOWED_ROLE_REQUESTS: dict[str, list[str]] = {
    "instructor": ["intern"],
}


def can_request_role(current_roles: list[str], target_role: str) -> bool:
    return any(target_role in ALLOWED_ROLE_REQUESTS.get(r, []) for r in current_roles)
