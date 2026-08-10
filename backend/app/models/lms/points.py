"""LMS points ledger (P2-1, Phase 2 Stage 2, 2026-08-10).

⚠️ Unrelated to `services/points.py`, which is the *ambassadors'* points
system keyed on `ambassador_id` — a completely different population. This
one is `services/lms/points.py`, keyed on `users.id`.

Append-only: a row is written once, at the moment of award, and never
updated or deleted (derive-don't-cache extends to "never recompute a past
award", not just "never cache a running total" — a leaderboard total is a
`SUM(points) GROUP BY user_id`, never a stored column). `source` names what
kind of event minted the row (quiz, migration-backfill, and — once built —
game/mission/attendance). `idempotency_key` scoped per-source, per-user, so
a quiz's key can collide harmlessly with a different source's key for the
same string, and a replay of the same award is a no-op by constraint —
the same discipline as `enroll()`/`register()` everywhere else here.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class PointEvent(Base):
    __tablename__ = "point_events"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "idempotency_key", name="uq_point_events_user_source_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # quiz|migration — game|mission|attendance land when those features do
    source = Column(String(16), nullable=False)
    points = Column(Integer, nullable=False)
    # Free-form provenance for this specific award — e.g. {"item_id": "..."}
    # for a quiz pass. Never read for scoring, only for "why does this
    # student have this many points" support questions.
    ref = Column(JSONB, nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
