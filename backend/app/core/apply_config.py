"""Shared constants for the unified public application pipeline (/apply/*)."""

# Roles a member of the public can self-apply for via /apply/{role}.
VALID_ROLES = {"ambassador", "intern", "teacher", "facilitator"}

# All application roles that support configurable form fields & custom questions.
CONFIGURABLE_APPLY_ROLES = {
    "ambassador",
    "intern",
    "teacher",
    "facilitator",
    "instructor",
    "organization",
    "student",
}

# Roles whose apply form collects a CV upload.
ROLES_WITH_CV = {"ambassador", "intern", "teacher", "facilitator"}

# Roles that must supply a valid invite code to apply.
ROLES_REQUIRING_CODE = {"teacher"}

# Keys stored inside Application.answers or RoleRequest.details that belong to
# structured sections or internal snapshots rather than freeform question answers.
RESERVED_ANSWER_KEYS = {
    "user_id",
    "organization_id",
    "city_id",
    "final_city_id",
    "full_name",
    "email",
    "phone",
    "country",
    "birthdate",
    "nationality",
    "city",
    "city_other",
    "university",
    "major",
    "university_id_number",
    "graduation_year",
    "education_level",
    "teaching_experience",
    "preferred_city_id",
    "requested_start_date",
    "requested_duration_weeks",
    "organization_name",
    "organization_name_ar",
    "organization_type",
    "org_type",
    "website",
    "bio",
    "linkedin",
    "experience",
    "motivation",
    "has_transportation",
    "invite_code",
    "cv_path",
    "cv_url",
    "parent_name",
    "parent_email",
    "parent_phone",
    "answers",
    "_question_snapshots",
}

