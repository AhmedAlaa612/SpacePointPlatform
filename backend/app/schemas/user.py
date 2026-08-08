from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole


class UserBase(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None


class UserCreate(UserBase):
    password: str
    roles: list[UserRole] = []


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    roles: list[UserRole] | None = None
    phone: str | None = None


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


class UserOut(UserBase):
    id: UUID
    roles: list[UserRole] = []
    status: str | None = None
    country: str | None = None
    photo_url: str | None = None
    linkedin_url: str | None = None
    invite_code: str | None = None
    created_at: datetime | None = None

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
    city_of_residence_id: UUID | None = None
    deliver_city_ids: list[UUID] | None = None
    background_areas: list[str] | None = None
    background_other: str | None = None
    has_own_transportation: bool = False
    country: str = "United Arab Emirates"

