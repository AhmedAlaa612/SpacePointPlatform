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


class UserOut(UserBase):
    id: UUID
    roles: list[UserRole] = []
    status: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class AmbassadorApply(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    country: str | None = None


class TeacherApply(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    invite_code: str
    answers: dict | None = None


class InstructorApply(BaseModel):
    """Public POST /auth/instructor-apply payload (PLAN §6/§9.2 — replaces the
    no-pipeline stub that was stripped before Phase 3; the route is the same,
    the semantics are new). invite_code is checked against both
    invitation_codes and an ambassador's users.invite_code."""

    full_name: str
    email: EmailStr
    password: str
    invite_code: str
    university: str | None = None
    highest_degree: str | None = None
    highest_degree_other: str | None = None
    city_of_residence: str | None = None
    deliver_cities: list[str] | None = None
    background_areas: list[str] | None = None
    background_other: str | None = None
    has_own_transportation: bool = False
    country: str = "United Arab Emirates"

