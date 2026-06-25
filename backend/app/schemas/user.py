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

