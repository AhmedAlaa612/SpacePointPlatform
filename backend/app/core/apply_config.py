"""Shared constants for the unified public application pipeline (/apply/*)."""

# Roles a member of the public can self-apply for via /apply/{role}.
VALID_ROLES = {"ambassador", "intern", "teacher", "facilitator"}

# Roles whose apply form collects a CV upload.
ROLES_WITH_CV = {"intern", "teacher", "facilitator"}

# Roles that must supply a valid invite code to apply.
ROLES_REQUIRING_CODE = {"teacher"}
