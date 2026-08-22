"""LMS learning-path domain (LMS redesign, 2026-08-08) — self-paced,
ordered course sequences with their own progress rollup, distinct from
`program_curriculum` (ops/cohort provisioning, LMS D5).

`LearningPathStep` mirrors `ProgramCurriculum`'s shape (program_id/course_id/
position -> learning_path_id/course_id/position) but is student-facing: a
student "starts" a path (bulk self-enrolls in every step's course) rather
than having it provisioned by ops at cohort-add time. A step's course may be
`kind='mission'` once Phase 2 authors missions — nothing here needs to change
for that, the step just points at whatever course exists.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class LearningPath(Base):
    """A published (or draft) curated sequence of courses — e.g. 'Space
    Science Foundations'. Image fields mirror `Course.image_bucket/path`
    (same storage-facade pattern); `is_published` mirrors `Course.is_published`
    (draft paths never show in `GET /lms/learning-paths`)."""

    __tablename__ = "learning_paths"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    is_published = Column(Boolean, nullable=False, default=False)
    image_bucket = Column(String(64), nullable=True)
    image_path = Column(String(512), nullable=True)
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Bundle pricing (2026-08-21) — mirrors Course.price_cents/currency. NULL
    # means "not purchasable as a bundle" — the existing free `/start`
    # self-enrol (open steps only) is unchanged either way. No enforced
    # relationship to the sum of the individual steps' prices — ops is
    # trusted to price it sensibly, same posture as course pricing.
    price_cents = Column(Integer, nullable=True)
    currency = Column(String(3), nullable=False, default="usd", server_default="usd")


class LearningPathStep(Base):
    """One ordered course inside a learning path. Same double-unique shape as
    `ProgramCurriculum`: a path can't list the same course twice, and can't
    name two steps the same position."""

    __tablename__ = "learning_path_steps"
    __table_args__ = (
        UniqueConstraint("learning_path_id", "course_id", name="uq_learning_path_steps_path_course"),
        UniqueConstraint("learning_path_id", "position", name="uq_learning_path_steps_path_position"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    learning_path_id = Column(
        UUID(as_uuid=True), ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False
    )
    course_id = Column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    position = Column(Integer, nullable=False)
