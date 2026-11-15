from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class PendingRequestsSummary(BaseModel):
    applications: int
    role_requests: int
    documents: int


class OnboardingSummary(BaseModel):
    pending: int
    to_be_reviewed: int
    phase1_in_progress: int
    phase2_in_progress: int
    phase3_in_progress: int
    phase2_or_3_in_progress: int


class PaymentsStatusSummary(BaseModel):
    pending: int
    published: int
    signed: int


class ActionQueueItem(BaseModel):
    id: str
    kind: Literal["app", "role_request", "doc_request", "applicant", "payment"]
    tag: str
    tone: Literal["emerald", "purple", "rose", "neutral"]
    title: str
    subtitle: str
    cta: str
    href: str
    created_at: datetime | None = None


class BusinessOverview(BaseModel):
    total_users: int
    students: int
    instructors: int
    interns: int
    organizations: int
    ambassadors: int
    mentors: int
    facilitators: int
    applicants: int
    org_members: int
    ops_admin: int


class AdminCommandOverviewOut(BaseModel):
    pending_requests: PendingRequestsSummary
    onboarding: OnboardingSummary
    payments: PaymentsStatusSummary
    actions: list[ActionQueueItem]
    business: BusinessOverview
