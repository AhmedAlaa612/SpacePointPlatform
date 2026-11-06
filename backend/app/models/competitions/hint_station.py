"""Interactive Card Hint Station models (2026-11).
Supports multi-level hint assistance for onsite competitions and workshops.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class CohortHintChallenge(Base):
    """An onsite or workshop challenge tied to a program template or cohort override."""
    __tablename__ = "cohort_hint_challenges"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", "position", name="uq_hint_challenges_owner_pos"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # "program" (default template) or "cohort" (cohort-specific override)
    owner_type = Column(String(32), nullable=False, index=True)
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    challenge_code = Column(String(64), nullable=True)  # e.g. "CHALLENGE 01"
    topic = Column(String(128), nullable=True)           # e.g. "Sensor Data Collection"
    description = Column(Text, nullable=False)
    mission_statement = Column(Text, nullable=True)
    max_points = Column(Integer, nullable=False, default=20, server_default="20")
    position = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CohortHintCard(Base):
    """An assistance card within a challenge with progressive reveal and point deduction."""
    __tablename__ = "cohort_hint_cards"
    __table_args__ = (
        UniqueConstraint("challenge_id", "unlock_order", name="uq_hint_cards_challenge_order"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    challenge_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cohort_hint_challenges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    level = Column(Integer, nullable=False)               # 1 (Thinking), 2 (Technical), 3+ (Custom)
    level_label = Column(String(64), nullable=False)     # e.g. "Level 1 — Think about it"
    badge_label = Column(String(64), nullable=True)      # e.g. "Guiding question", "Technical guidance"
    title = Column(String(255), nullable=False)          # e.g. "Thinking Hint"
    teaser = Column(Text, nullable=True)                 # Teaser text visible before unlocking
    revealed_content = Column(Text, nullable=False)       # Secret hint content unlocked on confirm

    point_deduction = Column(Integer, nullable=False, default=2, server_default="2")  # Marks deducted (2, 3, 5, etc.)
    unlock_order = Column(Integer, nullable=False, default=1, server_default="1")    # Prerequisite order
    position = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CohortTeamHintReveal(Base):
    """Audit log of team hint reveals and marks deducted."""
    __tablename__ = "cohort_team_hint_reveals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cohorts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Team-scoped when student is in a team; nullable for individual fallback
    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("learner_teams.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Fallback when student has no team
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    challenge_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cohort_hint_challenges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hint_card_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cohort_hint_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revealed_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    points_deducted = Column(Integer, nullable=False)
    revealed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
