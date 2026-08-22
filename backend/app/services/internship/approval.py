"""Shared "approve an internship request" core — used by all three entry
points that end in an internship letter: the authenticated self-apply path
(routers/internship.py, RoleRequest target_role="intern"), a direct
admin approval of a public intern Application (routers/admin/applications.py
::approve_application), and an intern Application routed into instructor
onboarding, replayed automatically once that pipeline is approved
(routers/instructors/admin.py::review_applicant). One place generates the
ref number, the letter, uploads it, and emails the intern — so all three
entry points stay in sync instead of duplicating this logic. See
HANDOFF_INTERNSHIP.md.
"""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.internship import InternProfile
from app.models.user import User
from app.schemas.internship import InternshipApprove
from app.services import storage
from app.services.documents.internship_letter import generate_internship_letter_pdf
from app.services.email import send_internship_letter_ready_email
from app.services.internship.ref_number import next_ref_number


def _format_letter_date(d: date) -> str:
    """"8 July 2026" — cross-platform, no %-d/%#d strftime flag needed.
    Matches contract.py's format_contract_date convention."""
    return f"{d.day} {d.strftime('%B %Y')}"


def resolve_internship_request_fields(approve: InternshipApprove, details: dict) -> tuple[str | None, date | None]:
    """Fills `approve.city_id`/`duration_weeks` from the applicant's own
    submitted `details` (a RoleRequest.details or an Application.answers
    dict — same key names, see routers/apply.py and routers/internship.py)
    when the admin didn't override them, and extracts
    `university_id_number`/`start_date` — the requester's own submission.
    `start_date` isn't overridden here even when `approve.start_date_override`
    is set — `approve_internship()`'s `resolve_start_date()` needs *both*
    values (what was requested, and any override) to apply the boss's
    auto-resolve rule, so this always returns the raw requested value.
    Mutates `approve` in place (city_id/duration_weeks only); returns the
    two extracted values for `approve_internship()`'s other two positional
    args."""
    if approve.city_id is None and details.get("preferred_city_id"):
        approve.city_id = uuid.UUID(str(details["preferred_city_id"]))
    if approve.duration_weeks is None and details.get("requested_duration_weeks"):
        approve.duration_weeks = int(details["requested_duration_weeks"])
    university_id_number = details.get("university_id_number")
    start_date = date.fromisoformat(details["requested_start_date"]) if details.get("requested_start_date") else None
    return university_id_number, start_date


def resolve_start_date(
    requested: date | None, override: date | None, approval_date: date, existing: date | None = None,
) -> date | None:
    """Boss spec (2026-08-20): admin can always override; otherwise auto-resolve
    against what was actually requested and the real approval moment —

    - approval happens on/before the requested date -> the requested date, as-is.
    - approval happens after the requested date -> the day *after* approval
      (not the approval date itself — the person can't start retroactively,
      and starting the same day admin happens to click approve is presumptuous
      about their availability that day).

    `existing` (a profile's current start_date, if any) is the fallback only
    when there's neither an override nor anything ever requested — preserves
    a previously-set value across a re-approval rather than resetting it to
    today for no reason."""
    if override is not None:
        return override
    if requested is not None:
        return requested if approval_date <= requested else approval_date + timedelta(days=1)
    return existing


async def approve_internship(
    db: AsyncSession,
    *,
    user: User,
    university_id_number: str | None,
    start_date: date | None,
    department: str | None,
    approve: InternshipApprove,
) -> InternProfile:
    """Grants the `intern` role (if not already held), creates/updates
    `InternProfile`, allocates a ref number, generates the unsigned letter,
    uploads it, and emails the intern. Caller commits."""
    if "intern" not in user.role_values:
        user.roles = list(user.roles or []) + [UserRole.intern]

    profile = await db.get(InternProfile, user.id)
    if profile is None:
        profile = InternProfile(user_id=user.id)
        db.add(profile)

    duration_weeks = approve.duration_weeks
    hours_per_week = approve.hours_per_week
    city_id = approve.city_id
    approval_date = datetime.now(timezone.utc).date()

    profile.university_id_number = university_id_number or profile.university_id_number
    profile.department = approve.activity_description or department or profile.department
    profile.start_date = resolve_start_date(start_date, approve.start_date_override, approval_date, profile.start_date)
    profile.duration_weeks = duration_weeks
    profile.hours_per_week = hours_per_week
    profile.work_city_id = city_id
    profile.salutation = approve.salutation
    profile.supervisor_title = approve.supervisor_title
    profile.supervisor_name = approve.supervisor_name
    profile.supervisor_email = approve.supervisor_email
    profile.supervisor_phone = approve.supervisor_phone

    ref_number = await next_ref_number(db, override=approve.ref_number_override)
    profile.ref_number = ref_number

    supervisor_first_name = approve.supervisor_name.split(" ")[0] if approve.supervisor_name else ""
    profile.letter_date = profile.letter_date or approval_date
    letter_date = _format_letter_date(profile.letter_date)
    start_date_str = _format_letter_date(profile.start_date) if profile.start_date else letter_date

    pdf_bytes = await asyncio.to_thread(
        generate_internship_letter_pdf,
        ref_number=ref_number,
        university_id=profile.university_id_number or "",
        letter_date=letter_date,
        salutation=approve.salutation,
        intern_name=user.full_name,
        start_date=start_date_str,
        duration_weeks=duration_weeks or 0,
        activity_description=approve.activity_description,
        hours_per_week=hours_per_week or 0,
        supervisor_title=approve.supervisor_title,
        supervisor_name=approve.supervisor_name,
        supervisor_first_name=supervisor_first_name,
        supervisor_email=approve.supervisor_email,
        supervisor_phone=approve.supervisor_phone,
    )

    letter_path = profile.letter_path or f"{user.id}/internship_letter.pdf"
    await storage.upload_file("internship-letters", letter_path, pdf_bytes, "application/pdf")
    profile.letter_path = letter_path

    await db.flush()

    await send_internship_letter_ready_email(user.email, user.full_name)

    return profile
