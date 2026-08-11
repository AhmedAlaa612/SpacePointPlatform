"""Intern mission proposals (7B-6, Missions Phase 2B, 2026-08-12) — the
front door onto `missions.status`'s draft/in_review/published pipeline
(P5-1), which has existed since Stage 5 but nothing has ever used.

D7's flow: intern proposes (repo link or zip + description), staff reviews,
staff integrates (real engineering work — porting the domain logic, maybe
building a new mission kind, wiring the verifier), *then* a real `Mission`
gets authored through the existing admin CRUD, starting at `status='draft'`
like any other. A proposal is deliberately never auto-promoted into a
`Mission` row — `status` here (submitted/in_review/approved/rejected) is
its own vocabulary, not `missions.status`. `mission_id` is set only once
integration is actually done, purely for traceability back to the proposal
that inspired it — nothing reads it to gate anything.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class MissionProposal(Base):
    __tablename__ = "mission_proposals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    repo_url = Column(String(512), nullable=True)
    zip_bucket = Column(String(64), nullable=True)
    zip_path = Column(String(512), nullable=True)
    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    # submitted|in_review|approved|rejected
    status = Column(String(12), nullable=False, default="submitted", server_default="submitted")
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_notes = Column(Text, nullable=True)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    decided_at = Column(DateTime(timezone=True), nullable=True)
