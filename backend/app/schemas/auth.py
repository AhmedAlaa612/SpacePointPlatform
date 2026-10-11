from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class StudentSignupRequest(BaseModel):
    """LMS student self-signup (LM1-4). Phone required (2026-09-15 — ops
    needs a working number for every competition/cohort registrant, same
    posture PublicRegistrationRequest/registration_desk already have);
    email is still the account key, exactly as it is for /auth/login.

    date_of_birth/invite_code/parent_*/country/city_id (2026-08-08) are all
    optional — collected if given, never required to sign up. invite_code
    is validated against the same admin-code/ambassador-referral mechanism
    instructor-apply uses (services/invitations.py). parent_name +
    parent_phone together create a linked guardian contact, mirroring
    PublicRegistrationRequest's identical rule. city_id references the same
    admin-configurable `cities` table instructors' deliver_city_ids uses
    (GET /public/cities)."""

    full_name: str
    email: EmailStr
    password: str
    phone: str
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


class ForgotPasswordRequest(BaseModel):
    """Self-service "Forgot password?" (LMS + portal login pages)."""

    email: EmailStr


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
    """`email` isn't re-validated as `EmailStr` on the way out — same
    production incident as `app.schemas.user.UserReadBase` (2026-08-28):
    a bulk-import artifact can carry a non-email value in that column, and
    reading it back (here: `/auth/me`, `/auth/users/{id}`, the profile
    modal) must never 500 just because the stored value isn't a real
    address. This is a separate class from `app.schemas.user.UserOut` —
    same shape, same fix needed twice because nothing shares them."""

    id: str
    full_name: str
    email: str
    roles: list[str]
    status: str
    must_change_password: bool = False
    phone: str | None = None
    country: str | None = None
    invite_code: str | None = None
    photo_url: str | None = None
    linkedin_url: str | None = None
    nickname: str | None = None  # students only — the public identity leaderboards/games show
    avatar: str | None = None  # the account's default game avatar (AVATAR_PRESETS key)
    invitation_code_used: str | None = None  # the code this person typed at signup
    created_at: datetime | None = None
    # SP-0000 identity number (services/documents/id_card.py) — shared across
    # every role this person holds. Null until ensure_card_number() has run
    # for this account (every creation path now calls it; pre-existing
    # accounts get one from the one-time reset script).
    card_number: int | None = None
    card_id: str | None = None
    # Demographic fields (date_of_birth/birthdate, grade)
    date_of_birth: date | None = None
    birthdate: date | None = None
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
    nationality: str | None = None
    work_status: str | None = None
    fluent_languages: list[str] | None = None
    graduated_university: str | None = None
    author_can_publish: bool | None = None
    author_scope_all: bool | None = None
    organization_id: UUID | None = None
    organization_name: str | None = None
    organization_name_arabic: str | None = None
    organization_type: str | None = None
    organization_country: str | None = None
    organization_city: str | None = None


class OrganizationSignupRequest(BaseModel):
    org_name_latin: str
    org_name_arabic: str | None = None
    org_type: str = "university"
    country: str = "uae"
    city: str | None = None
    full_name: str
    email: EmailStr
    phone: str
    password: str

    @classmethod
    def _clean_email(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v

    def model_post_init(self, __context: object) -> None:
        self.email = self.email.strip().lower()




class UpdateMeRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    birthdate: date | None = None
    date_of_birth: date | None = None
    city_id: UUID | None = None
    city_other: str | None = None
    city_of_residence_id: UUID | None = None
    deliver_city_ids: list[UUID] | None = None
    has_own_transportation: bool | None = None
    org_name_latin: str | None = None
    org_name_arabic: str | None = None
    org_type: str | None = None
    org_country: str | None = None
    org_city: str | None = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(Token):
    user: UserOut
