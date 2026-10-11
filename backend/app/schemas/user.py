from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole


class UserBase(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    birthdate: date | None = None


class UserReadBase(BaseModel):
    """Same shape as `UserBase`, but `email` isn't re-validated as `EmailStr`
    on the way out. A handful of rows in the live DB (bulk-import artifacts,
    pre-dating stricter validation) don't parse as a real email address, and
    that must never 500 the *entire* admin user list for every row along with
    them — output schemas reflect what's stored, they don't gatekeep it.
    `EmailStr` stays on `UserCreate`/`UserUpdate` below, where it belongs:
    stopping a new bad value from ever being written."""
    full_name: str
    email: str
    phone: str | None = None
    birthdate: date | None = None


class UserCreate(UserBase):
    password: str
    roles: list[UserRole] = []
    author_can_publish: bool | None = None
    author_scope_all: bool | None = None
    org_name_latin: str | None = None
    org_name_arabic: str | None = None
    org_type: str | None = None
    org_country: str | None = None
    org_city: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    roles: list[UserRole] | None = None
    author_can_publish: bool | None = None
    author_scope_all: bool | None = None
    phone: str | None = None
    birthdate: date | None = None
    # Student identity in live games. Editable by an admin because a
    # generated nickname occasionally lands somewhere unusable in front of a
    # class, and there was previously no way to change it for someone else.
    nickname: str | None = None
    avatar: str | None = None
    # "active" | "inactive" — already enforced everywhere (auth.py's login
    # checks, dependencies.py's per-request check), but had no admin-facing
    # way to set it. Judge accounts (competition domain, 2026-08-24) are
    # meant to be temporary; deactivating one blocks login/access instantly
    # without touching their historical CompetitionScore rows the way a
    # hard delete would (see delete_user's guard below).
    status: str | None = None
    org_name_latin: str | None = None
    org_name_arabic: str | None = None
    org_type: str | None = None
    org_country: str | None = None
    org_city: str | None = None


class UserSelfUpdate(BaseModel):
    """PATCH /interns/users/me (self-service profile edit) — deliberately has
    no `roles` field, unlike UserUpdate, so a client can never smuggle a role
    change through their own profile update. An earlier version of that
    endpoint tried to guard this by force-setting `user_in.roles = None` on a
    UserUpdate instance, but Pydantic v2 still marks that as "set", so it flowed
    through into an IntegrityError on the NOT NULL users.roles column."""

    full_name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    phone: str | None = None
    birthdate: date | None = None


class UserOut(UserReadBase):
    id: UUID
    roles: list[UserRole] = []
    status: str | None = None
    country: str | None = None
    photo_url: str | None = None
    linkedin_url: str | None = None
    invite_code: str | None = None
    created_at: datetime | None = None
    # Live-games identity (students only).
    nickname: str | None = None
    avatar: str | None = None
    # The code this person typed at signup — the column the students table
    # groups by, and the answer to "which cohort did this account come from".
    invitation_code_used: str | None = None
    # Resolved from the linked Contact rather than stored on `users`. Absent
    # for accounts without one; enriched by the admin list route in one
    # batched query rather than per row.
    grade: str | None = None
    school_name: str | None = None
    # SP-0000 identity number (services/documents/id_card.py). card_id is
    # computed, not a real column — set explicitly by the admin list route,
    # same pattern as grade/school_name above.
    card_number: int | None = None
    card_id: str | None = None
    author_can_publish: bool | None = None
    author_scope_all: bool | None = None
    organization_id: UUID | None = None
    organization_name: str | None = None
    organization_name_arabic: str | None = None
    organization_type: str | None = None
    organization_country: str | None = None
    organization_city: str | None = None

    class Config:
        from_attributes = True


class InstructorApply(BaseModel):
    """Public POST /auth/instructor-apply payload (PLAN §6/§9.2 — replaces the
    no-pipeline stub that was stripped before Phase 3; the route is the same,
    the semantics are new). invite_code is checked against both
    invitation_codes and an ambassador's users.invite_code."""

    full_name: str
    email: EmailStr
    password: str
    invite_code: str | None = None
    university: str | None = None
    highest_degree: str | None = None
    highest_degree_other: str | None = None
    # Structured (2026-08-08) — city_of_residence_id/deliver_city_ids
    # reference the admin-configurable `cities` table (GET /public/cities)
    # instead of hand-typed strings.
    birthdate: date | None = None
    nationality: str | None = None
    work_status: str | None = None
    fluent_languages: list[str] | None = None
    graduated_university: str | None = None
    city_of_residence_id: UUID | None = None
    deliver_city_ids: list[UUID] | None = None
    background_areas: list[str] | None = None
    background_other: str | None = None
    has_own_transportation: bool = False
    country: str = "United Arab Emirates"

