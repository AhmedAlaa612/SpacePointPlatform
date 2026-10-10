from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Team ──────────────────────────────────────────────────────────────────


class TeamMemberOut(BaseModel):
    id: UUID
    name: str
    role: str
    department: str
    bio: Optional[str] = None
    photo_url: str
    linkedin_url: Optional[str] = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TeamMemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=128)
    department: str = Field(default="Engineering", max_length=64)
    bio: Optional[str] = None
    photo_url: str = Field(min_length=1, max_length=512)
    linkedin_url: Optional[str] = Field(default=None, max_length=512)
    display_order: int = 0
    is_active: bool = True


class TeamMemberUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role: Optional[str] = Field(default=None, min_length=1, max_length=128)
    department: Optional[str] = Field(default=None, max_length=64)
    bio: Optional[str] = None
    photo_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    linkedin_url: Optional[str] = Field(default=None, max_length=512)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


# ── Ambassadors ───────────────────────────────────────────────────────────


class AmbassadorOut(BaseModel):
    id: UUID
    name: str
    university: str
    major: Optional[str] = None
    year: Optional[str] = None
    bio: Optional[str] = None
    photo_url: str
    badge: Optional[str] = None
    linkedin_url: Optional[str] = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AmbassadorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    university: str = Field(min_length=1, max_length=255)
    major: Optional[str] = Field(default=None, max_length=128)
    year: Optional[str] = Field(default=None, max_length=32)
    bio: Optional[str] = None
    photo_url: str = Field(min_length=1, max_length=512)
    badge: Optional[str] = Field(default=None, max_length=64)
    linkedin_url: Optional[str] = Field(default=None, max_length=512)
    display_order: int = 0
    is_active: bool = True


class AmbassadorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    university: Optional[str] = Field(default=None, min_length=1, max_length=255)
    major: Optional[str] = Field(default=None, max_length=128)
    year: Optional[str] = Field(default=None, max_length=32)
    bio: Optional[str] = None
    photo_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    badge: Optional[str] = Field(default=None, max_length=64)
    linkedin_url: Optional[str] = Field(default=None, max_length=512)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


# ── Alumni ────────────────────────────────────────────────────────────────


class AlumniOut(BaseModel):
    id: UUID
    name: str
    program_completed: str
    current_role: str
    testimonial: Optional[str] = None
    photo_url: str
    linkedin_url: Optional[str] = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlumniCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    program_completed: str = Field(min_length=1, max_length=128)
    current_role: str = Field(min_length=1, max_length=255)
    testimonial: Optional[str] = None
    photo_url: str = Field(min_length=1, max_length=512)
    linkedin_url: Optional[str] = Field(default=None, max_length=512)
    display_order: int = 0
    is_active: bool = True


class AlumniUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    program_completed: Optional[str] = Field(default=None, min_length=1, max_length=128)
    current_role: Optional[str] = Field(default=None, min_length=1, max_length=255)
    testimonial: Optional[str] = None
    photo_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    linkedin_url: Optional[str] = Field(default=None, max_length=512)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


# ── Student missions ──────────────────────────────────────────────────────


class StudentMissionOut(BaseModel):
    id: UUID
    student_name: str
    project_title: str
    category: str
    description: str
    docx_url: Optional[str] = None
    photo_url: Optional[str] = None
    metrics_json: Optional[dict] = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StudentMissionCreate(BaseModel):
    student_name: str = Field(min_length=1, max_length=255)
    project_title: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1)
    docx_url: Optional[str] = Field(default=None, max_length=512)
    photo_url: Optional[str] = Field(default=None, max_length=512)
    metrics_json: Optional[dict] = None
    display_order: int = 0
    is_active: bool = True


class StudentMissionUpdate(BaseModel):
    student_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    project_title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    category: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, min_length=1)
    docx_url: Optional[str] = Field(default=None, max_length=512)
    photo_url: Optional[str] = Field(default=None, max_length=512)
    metrics_json: Optional[dict] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
