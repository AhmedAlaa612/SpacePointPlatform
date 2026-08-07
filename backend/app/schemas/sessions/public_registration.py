from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr


class PublicRegistrationRequest(BaseModel):
    student_name: str
    email: EmailStr
    phone: str
    city: str | None = None

    # Purely informational (2026-07-24, CEO request) — no age/minor
    # enforcement is derived from date_of_birth anywhere in this system.
    # organization_name resolves or creates an Organization by name (school).
    date_of_birth: date | None = None
    grade: str | None = None
    organization_name: str | None = None

    # Always optional — no age/minor detection or enforcement happens in this
    # system at all; if a parent's details are given they're linked as the
    # guardian/payer, otherwise the student is their own payer. Whether that's
    # appropriate for a given registration is a judgment call made outside
    # this flow, not something the system gates on.
    parent_name: str | None = None
    parent_phone: str | None = None
    parent_email: EmailStr | None = None

    # Which of the cohort's sessions this registration covers. None (the
    # default) means "every session in the cohort" — the common case for a
    # single-session workshop, and safe even if not every session has been
    # generated yet at registration time.
    session_ids: list[UUID] | None = None

    # Honeypot — real users never see or fill this field. A bot that fills
    # every field on the form will fill this one too.
    website: str = ""


class PublicInterestRequest(BaseModel):
    """"Notify me" — a lighter cousin of PublicRegistrationRequest for a
    `planned` cohort. No parent/guardian, no session_ids (nothing to book
    into yet), same honeypot posture."""
    student_name: str
    email: EmailStr
    phone: str
    website: str = ""
