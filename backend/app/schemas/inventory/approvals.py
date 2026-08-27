"""The approval gate (2026-08-27 follow-up). See
`services/inventory/approvals.py` for ACTION_TYPES and the gate/executor
machinery these schemas surface."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ApprovalRequestOut(BaseModel):
    id: uuid.UUID
    action_type: str
    action_label: str
    status: str
    summary: str
    requested_by_user_id: uuid.UUID
    requested_by_name: str
    requested_at: datetime | None
    reviewed_by_user_id: uuid.UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None


class ApprovalDecisionIn(BaseModel):
    note: str | None = None


class ActionPolicyOut(BaseModel):
    action_type: str
    action_label: str
    requires_approval: bool
    updated_by_name: str | None = None
    updated_at: datetime | None = None


class ActionPolicyUpdate(BaseModel):
    requires_approval: bool
