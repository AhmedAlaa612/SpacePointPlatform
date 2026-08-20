"""Shared "approve an internship request" core — used by both the
authenticated self-apply path (routers/internship.py, RoleRequest
target_role="intern") and, in future, the public /apply/intern path once
its approval branch is wired up. One place generates the ref number, the
letter, uploads it, and emails the intern — so both entry points stay in
sync instead of duplicating this logic.
"""

import asyncio
from datetime import date, datetime, timezone

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

    profile.university_id_number = university_id_number or profile.university_id_number
    profile.department = approve.activity_description or department or profile.department
    profile.start_date = start_date or profile.start_date
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
    profile.letter_date = profile.letter_date or datetime.now(timezone.utc).date()
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
