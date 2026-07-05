from datetime import datetime

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    new_password: str
    current_password: str | None = None


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
    created_at: datetime | None = None
    # Applicant-derived profile fields (instructors/facilitators/applicants).
    # Present only when the user has an applicant_profile; null otherwise.
    city_of_residence: str | None = None
    deliver_cities: list[str] | None = None
    has_own_transportation: bool | None = None


class UpdateMeRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    city_of_residence: str | None = None
    deliver_cities: list[str] | None = None
    has_own_transportation: bool | None = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(Token):
    user: UserOut
