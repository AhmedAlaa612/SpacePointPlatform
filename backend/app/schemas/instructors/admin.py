import uuid
from typing import List, Optional

from pydantic import BaseModel

from app.models.enums import ApplicationStatus, ModuleSubmissionStatus


class BatchDocumentsZipRequest(BaseModel):
    user_ids: List[uuid.UUID]
    include_generated: bool = False
    document_types: Optional[List[str]] = None


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


class DistributionEntry(BaseModel):
    name: str
    count: int


class SignupTrendEntry(BaseModel):
    month: str
    count: int


class AdminOverviewOut(BaseModel):
    pending_applications: int
    pending_payment_signatures: int
    total_instructors: int
    total_applicants: int
    total_facilitators: int = 0
    active_users_30d: int = 0
    # Pipeline counts from application_reviews (role-independent). The
    # applicants list only contains users still holding the `applicant`
    # role — final approval swaps it for `instructor`, so counting
    # "approved" from that list always yields ~0.
    total_applications: int = 0
    approved_applications: int = 0
    rejected_applications: int = 0
    university_distribution: List[DistributionEntry] = []
    city_distribution: List[DistributionEntry] = []
    signup_trend: List[SignupTrendEntry] = []


class FacilitatorCreate(BaseModel):
    full_name: str
    email: str
    password: str


class PortalSettingUpdate(BaseModel):
    key: str
    value: str
