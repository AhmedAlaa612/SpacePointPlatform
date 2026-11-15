"""Compute missing mandatory profile fields for an authenticated user.

Reads the per-role form configuration (``apply_field_config_{role}`` in
``PortalSetting`` via ``services/apply_form_config.py``) so admins control
mandatory fields in one place (Applications -> Form & Questions) and existing
accounts are prompted for any required profile fields they have not filled yet.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.apply_config import CONFIGURABLE_APPLY_ROLES
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.instructor_profile import InstructorProfile
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.apply_form_config import get_role_form_config, is_value_present

# Maps form-config field keys to canonical profile-completion field keys.
# Signup/application-only fields (password, invite_code, cv, parent_info, etc.)
# are intentionally omitted so existing users are never blocked on them.
_FORM_KEY_TO_PROFILE_KEY: dict[str, str] = {
    "phone": "phone",
    "nationality": "nationality",
    "date_of_birth": "birthdate",
    "birthdate": "birthdate",
    "country": "country",
    "city": "city",
    "city_of_residence_id": "city",
    "university": "university_name",
    "university_name": "university_name",
    "university_id_number": "student_id",
    "student_id": "student_id",
    "work_status": "work_status",
    "fluent_languages": "fluent_languages",
    "graduated_university": "graduated_university",
}

# Roles that are never blocked by the profile completion gate.
_EXEMPT_ROLES = {"admin", "observer", "judge"}


def _has_profile_value(
    profile_key: str,
    user: User,
    contact: Contact | None,
    profile: ApplicantProfile | None,
    instructor_prof: InstructorProfile | None,
) -> bool:
    if profile_key == "phone":
        return is_value_present(user.phone) or bool(contact and is_value_present(contact.primary_phone_e164))
    if profile_key == "nationality":
        return (
            bool(instructor_prof and is_value_present(instructor_prof.nationality))
            or bool(profile and is_value_present(profile.nationality))
            or bool(contact and is_value_present(contact.nationality))
        )
    if profile_key == "birthdate":
        return is_value_present(user.birthdate) or bool(contact and is_value_present(contact.date_of_birth))
    if profile_key == "country":
        return is_value_present(user.country) or bool(contact and is_value_present(contact.country))
    if profile_key == "city":
        return (
            is_value_present(user.city_id)
            or is_value_present(user.city_other)
            or bool(profile and is_value_present(profile.city_of_residence_id))
            or bool(contact and is_value_present(contact.city))
        )
    if profile_key == "university_name":
        return (
            is_value_present(user.organization_id)
            or bool(contact and is_value_present(contact.organization_id))
            or bool(profile and is_value_present(profile.university))
        )
    if profile_key == "student_id":
        return is_value_present(user.student_id) or bool(contact and is_value_present(contact.student_id))
    if profile_key == "work_status":
        return bool(instructor_prof and is_value_present(instructor_prof.work_status)) or bool(
            profile and is_value_present(profile.work_status)
        )
    if profile_key == "fluent_languages":
        return bool(instructor_prof and is_value_present(instructor_prof.fluent_languages)) or bool(
            profile and is_value_present(profile.fluent_languages)
        )
    if profile_key == "graduated_university":
        return bool(instructor_prof and is_value_present(instructor_prof.graduated_university)) or bool(
            profile and is_value_present(profile.graduated_university)
        )
    return True


async def compute_missing_profile_fields(
    db: AsyncSession,
    user: User,
    *,
    contact: Contact | None = None,
    profile: ApplicantProfile | None = None,
    instructor_prof: InstructorProfile | None = None,
) -> list[str]:
    """Return ordered, deduplicated canonical keys of required profile fields that are missing."""
    roles = user.role_values
    if "admin" in roles:
        return []
    check_roles = [r for r in roles if r in CONFIGURABLE_APPLY_ROLES and r not in _EXEMPT_ROLES]
    if not check_roles:
        return []

    missing: list[str] = []
    seen: set[str] = set()

    for role in check_roles:
        cfg: dict[str, Any] = await get_role_form_config(db, role)
        for field in cfg.get("fields", []):
            if field.get("locked") or not field.get("enabled") or not field.get("required"):
                continue
            profile_key = _FORM_KEY_TO_PROFILE_KEY.get(field["key"])
            if not profile_key or profile_key in seen:
                continue
            if not _has_profile_value(profile_key, user, contact, profile, instructor_prof):
                missing.append(profile_key)
                seen.add(profile_key)

    return missing
