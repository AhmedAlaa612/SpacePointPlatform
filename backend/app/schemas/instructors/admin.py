from typing import Optional

from pydantic import BaseModel

from app.models.enums import ApplicationStatus, ModuleSubmissionStatus


class AdminReviewUpdate(BaseModel):
    status: ApplicationStatus
    feedback: Optional[str] = None


class ModuleSubmissionDecision(BaseModel):
    status: ModuleSubmissionStatus
    feedback: Optional[str] = None


class InvitationCodeCreate(BaseModel):
    code: str
    max_uses: int = 20
    is_active: bool = True


class InvitationCodeUpdate(BaseModel):
    is_active: Optional[bool] = None
    max_uses: Optional[int] = None
