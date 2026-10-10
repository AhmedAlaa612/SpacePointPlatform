from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WebsiteConfigOut(BaseModel):
    id: int = 1
    students_count: str
    workshops_count: str
    partners_count: str
    satellites_flown_count: str
    instructor_invite_code: Optional[str] = None
    intern_invite_code: Optional[str] = None
    contact_email: str
    contact_phone: str
    contact_whatsapp: Optional[str] = None
    office_address: str
    social_linkedin: Optional[str] = None
    social_x: Optional[str] = None
    social_instagram: Optional[str] = None
    social_youtube: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class WebsiteConfigUpdate(BaseModel):
    students_count: Optional[str] = Field(default=None, max_length=64)
    workshops_count: Optional[str] = Field(default=None, max_length=64)
    partners_count: Optional[str] = Field(default=None, max_length=64)
    satellites_flown_count: Optional[str] = Field(default=None, max_length=64)
    instructor_invite_code: Optional[str] = Field(default=None, max_length=64)
    intern_invite_code: Optional[str] = Field(default=None, max_length=64)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    contact_phone: Optional[str] = Field(default=None, max_length=64)
    contact_whatsapp: Optional[str] = Field(default=None, max_length=64)
    office_address: Optional[str] = Field(default=None, max_length=255)
    social_linkedin: Optional[str] = Field(default=None, max_length=255)
    social_x: Optional[str] = Field(default=None, max_length=255)
    social_instagram: Optional[str] = Field(default=None, max_length=255)
    social_youtube: Optional[str] = Field(default=None, max_length=255)
