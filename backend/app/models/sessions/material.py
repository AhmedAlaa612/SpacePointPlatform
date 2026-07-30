import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Material(Base):
    """Teaching material — a file or a link — attached at one level of the
    program → cohort → session chain (I5-6).

    **Operator decision, 2026-07-30:** a program has materials, a cohort can
    override them, and they can also be assigned to a single session. That is
    the same three-level shape `price` and `duration_hours` already use, so it
    introduces no new idea — but unlike those, materials are a *set* rather
    than a value, so "override" means the nearest level that has any rows wins
    outright. A cohort with its own materials does not inherit the program's;
    that is what override means, and merging the two would make it impossible
    to remove a program-level file for one cohort.

    Exactly one of `program_id` / `cohort_id` / `session_id` is set, enforced
    by CHECK — the same idiom as `activity_assignments` and `movements`.

    A row is either an uploaded file (`bucket` + `file_path`) or an external
    link (`url`), never both, also by CHECK. `Session.material_url` predates
    this and still works; it is left alone rather than migrated, because it is
    live and one nullable column costs nothing to keep.

    Managed by ops, facilitators and admin (operator's call). Instructors
    assigned to a session can read what resolves to it, but not change it.
    """

    __tablename__ = "session_materials"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_material_exactly_one_owner",
        ),
        CheckConstraint(
            "(file_path IS NOT NULL) <> (url IS NOT NULL)",
            name="ck_material_file_xor_link",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=True, index=True)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)

    # A file lives in storage; a link is just a URL. Never both (CHECK above).
    bucket = Column(String(64), nullable=True)
    file_path = Column(String(512), nullable=True)
    url = Column(Text, nullable=True)

    sort_order = Column(Integer, nullable=False, default=1)
    # SET NULL, not CASCADE — a departed facilitator must not delete the
    # material they uploaded (same rule as everywhere else in this codebase).
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
