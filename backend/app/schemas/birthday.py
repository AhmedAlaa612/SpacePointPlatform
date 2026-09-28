from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class BirthdayTestSendIn(BaseModel):
    email: EmailStr
    full_name: str = "SpacePoint Explorer"
    birthdate: date


class BirthdayTestSendOut(BaseModel):
    success: bool
    message: str
    recipient_email: str
    nasa_title: Optional[str] = None
    nasa_image_url: Optional[str] = None
    birth_year_referenced: Optional[int] = None


class UpcomingBirthdayUser(BaseModel):
    id: UUID
    full_name: str
    email: str
    roles: list[str] = []
    birthdate: date
    days_until: int
    next_birthday: date
    photo_url: Optional[str] = None
    status: str
    has_sent_this_year: bool = False

    class Config:
        from_attributes = True


class BirthdayLogOut(BaseModel):
    id: UUID
    user_id: UUID
    user_full_name: str
    user_email: str
    user_roles: list[str] = []
    user_birthdate: Optional[date] = None
    sent_at: datetime
    sent_at_year: int
    birth_year_referenced: Optional[int] = None
    nasa_image_url: Optional[str] = None
    nasa_title: Optional[str] = None
    nasa_explanation: Optional[str] = None
    status: str
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class BirthdayLogsResponse(BaseModel):
    items: list[BirthdayLogOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class BirthdayStatsOut(BaseModel):
    total_with_birthdays: int
    sent_this_year: int
    upcoming_7_days: int
    upcoming_30_days: int
    failed_count: int
