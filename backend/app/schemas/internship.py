from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class RoleRequestCreate(BaseModel):
    """Body for POST /me/role-requests. `details` is validated per
    target_role in the router (see services/internship/allowed_role_requests.py)
    — for target_role="intern": university_id_number, preferred_city_id,
    requested_start_date, requested_duration_weeks."""
    target_role: str
    details: dict


class RoleRequestOut(BaseModel):
    id: UUID
    requester_user_id: UUID
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    target_role: str
    status: str
    details: dict
    resolution: dict
    admin_notes: Optional[str] = None
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RoleRequestReject(BaseModel):
    admin_notes: Optional[str] = None


class InternshipApprove(BaseModel):
    """Admin sets these at approval time. `salutation`/`supervisor_*` are
    required — nothing in the schema captures gender/title anywhere, so
    there's no default to fall back to and the letter needs real values
    (same reasoning the letter template itself already bakes in: these are
    free text, admin-editable per request, not inferred). `city_id`/
    `duration_weeks`/`hours_per_week`/`ref_number_override` are optional
    overrides — fall back to the requester's own `details` (city/duration)
    when omitted, or to services/internship/ref_number.py's auto-increment
    when ref_number_override is unset."""
    salutation: str
    activity_description: str  # e.g. "research and development" — prints in the letter body
    supervisor_title: str
    supervisor_name: str
    supervisor_email: str
    supervisor_phone: str
    city_id: Optional[UUID] = None
    duration_weeks: Optional[int] = None
    hours_per_week: Optional[int] = None
    ref_number_override: Optional[int] = None
    admin_notes: Optional[str] = None


class InternProfileOut(BaseModel):
    user_id: UUID
    ref_number: Optional[str] = None
    university_id_number: Optional[str] = None
    department: Optional[str] = None
    start_date: Optional[date] = None
    duration_weeks: Optional[int] = None
    hours_per_week: Optional[int] = None
    work_city_id: Optional[UUID] = None
    supervisor_name: Optional[str] = None
    supervisor_email: Optional[str] = None
    supervisor_phone: Optional[str] = None
    letter_url: Optional[str] = None
    signed_letter_url: Optional[str] = None
    letter_signed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SignInternshipLetterRequest(BaseModel):
    signature: str  # data:image/png;base64,...
