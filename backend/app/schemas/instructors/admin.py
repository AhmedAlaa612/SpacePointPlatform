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


class AdminOverviewOut(BaseModel):
    pending_applications: int
    pending_payment_signatures: int
    total_instructors: int
    total_applicants: int


class FacilitatorCreate(BaseModel):
    full_name: str
    email: str
    password: str


class PortalSettingUpdate(BaseModel):
    key: str
    value: str
