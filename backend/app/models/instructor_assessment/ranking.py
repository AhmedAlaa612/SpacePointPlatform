import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base

# Keys `factor_weights` on the active RankingWeightProfile must carry —
# validated at the Pydantic layer. Percentages need not sum to exactly 100;
# the read-time blend normalizes.
RANKING_FACTORS = [
    "assessment_score",
    "previous_rating",
    "relevant_experience",
    "sessions_hours",
    "reliability",
    "recent_performance",
]


class RankingWeightProfile(Base):
    """The configurable weighting behind the instructor Priority Score
    (operator ask: "doesn't need to be hardcoded initially, but the
    database structure should allow us to introduce or adjust weighting
    later"). `factor_weights` is a JSONB `{key: percentage}` over
    `RANKING_FACTORS` so adding, removing or reweighting a factor is a data
    change, never a migration.

    Exactly one row is `is_active` at a time for now (platform-wide) —
    per-program-type weighting later is a natural extension of this same
    shape, not a redesign.
    """

    __tablename__ = "ranking_weight_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    factor_weights = Column(JSONB, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
