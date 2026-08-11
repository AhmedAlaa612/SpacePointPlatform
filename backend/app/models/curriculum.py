"""Unified prerequisites (7B-2, Missions Phase 2B, 2026-08-12) — courses and
missions as interchangeable "items" in one DAG (D2). Supersedes the
mission-only `mission_prerequisites` (P5-1); see the `ee33eb03e57d`
migration for the backfill.

Shared between `lms` and `missions` on purpose — neither domain owns the
concept of "you need X before Y" more than the other, so it lives at the
top level next to the other cross-domain models (`Notification`,
`Certificate`).
"""

from sqlalchemy import CheckConstraint, Column, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Prerequisite(Base):
    """A DAG edge: `(item_type, item_id)` cannot be attempted/enrolled until
    `(requires_type, requires_id)` is satisfied — a passed mission or a
    completed course, evaluated by `services/curriculum/prerequisites.py`.

    No FK on `item_id`/`requires_id`: a single column can't target two
    different tables (`courses` or `missions`), so existence is checked at
    the service layer when an edge is authored instead. `item_type` and
    `requires_type` are each 'course'|'mission'; self-reference is blocked
    by a CHECK, same as the mission-only table this replaces.
    """

    __tablename__ = "prerequisites"
    __table_args__ = (
        PrimaryKeyConstraint("item_type", "item_id", "requires_type", "requires_id", name="pk_prerequisites"),
        CheckConstraint("item_type IN ('course', 'mission')", name="ck_prerequisites_item_type"),
        CheckConstraint("requires_type IN ('course', 'mission')", name="ck_prerequisites_requires_type"),
        CheckConstraint(
            "NOT (item_type = requires_type AND item_id = requires_id)", name="ck_prerequisites_not_self",
        ),
    )

    item_type = Column(String(8), nullable=False)
    item_id = Column(UUID(as_uuid=True), nullable=False)
    requires_type = Column(String(8), nullable=False)
    requires_id = Column(UUID(as_uuid=True), nullable=False)
