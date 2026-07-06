from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ApplicationStatus, ModuleSubmissionStatus, VideoSubmissionStatus


class VideoSubmissionOut(BaseModel):
    id: UUID
    video_no: int
    youtube_url: Optional[str] = None
    summary_text: Optional[str] = None
    word_count: int
    status: VideoSubmissionStatus
    submitted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VideoSummaryUpdate(BaseModel):
    youtube_url: Optional[str] = None
    summary_text: str
    submit: bool = False  # True -> validate word count and mark submitted


class ChecklistItemProgressOut(BaseModel):
    id: UUID
    item_code: str
    title: str
    description: Optional[str] = None
    is_required: bool
    is_completed: bool = False


class ModuleSectionOut(BaseModel):
    id: Optional[UUID] = None  # None for the implicit "no section" group
    title: Optional[str] = None
    items: list[ChecklistItemProgressOut] = []


class ChecklistModuleOut(BaseModel):
    id: UUID
    title: str
    sort_order: int
    sections: list[ModuleSectionOut] = []
    item_count: int = 0
    completed_count: int = 0
    submission_status: Optional[ModuleSubmissionStatus] = None
    submission_feedback: Optional[str] = None


class ModuleSubmissionOut(BaseModel):
    id: UUID
    module_id: UUID
    file_url: str
    original_filename: Optional[str] = None
    notes_text: Optional[str] = None
    status: ModuleSubmissionStatus
    feedback: Optional[str] = None
    submitted_at: datetime

    class Config:
        from_attributes = True


class PresentationSubmit(BaseModel):
    video_link: str


class AssessmentSubmissionOut(BaseModel):
    file_url: Optional[str] = None
    google_drive_link: Optional[str] = None
    comments: Optional[str] = None
    submitted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApplicationStatusOut(BaseModel):
    status: ApplicationStatus
    feedback: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    presentation_video_link: Optional[str] = None
    assessment: Optional[AssessmentSubmissionOut] = None
