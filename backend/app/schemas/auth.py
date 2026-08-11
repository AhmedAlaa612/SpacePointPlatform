from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class StudentSignupRequest(BaseModel):
    """LMS student self-signup (LM1-4). Phone optional — email is the account
    key, exactly as it is for /auth/login.

    date_of_birth/invite_code/parent_*/country/city_id (2026-08-08) are all
    optional, same posture as phone — collected if given, never required to
    sign up. invite_code is validated against the same admin-code/
    ambassador-referral mechanism instructor-apply uses
    (services/invitations.py). parent_name + parent_phone together create a
    linked guardian contact, mirroring PublicRegistrationRequest's identical
    rule. city_id references the same admin-configurable `cities` table
    instructors' deliver_city_ids uses (GET /public/cities)."""

    full_name: str
    email: EmailStr
    password: str
    phone: str | None = None
    date_of_birth: date | None = None
    invite_code: str | None = None
    parent_name: str | None = None
    parent_phone: str | None = None
    parent_email: EmailStr | None = None
    country: str | None = None
    city_id: UUID | None = None
    # Free-text fallback (2026-08-08) — "Other" city for countries the
    # pickers have no SpacePoint city for; stored on users.city_other.
    city_other: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    new_password: str
    current_password: str | None = None


class SetPasswordRequest(BaseModel):
    """LM1-7 — the "invite sent" email link for ops-created LMS accounts
    (§8 Q5). Token-authenticated, so no current password is needed."""

    token: str
    new_password: str


class UserOut(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    roles: list[str]
    status: str
    must_change_password: bool = False
    phone: str | None = None
    country: str | None = None
    invite_code: str | None = None
    photo_url: str | None = None
    linkedin_url: str | None = None
    nickname: str | None = None  # students only — the public identity leaderboards/games show
    created_at: datetime | None = None
    # Resolved from the user's linked Contact (2026-08-08) — None for staff
    # users without a contact_id, or students who never provided them.
    date_of_birth: date | None = None
    grade: str | None = None
    # The user's own city (2026-08-08) — independent of the applicant-profile
    # fields below, available to every role including students.
    city_id: UUID | None = None
    city_name: str | None = None
    city_other: str | None = None
    # Applicant-derived profile fields (instructors/facilitators/applicants).
    # Present only when the user has an applicant_profile; null otherwise.
    # Structured (2026-08-08) — reference `cities` instead of free text.
    city_of_residence_id: UUID | None = None
    deliver_city_ids: list[UUID] | None = None
    # Resolved names for the two id fields above (2026-08-09) so consumers can
    # display cities without separately fetching /public/cities to build an
    # id->name map. deliver_city_names follows deliver_city_ids order and
    # omits ids whose city has since been deleted, so it can be SHORTER than
    # deliver_city_ids — never index one by the other's position.
    city_of_residence_name: str | None = None
    deliver_city_names: list[str] | None = None
    has_own_transportation: bool | None = None


class UpdateMeRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    city_id: UUID | None = None
    city_other: str | None = None
    city_of_residence_id: UUID | None = None
    deliver_city_ids: list[UUID] | None = None
    has_own_transportation: bool | None = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(Token):
    user: UserOut
