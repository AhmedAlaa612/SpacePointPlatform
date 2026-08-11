"""Intern mission proposal schemas (7B-6)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MissionProposalCreateIn(BaseModel):
    title: str
    description: str
    repo_url: str | None = None


class MissionProposalReviewIn(BaseModel):
    status: str  # in_review|approved|rejected
    review_notes: str | None = None


class MissionProposalLinkIn(BaseModel):
    mission_id: UUID


class MissionProposalOut(BaseModel):
    id: UUID
    title: str
    description: str
    repo_url: str | None = None
    zip_url: str | None = None
    submitted_by: UUID
    submitted_by_name: str
    status: str
    reviewed_by: UUID | None = None
    review_notes: str | None = None
    mission_id: UUID | None = None
    created_at: datetime | None = None
    decided_at: datetime | None = None
