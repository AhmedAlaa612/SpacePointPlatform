"""Instructor onboarding pipeline deadlines, intake eligibility, and extension services."""

from datetime import date, datetime, timedelta, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.payment import PortalSetting
from app.models.user import User

DEFAULT_PHASE1_DAYS = 7
DEFAULT_REVISION_DAYS = 3
DEFAULT_PRESENTATION_DAYS = 3
DEFAULT_ASSESSMENT_DAYS = 3
DEFAULT_EXTENSION_DAYS = 1
DEFAULT_HARD_TIMEOUT_DAYS = 10
DEFAULT_MIN_AGE = 18

SETTING_KEYS = {
    "instructor_intake_enabled": "true",
    "instructor_intake_min_age": str(DEFAULT_MIN_AGE),
    "instructor_intake_require_university": "false",
    "instructor_deadline_phase1_days": str(DEFAULT_PHASE1_DAYS),
    "instructor_deadline_presentation_days": str(DEFAULT_PRESENTATION_DAYS),
    "instructor_deadline_assessment_days": str(DEFAULT_ASSESSMENT_DAYS),
    "instructor_deadline_revision_days": str(DEFAULT_REVISION_DAYS),
    "instructor_extension_days": str(DEFAULT_EXTENSION_DAYS),
    "instructor_hard_timeout_days": str(DEFAULT_HARD_TIMEOUT_DAYS),
}


async def get_instructor_settings(db: AsyncSession) -> dict[str, Any]:
    """Fetches intake rules and pipeline deadlines from portal_settings with safe defaults."""
    keys = list(SETTING_KEYS.keys())
    rows = (await db.execute(select(PortalSetting).where(PortalSetting.key.in_(keys)))).scalars().all()
    data = {r.key: r.value for r in rows}

    def _int(k: str, default: int) -> int:
        try:
            return int(data.get(k, SETTING_KEYS[k]))
        except (ValueError, TypeError):
            return default

    def _bool(k: str, default: bool) -> bool:
        v = data.get(k, SETTING_KEYS[k])
        if v is None:
            return default
        return str(v).lower() in ("true", "1", "yes")

    return {
        "instructor_intake_enabled": _bool("instructor_intake_enabled", True),
        "instructor_intake_min_age": _int("instructor_intake_min_age", DEFAULT_MIN_AGE),
        "instructor_intake_require_university": _bool("instructor_intake_require_university", False),
        "instructor_deadline_phase1_days": _int("instructor_deadline_phase1_days", DEFAULT_PHASE1_DAYS),
        "instructor_deadline_presentation_days": _int("instructor_deadline_presentation_days", DEFAULT_PRESENTATION_DAYS),
        "instructor_deadline_assessment_days": _int("instructor_deadline_assessment_days", DEFAULT_ASSESSMENT_DAYS),
        "instructor_deadline_revision_days": _int("instructor_deadline_revision_days", DEFAULT_REVISION_DAYS),
        "instructor_extension_days": _int("instructor_extension_days", DEFAULT_EXTENSION_DAYS),
        "instructor_hard_timeout_days": _int("instructor_hard_timeout_days", DEFAULT_HARD_TIMEOUT_DAYS),
    }


def is_student_eligible_to_apply(user: User, settings: dict[str, Any]) -> tuple[bool, str | None]:
    """Evaluates whether the given user meets the admin-defined criteria to apply as instructor."""
    if not settings.get("instructor_intake_enabled", True):
        return False, "Instructor applications are currently closed."

    roles = user.role_values
    if "instructor" in roles:
        return False, "You are already an instructor."
    if "applicant" in roles:
        return False, "You already have an active instructor application."

    if not user.birthdate:
        return False, "Birthdate is not set on your profile. A verified birthdate (18+) is required."

    today = date.today()
    birth = user.birthdate
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    min_age = settings.get("instructor_intake_min_age", DEFAULT_MIN_AGE)
    if age < min_age:
        return False, f"You must be at least {min_age} years old to apply (current age: {age})."

    if settings.get("instructor_intake_require_university", False):
        if not user.student_id:
            return False, "University affiliation / Student ID is required to apply."

    return True, None


def compute_phase_deadline(days: int) -> datetime:
    """Returns a UTC timestamp `days` in the future."""
    return datetime.now(timezone.utc) + timedelta(days=max(1, days))
